"""Database revision and integrity contracts."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from api.database import init_db, upgrade_db
from api.models import (
    ActionTable,
    AssumptionTable,
    ChangeRequestTable,
    DecisionTable,
    DeliverableTable,
    DependencyTable,
    GateCriterionTable,
    GateReviewTable,
    GateTable,
    IssueTable,
    ProjectMemberTable,
    ProjectTable,
    TaskTable,
    WorkPackageTable,
)


def _memory_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_init_db_upgrades_empty_database_to_baseline(engine: Engine) -> None:
    tables = inspect(engine).get_table_names()
    assert {
        "projects",
        "issues",
        "assumptions",
        "work_packages",
        "deliverables",
        "gates",
        "gate_criteria",
        "gate_reviews",
    }.issubset(tables)
    assert _revision(engine) == "20260925_0018"


def test_baseline_adopts_existing_schema_without_losing_data() -> None:
    legacy_engine = _memory_engine()
    upgrade_db(legacy_engine, "20260316_0002")
    with legacy_engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO projects (
                    created_at, updated_at, project_id, project_name, domain,
                    project_manager, start_date, project_phase, business_priority
                ) VALUES (
                    :created_at, :updated_at, :project_id, :project_name, :domain,
                    :project_manager, :start_date, :project_phase, :business_priority
                )
                """),
            {
                "created_at": "2026-03-01 00:00:00",
                "updated_at": "2026-03-01 00:00:00",
                "project_id": "P-MIGRATION",
                "project_name": "Migration Preservation Probe",
                "domain": "Engineering",
                "project_manager": "Synthetic Manager",
                "start_date": "2026-01-01",
                "project_phase": "Execution",
                "business_priority": "Medium",
            },
        )
        connection.execute(text("DROP TABLE alembic_version"))

    init_db(legacy_engine)
    init_db(legacy_engine)

    with Session(legacy_engine) as session:
        project = session.get(ProjectTable, "P-MIGRATION")
        assert project is not None
        assert project.row_version == 1
    assert _revision(legacy_engine) == "20260925_0018"


def test_baseline_rejects_complete_schema_missing_unique_index() -> None:
    legacy_engine = _memory_engine()
    upgrade_db(legacy_engine, "20260316_0002")
    with legacy_engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_users_email"))
        connection.execute(text("DROP TABLE alembic_version"))

    with pytest.raises(RuntimeError, match="users.*index"):
        init_db(legacy_engine)

    assert "alembic_version" not in inspect(legacy_engine).get_table_names()


def test_baseline_rejects_partial_legacy_schema() -> None:
    legacy_engine = _memory_engine()
    ProjectTable.__table__.create(legacy_engine)

    with pytest.raises(RuntimeError, match="partial pre-Alembic schema"):
        init_db(legacy_engine)


def test_sqlite_rejects_invalid_foreign_key(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            TaskTable(
                task_id="T-INVALID-FK",
                project_id="P-NOT-THERE",
                milestone_id="M-NOT-THERE",
                task_name="Invalid reference probe",
                status="Not Started",
                planned_end_date=date(2026, 4, 1),
                forecast_end_date=date(2026, 4, 1),
                completion_percent=0,
                is_blocked=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_sqlite_rejects_cross_project_task_milestone(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        session.add(
            TaskTable(
                task_id="T-INVALID-MILESTONE-PROJECT",
                project_id="P-002",
                milestone_id="M-701",
                task_name="Cross-project hierarchy probe",
                status="Not Started",
                planned_end_date=date(2026, 10, 1),
                forecast_end_date=date(2026, 10, 1),
                completion_percent=0,
                is_blocked=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_migration_refuses_legacy_cross_project_task_milestone() -> None:
    legacy_engine = _memory_engine()
    upgrade_db(legacy_engine, "20260316_0007")
    with legacy_engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO projects (
                    created_at, updated_at, project_id, project_name, domain,
                    project_manager, start_date, project_phase, business_priority
                ) VALUES (
                    :created_at, :updated_at, :project_id, :project_name, :domain,
                    :project_manager, :start_date, :project_phase, :business_priority
                )
                """),
            [
                {
                    "created_at": "2026-08-27 00:00:00",
                    "updated_at": "2026-08-27 00:00:00",
                    "project_id": project_id,
                    "project_name": project_name,
                    "domain": "Engineering",
                    "project_manager": "Synthetic Manager",
                    "start_date": "2026-01-01",
                    "project_phase": "Execution",
                    "business_priority": "Medium",
                }
                for project_id, project_name in (
                    ("P-LEFT", "Left project"),
                    ("P-RIGHT", "Right project"),
                )
            ],
        )
        connection.execute(text("""
                INSERT INTO milestones (
                    created_at, updated_at, milestone_id, project_id,
                    milestone_name, status, criticality
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'M-RIGHT', 'P-RIGHT', 'Right milestone', 'Not Started', 'Medium'
                )
                """))
        connection.execute(text("""
                INSERT INTO tasks (
                    created_at, updated_at, task_id, project_id, milestone_id,
                    task_name, status, planned_end_date, forecast_end_date,
                    completion_percent, is_blocked
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'T-LEFT', 'P-LEFT', 'M-RIGHT', 'Invalid legacy hierarchy',
                    'Not Started', '2026-10-01', '2026-10-01', 0, 0
                )
                """))

    with pytest.raises(RuntimeError, match="T-LEFT -> M-RIGHT in P-LEFT"):
        upgrade_db(legacy_engine)


def test_sqlite_rejects_cross_project_change_request(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        session.add(
            ChangeRequestTable(
                change_request_id="CR-INVALID-REQUIREMENT-PROJECT",
                project_id="P-002",
                requirement_id="REQ-7001",
                change_description="Cross-project requirement probe",
                reason="Validate persistence integrity",
                priority="High",
                status="Open",
                requested_date=date(2026, 8, 1),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_dependency_migration_refuses_a_legacy_cycle_with_source_ids() -> None:
    legacy_engine = _memory_engine()
    upgrade_db(legacy_engine, "20260316_0009")
    with legacy_engine.begin() as connection:
        connection.execute(text("""
                INSERT INTO projects (
                    created_at, updated_at, project_id, project_name, domain,
                    project_manager, start_date, project_phase, business_priority
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'P-CYCLE', 'Cycle project', 'Engineering', 'Synthetic Manager',
                    '2026-01-01', 'Execution', 'Medium'
                )
                """))
        connection.execute(text("""
                INSERT INTO milestones (
                    created_at, updated_at, milestone_id, project_id,
                    milestone_name, status, criticality
                ) VALUES
                    ('2026-08-27 00:00:00', '2026-08-27 00:00:00',
                     'M-CYCLE-1', 'P-CYCLE', 'First milestone', 'Not Started', 'Medium'),
                    ('2026-08-27 00:00:00', '2026-08-27 00:00:00',
                     'M-CYCLE-2', 'P-CYCLE', 'Second milestone', 'Not Started', 'Medium')
                """))
        connection.execute(text("""
                INSERT INTO dependencies (
                    created_at, updated_at, dependency_id, project_id,
                    predecessor_type, predecessor_id, successor_type, successor_id,
                    dependency_name, status, delay_days, criticality
                ) VALUES
                    ('2026-08-27 00:00:00', '2026-08-27 00:00:00',
                     'D-CYCLE-1', 'P-CYCLE', 'Milestone', 'M-CYCLE-1',
                     'Milestone', 'M-CYCLE-2', 'First edge', 'On Track', 0, 'Medium'),
                    ('2026-08-27 00:00:00', '2026-08-27 00:00:00',
                     'D-CYCLE-2', 'P-CYCLE', 'Milestone', 'M-CYCLE-2',
                     'Milestone', 'M-CYCLE-1', 'Second edge', 'On Track', 0, 'Medium')
                """))

    with pytest.raises(RuntimeError, match="D-CYCLE-1, D-CYCLE-2"):
        upgrade_db(legacy_engine)


def test_migration_refuses_legacy_cross_project_change_request() -> None:
    legacy_engine = _memory_engine()
    upgrade_db(legacy_engine, "20260316_0013")
    with legacy_engine.begin() as connection:
        connection.execute(text("""
                INSERT INTO projects (
                    created_at, updated_at, project_id, project_name, domain,
                    project_manager, start_date, project_phase, business_priority
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'P-LEFT', 'Left project', 'Engineering', 'Synthetic Manager',
                    '2026-01-01', 'Execution', 'Medium'
                ), (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'P-RIGHT', 'Right project', 'Engineering', 'Synthetic Manager',
                    '2026-01-01', 'Execution', 'Medium'
                )
                """))
        connection.execute(text("""
                INSERT INTO requirements (
                    created_at, updated_at, requirement_id, project_id, requirement_text,
                    requirement_type, priority, status
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'REQ-RIGHT', 'P-RIGHT', 'Right requirement', 'System', 'High', 'Draft'
                )
                """))
        connection.execute(text("""
                INSERT INTO change_requests (
                    created_at, updated_at, change_request_id, project_id, requirement_id,
                    change_description, reason, priority, status, requested_date
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'CR-CROSS', 'P-LEFT', 'REQ-RIGHT', 'Invalid legacy reference',
                    'Migration probe', 'High', 'Open', '2026-08-27'
                )
                """))

    with pytest.raises(RuntimeError, match="CR-CROSS.*REQ-RIGHT.*P-LEFT"):
        upgrade_db(legacy_engine)


def test_migration_refuses_archived_cross_project_change_request() -> None:
    legacy_engine = _memory_engine()
    upgrade_db(legacy_engine, "20260316_0013")
    with legacy_engine.begin() as connection:
        connection.execute(text("""
                INSERT INTO projects (
                    created_at, updated_at, project_id, project_name, domain,
                    project_manager, start_date, project_phase, business_priority
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'P-ARCHIVE-LEFT', 'Archive left', 'Engineering', 'Synthetic Manager',
                    '2026-01-01', 'Execution', 'Medium'
                ), (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'P-ARCHIVE-RIGHT', 'Archive right', 'Engineering', 'Synthetic Manager',
                    '2026-01-01', 'Execution', 'Medium'
                )
                """))
        connection.execute(text("""
                INSERT INTO requirements (
                    created_at, updated_at, requirement_id, project_id, requirement_text,
                    requirement_type, priority, status
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'REQ-ARCHIVE-RIGHT', 'P-ARCHIVE-RIGHT', 'Archived reference',
                    'System', 'High', 'Draft'
                )
                """))
        connection.execute(text("""
                INSERT INTO change_requests (
                    created_at, updated_at, deleted_at, change_request_id, project_id,
                    requirement_id, change_description, reason, priority, status,
                    requested_date
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-28 00:00:00',
                    '2026-08-28 00:00:00', 'CR-ARCHIVE-CROSS', 'P-ARCHIVE-LEFT',
                    'REQ-ARCHIVE-RIGHT', 'Archived invalid legacy reference',
                    'Migration probe', 'High', 'Rejected', '2026-08-27'
                )
                """))

    with pytest.raises(
        RuntimeError,
        match="CR-ARCHIVE-CROSS.*REQ-ARCHIVE-RIGHT.*P-ARCHIVE-LEFT",
    ):
        upgrade_db(legacy_engine)


def test_migration_refuses_live_change_request_for_withdrawn_requirement() -> None:
    legacy_engine = _memory_engine()
    upgrade_db(legacy_engine, "20260316_0013")
    with legacy_engine.begin() as connection:
        connection.execute(text("""
                INSERT INTO projects (
                    created_at, updated_at, project_id, project_name, domain,
                    project_manager, start_date, project_phase, business_priority
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'P-WITHDRAWN', 'Withdrawn reference project', 'Engineering',
                    'Synthetic Manager', '2026-01-01', 'Execution', 'Medium'
                )
                """))
        connection.execute(text("""
                INSERT INTO requirements (
                    created_at, updated_at, deleted_at, requirement_id, project_id,
                    requirement_text, requirement_type, priority, status
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    '2026-08-28 00:00:00', 'REQ-WITHDRAWN', 'P-WITHDRAWN',
                    'Withdrawn requirement', 'System', 'High', 'Draft'
                )
                """))
        connection.execute(text("""
                INSERT INTO change_requests (
                    created_at, updated_at, change_request_id, project_id, requirement_id,
                    change_description, reason, priority, status, requested_date
                ) VALUES (
                    '2026-08-27 00:00:00', '2026-08-27 00:00:00',
                    'CR-WITHDRAWN', 'P-WITHDRAWN', 'REQ-WITHDRAWN',
                    'Live request against withdrawn evidence', 'Migration probe',
                    'High', 'Open', '2026-08-27'
                )
                """))

    with pytest.raises(RuntimeError, match="CR-WITHDRAWN.*REQ-WITHDRAWN.*P-WITHDRAWN"):
        upgrade_db(legacy_engine)


def test_existing_delivery_rows_gain_empty_schedule_evidence(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        task = session.get(TaskTable, "T-2001")
        assert task is not None
        assert task.planned_start_date is None
        assert task.forecast_start_date is None
        assert task.actual_start_date is None
        assert task.actual_end_date is None
        assert task.deliverable_id is None
        assert task.parent_task_id is None
        assert session.exec(select(WorkPackageTable)).all() == []
        assert session.exec(select(DeliverableTable)).all() == []
        dependency = session.get(DependencyTable, "D-2002")
        assert dependency is not None
        assert dependency.relationship_type is None
        assert dependency.lag_days is None


def test_database_rejects_cross_project_delivery_hierarchy(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        session.add_all(
            [
                WorkPackageTable(
                    work_package_id="WP-LEFT",
                    project_id="P-002",
                    work_package_name="Left package",
                    description="Synthetic hierarchy integrity probe.",
                    status="Planned",
                    priority="Medium",
                ),
                DeliverableTable(
                    deliverable_id="DEL-RIGHT",
                    project_id="P-007",
                    work_package_id="WP-LEFT",
                    deliverable_name="Cross-project deliverable",
                    description="Synthetic hierarchy integrity probe.",
                    status="Planned",
                    priority="Medium",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_rejects_cross_project_or_self_task_parent(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        task = session.get(TaskTable, "T-2001")
        assert task is not None
        task.parent_task_id = "T-7001"
        with pytest.raises(IntegrityError):
            session.commit()

    with Session(seeded_engine) as session:
        task = session.get(TaskTable, "T-2001")
        assert task is not None
        task.parent_task_id = task.task_id
        with pytest.raises(IntegrityError):
            session.commit()


def test_stage_gate_migration_adds_empty_governance_tables(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        assert session.exec(select(GateTable)).all() == []
        assert session.exec(select(GateCriterionTable)).all() == []
        assert session.exec(select(GateReviewTable)).all() == []


@pytest.mark.parametrize(
    "gate",
    [
        GateTable(
            gate_id="G-CROSS-PROJECT",
            project_id="P-002",
            milestone_id="M-701",
            gate_name="Cross-project Gate",
            sequence=90,
            planned_review_date=date(2026, 10, 1),
            owner="Test Owner",
        ),
        GateTable(
            gate_id="G-INVALID-STATUS",
            project_id="P-002",
            milestone_id="M-202",
            gate_name="Invalid status Gate",
            sequence=91,
            planned_review_date=date(2026, 10, 1),
            owner="Test Owner",
            status="Invented",
        ),
    ],
)
def test_database_rejects_invalid_gate_records(seeded_engine: Engine, gate: GateTable) -> None:
    with Session(seeded_engine) as session:
        session.add(gate)
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_requires_criterion_evidence_and_immutable_reviews(
    seeded_engine: Engine,
) -> None:
    with Session(seeded_engine) as session:
        gate = GateTable(
            gate_id="G-INTEGRITY",
            project_id="P-002",
            milestone_id="M-202",
            gate_name="Integrity Gate",
            sequence=92,
            planned_review_date=date(2026, 10, 1),
            owner="Test Owner",
            status="In Review",
        )
        session.add(gate)
        session.commit()

        session.add(
            GateCriterionTable(
                criterion_id="GC-MISSING-EVIDENCE",
                gate_id=gate.gate_id,
                project_id=gate.project_id,
                criterion_type="Exit",
                criterion_name="Evidence required",
                description="Synthetic constraint probe.",
                evidence_required=True,
                status="Met",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            GateReviewTable(
                review_id="GR-IMMUTABLE",
                gate_id=gate.gate_id,
                project_id=gate.project_id,
                reviewer="Test Reviewer",
                review_cycle=1,
                outcome="Approved",
                rationale="Synthetic immutable review probe.",
                created_by="reviewer@test.example.com",
            )
        )
        session.commit()

    with seeded_engine.connect() as connection:
        with pytest.raises(IntegrityError, match="Gate Reviews are immutable"):
            connection.execute(
                text(
                    "UPDATE gate_reviews SET outcome = 'Rejected' "
                    "WHERE review_id = 'GR-IMMUTABLE'"
                )
            )
            connection.commit()
        connection.rollback()
        with pytest.raises(IntegrityError, match="Gate Reviews are immutable"):
            connection.execute(text("DELETE FROM gate_reviews WHERE review_id = 'GR-IMMUTABLE'"))
            connection.commit()


@pytest.mark.parametrize(
    "date_fields",
    [
        {"planned_start_date": date(2026, 10, 2)},
        {"forecast_start_date": date(2026, 10, 2)},
        {"actual_end_date": date(2026, 10, 1)},
        {
            "actual_start_date": date(2026, 10, 2),
            "actual_end_date": date(2026, 10, 1),
        },
    ],
)
def test_database_rejects_incoherent_task_schedule(
    seeded_engine: Engine, date_fields: dict[str, date]
) -> None:
    with Session(seeded_engine) as session:
        session.add(
            TaskTable(
                task_id="T-INVALID-SCHEDULE",
                project_id="P-002",
                milestone_id="M-202",
                task_name="Invalid schedule probe",
                status="Not Started",
                planned_end_date=date(2026, 10, 1),
                forecast_end_date=date(2026, 10, 1),
                completion_percent=0,
                is_blocked=False,
                **date_fields,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "overrides",
    [
        {"predecessor_type": "Invented"},
        {"successor_type": "Supplier"},
        {"relationship_type": "Finish-to-Start", "lag_days": None},
        {
            "predecessor_type": "Task",
            "predecessor_id": "T-2001",
            "successor_type": "Task",
            "successor_id": "T-2001",
        },
        {"delay_days": -1},
    ],
)
def test_database_rejects_invalid_dependency_evidence(
    seeded_engine: Engine, overrides: dict[str, object]
) -> None:
    values: dict[str, object] = {
        "dependency_id": "D-INVALID-EVIDENCE",
        "project_id": "P-002",
        "predecessor_type": "Task",
        "predecessor_id": "T-2002",
        "successor_type": "Milestone",
        "successor_id": "M-203",
        "dependency_name": "Invalid dependency evidence probe",
        "relationship_type": "Finish-to-Start",
        "lag_days": 0,
        "status": "On Track",
        "delay_days": 0,
        "criticality": "High",
    }
    with Session(seeded_engine) as session:
        session.add(DependencyTable(**(values | overrides)))
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_rejects_duplicate_dependency_edge(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        session.add(
            DependencyTable(
                dependency_id="D-DUPLICATE-EDGE",
                project_id="P-002",
                predecessor_type="Task",
                predecessor_id="T-2001",
                successor_type="Task",
                successor_id="T-2002",
                dependency_name="Duplicate edge probe",
                relationship_type="Finish-to-Start",
                lag_days=0,
                status="On Track",
                delay_days=0,
                criticality="High",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_project_membership_pair_is_unique(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        membership = session.exec(select(ProjectMemberTable)).first()
        assert membership is not None
        session.add(
            ProjectMemberTable(
                project_id=membership.project_id,
                user_id=membership.user_id,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "row",
    [
        IssueTable(
            issue_id="ISS-INVALID-STATE",
            project_id="P-002",
            title="Invalid state probe",
            description="Synthetic integrity probe.",
            severity="Low",
            status="Invented",
            raised_date=date(2026, 8, 27),
        ),
        AssumptionTable(
            assumption_id="ASM-INVALID-STATE",
            project_id="P-002",
            assumption_text="Synthetic integrity probe.",
            owner="Test Owner",
            status="Invented",
        ),
    ],
)
def test_governance_registers_reject_unknown_states(
    seeded_engine: Engine, row: IssueTable | AssumptionTable
) -> None:
    with Session(seeded_engine) as session:
        session.add(row)
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "row",
    [
        ActionTable(
            action_id="A-INVALID-STATE",
            project_id="P-002",
            action_description="Synthetic integrity probe.",
            due_date=date(2026, 9, 1),
            status="Invented",
            priority="Low",
        ),
        DecisionTable(
            decision_id="DEC-INVALID-STATE",
            project_id="P-002",
            title="Invalid state probe",
            description="Synthetic integrity probe.",
            category="Delivery",
            decision_date=date(2026, 8, 27),
            owner="Test Owner",
            status="Invented",
        ),
    ],
)
def test_existing_governance_records_reject_unknown_states(
    seeded_engine: Engine, row: ActionTable | DecisionTable
) -> None:
    with Session(seeded_engine) as session:
        session.add(row)
        with pytest.raises(IntegrityError):
            session.commit()


def test_migrated_schema_matches_declared_models() -> None:
    """The migration chain must create every table and column the models declare.

    Guards against drift, where a model gains a field that no migration adds. Runtime uses
    Alembic rather than ``create_all``, so such a field would only fail in production.
    """
    engine = _memory_engine()
    init_db(engine)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    missing: list[str] = []
    for table_name, table in SQLModel.metadata.tables.items():
        if table_name not in existing_tables:
            missing.append(f"missing table: {table_name}")
            continue
        migrated_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing.extend(
            f"missing column: {table_name}.{column.name}"
            for column in table.columns
            if column.name not in migrated_columns
        )

    assert missing == []
