"""SQLModel table definitions for EPOS Next persistence.

Business tables mirror the Pydantic entity models in ``src/schemas.py`` column for column, plus
audit fields. Use ``api.crud.to_entity`` to convert a row into an engine input model, since the
audit columns are not part of the engine contract.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import declared_attr
from sqlmodel import Field, SQLModel

from api.security.permissions import DEFAULT_ROLE, Role
from src.gate_rules import GateCriterionStatus, GateStatus
from src.workflow_rules import AssumptionStatus, IssueStatus


def _utc_now() -> datetime:
    """Timezone-aware creation timestamp for audit rows."""
    return datetime.now(UTC)


class AuditMixin(SQLModel):
    """Provenance and soft-delete columns shared by every business record.

    ``deleted_at`` marks a record as withdrawn. Soft-deleted rows are excluded from reads and from
    the portfolio handed to the engines, so a deletion changes the analysis without destroying the
    audit trail.
    """

    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    created_by: str | None = Field(default=None)
    updated_by: str | None = Field(default=None)
    deleted_at: datetime | None = Field(default=None, index=True)
    row_version: int = Field(default=1, ge=1)

    @declared_attr
    def __mapper_args__(cls) -> dict[str, object]:
        return {
            "version_id_col": cls.__table__.c.row_version,
            "version_id_generator": False,
        }


class ProjectTable(AuditMixin, table=True):
    __tablename__ = "projects"

    project_id: str = Field(primary_key=True)
    project_name: str
    domain: str
    project_manager: str
    start_date: date
    baseline_end_date: date | None = None
    forecast_end_date: date | None = None
    status_update_date: date | None = None
    project_phase: str
    business_priority: str


class MilestoneTable(AuditMixin, table=True):
    __tablename__ = "milestones"
    __table_args__ = (
        UniqueConstraint("milestone_id", "project_id", name="uq_milestones_id_project"),
    )

    milestone_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    milestone_name: str
    baseline_date: date | None = None
    forecast_date: date | None = None
    actual_date: date | None = None
    status: str
    criticality: str
    owner: str | None = None


class GateTable(AuditMixin, table=True):
    """A governed project stage or release-readiness review point."""

    __tablename__ = "gates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["milestone_id", "project_id"],
            ["milestones.milestone_id", "milestones.project_id"],
            name="fk_gates_milestone_project",
        ),
        UniqueConstraint("gate_id", "project_id", name="uq_gates_id_project"),
        UniqueConstraint("project_id", "sequence", name="uq_gates_project_sequence"),
        CheckConstraint("sequence > 0", name="ck_gates_positive_sequence"),
        CheckConstraint("review_cycle > 0", name="ck_gates_positive_review_cycle"),
        CheckConstraint(
            "status IN ('Not Started', 'Preparing', 'Ready for Review', 'In Review', "
            "'Passed', 'Passed with Conditions', 'Failed', 'Deferred', 'Withdrawn')",
            name="ck_gates_status",
        ),
    )

    gate_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    milestone_id: str | None = Field(default=None, index=True)
    gate_name: str
    sequence: int
    planned_review_date: date
    actual_review_date: date | None = None
    owner: str
    status: str = Field(default=GateStatus.NOT_STARTED.value, index=True)
    review_cycle: int = 1
    applicable_baseline: str | None = None


class GateCriterionTable(AuditMixin, table=True):
    """One entry or exit criterion configured for a project Gate."""

    __tablename__ = "gate_criteria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["gate_id", "project_id"],
            ["gates.gate_id", "gates.project_id"],
            name="fk_gate_criteria_gate_project",
        ),
        CheckConstraint("criterion_type IN ('Entry', 'Exit')", name="ck_gate_criteria_type"),
        CheckConstraint(
            "status IN ('Not Assessed', 'Met', 'Not Met')",
            name="ck_gate_criteria_status",
        ),
        CheckConstraint(
            "status != 'Met' OR evidence_required = 0 OR "
            "(evidence_reference IS NOT NULL AND length(trim(evidence_reference)) > 0)",
            name="ck_gate_criteria_required_evidence",
        ),
    )

    criterion_id: str = Field(primary_key=True)
    gate_id: str = Field(index=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    criterion_type: str
    criterion_name: str
    description: str
    is_mandatory: bool = True
    evidence_required: bool = False
    status: str = Field(default=GateCriterionStatus.NOT_ASSESSED.value, index=True)
    evidence_reference: str | None = None
    assessment_rationale: str | None = None
    assessed_by: str | None = None
    assessed_at: datetime | None = None


class GateReviewTable(SQLModel, table=True):
    """An immutable human review outcome for one project Gate."""

    __tablename__ = "gate_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["gate_id", "project_id"],
            ["gates.gate_id", "gates.project_id"],
            name="fk_gate_reviews_gate_project",
        ),
        CheckConstraint(
            "outcome IN ('Approved', 'Approved with Conditions', 'Rejected', 'Deferred')",
            name="ck_gate_reviews_outcome",
        ),
        CheckConstraint("review_cycle > 0", name="ck_gate_reviews_positive_cycle"),
        UniqueConstraint("gate_id", "review_cycle", name="uq_gate_reviews_gate_cycle"),
        CheckConstraint(
            "(outcome = 'Approved with Conditions' AND conditions IS NOT NULL "
            "AND length(trim(conditions)) > 0) OR "
            "(outcome != 'Approved with Conditions' AND conditions IS NULL)",
            name="ck_gate_reviews_conditions",
        ),
    )

    review_id: str = Field(primary_key=True)
    gate_id: str = Field(index=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    reviewer: str
    review_cycle: int
    outcome: str = Field(index=True)
    rationale: str
    conditions: str | None = None
    reviewed_at: datetime = Field(default_factory=_utc_now, index=True)
    created_by: str


class WorkPackageTable(AuditMixin, table=True):
    """A governed grouping of engineering deliverables within one project."""

    __tablename__ = "work_packages"
    __table_args__ = (
        UniqueConstraint("work_package_id", "project_id", name="uq_work_packages_id_project"),
    )

    work_package_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    work_package_name: str
    description: str
    owner: str | None = None
    accountable_owner: str | None = None
    status: str = Field(index=True)
    priority: str


class DeliverableTable(AuditMixin, table=True):
    """A governed engineering outcome owned by one Work Package."""

    __tablename__ = "deliverables"
    __table_args__ = (
        ForeignKeyConstraint(
            ["work_package_id", "project_id"],
            ["work_packages.work_package_id", "work_packages.project_id"],
            name="fk_deliverables_work_package_project",
        ),
        UniqueConstraint("deliverable_id", "project_id", name="uq_deliverables_id_project"),
    )

    deliverable_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    work_package_id: str = Field(index=True)
    deliverable_name: str
    description: str
    owner: str | None = None
    accountable_owner: str | None = None
    status: str = Field(index=True)
    priority: str
    acceptance_criteria: str | None = None
    completion_evidence: str | None = None


class TaskTable(AuditMixin, table=True):
    __tablename__ = "tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["milestone_id", "project_id"],
            ["milestones.milestone_id", "milestones.project_id"],
            name="fk_tasks_milestone_project",
        ),
        ForeignKeyConstraint(
            ["deliverable_id", "project_id"],
            ["deliverables.deliverable_id", "deliverables.project_id"],
            name="fk_tasks_deliverable_project",
        ),
        ForeignKeyConstraint(
            ["parent_task_id", "project_id"],
            ["tasks.task_id", "tasks.project_id"],
            name="fk_tasks_parent_project",
        ),
        UniqueConstraint("task_id", "project_id", name="uq_tasks_id_project"),
        CheckConstraint(
            "parent_task_id IS NULL OR parent_task_id != task_id",
            name="ck_tasks_not_own_parent",
        ),
        CheckConstraint(
            "planned_start_date IS NULL OR planned_start_date <= planned_end_date",
            name="ck_tasks_planned_date_order",
        ),
        CheckConstraint(
            "forecast_start_date IS NULL OR forecast_start_date <= forecast_end_date",
            name="ck_tasks_forecast_date_order",
        ),
        CheckConstraint(
            "actual_end_date IS NULL OR actual_start_date IS NOT NULL",
            name="ck_tasks_actual_end_requires_start",
        ),
        CheckConstraint(
            "actual_start_date IS NULL OR actual_end_date IS NULL "
            "OR actual_start_date <= actual_end_date",
            name="ck_tasks_actual_date_order",
        ),
    )

    task_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    milestone_id: str = Field(index=True)
    deliverable_id: str | None = Field(default=None, index=True)
    parent_task_id: str | None = Field(default=None, index=True)
    task_name: str
    owner: str | None = None
    owner_user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    status: str
    planned_start_date: date | None = None
    forecast_start_date: date | None = None
    actual_start_date: date | None = None
    planned_end_date: date
    forecast_end_date: date
    actual_end_date: date | None = None
    completion_percent: int
    is_blocked: bool
    last_updated_date: date | None = None
    # Optional manager review of reported completion. Reported and accepted stay separate.
    review_required: bool = Field(default=False, sa_column_kwargs={"server_default": false()})
    review_status: str | None = Field(default=None, index=True)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    # The assignee's answer to an assignment: Pending, Accepted or Declined.
    assignment_status: str | None = Field(default=None, index=True)
    assignment_responded_at: datetime | None = None
    assignment_note: str | None = None


class RiskTable(AuditMixin, table=True):
    __tablename__ = "risks"

    risk_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    risk_name: str
    probability: int
    impact: int
    status: str
    mitigation_owner: str | None = None
    mitigation_owner_user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    mitigation_status: str | None = None
    due_date: date


class DependencyTable(AuditMixin, table=True):
    __tablename__ = "dependencies"
    __table_args__ = (
        CheckConstraint(
            "predecessor_type IN ('Task', 'Milestone', 'Supplier', 'External', 'Customer')",
            name="ck_dependencies_predecessor_type",
        ),
        CheckConstraint(
            "successor_type IN ('Task', 'Milestone')",
            name="ck_dependencies_successor_type",
        ),
        CheckConstraint(
            "relationship_type IS NULL OR relationship_type IN "
            "('Finish-to-Start', 'Start-to-Start', 'Finish-to-Finish', 'Start-to-Finish')",
            name="ck_dependencies_relationship_type",
        ),
        CheckConstraint(
            "(relationship_type IS NULL AND lag_days IS NULL) OR "
            "(relationship_type IS NOT NULL AND lag_days IS NOT NULL)",
            name="ck_dependencies_relationship_metadata",
        ),
        CheckConstraint(
            "predecessor_type != successor_type OR predecessor_id != successor_id",
            name="ck_dependencies_not_self_referencing",
        ),
        CheckConstraint("delay_days >= 0", name="ck_dependencies_delay_days"),
        UniqueConstraint(
            "project_id",
            "predecessor_type",
            "predecessor_id",
            "successor_type",
            "successor_id",
            name="uq_dependencies_project_edge",
        ),
    )

    dependency_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    predecessor_type: str
    predecessor_id: str
    successor_type: str
    successor_id: str
    dependency_name: str
    relationship_type: str | None = None
    lag_days: int | None = None
    status: str
    delay_days: int
    criticality: str


class ActionTable(AuditMixin, table=True):
    __tablename__ = "actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Open', 'In Progress', 'Blocked', 'Complete', 'Cancelled')",
            name="ck_actions_status",
        ),
    )

    action_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    action_description: str
    owner: str | None = None
    owner_user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    due_date: date
    status: str
    priority: str
    source_reference: str | None = None


class IssueTable(AuditMixin, table=True):
    """A present delivery problem requiring owned resolution."""

    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Open', 'In Progress', 'Resolved', 'Closed')",
            name="ck_issues_status",
        ),
    )

    issue_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    title: str
    description: str
    severity: str
    owner: str | None = None
    owner_user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    status: str = Field(default=IssueStatus.OPEN.value, index=True)
    raised_date: date
    target_resolution_date: date | None = None
    resolution_summary: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    source_reference: str | None = None


class AssumptionTable(AuditMixin, table=True):
    """A project assumption whose validity must be reviewed explicitly."""

    __tablename__ = "assumptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Proposed', 'Validated', 'Invalidated', 'Retired')",
            name="ck_assumptions_status",
        ),
    )

    assumption_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    assumption_text: str
    owner: str
    owner_user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    status: str = Field(default=AssumptionStatus.PROPOSED.value, index=True)
    validation_due_date: date | None = None
    impact_if_false: str | None = None
    validation_evidence: str | None = None
    validated_by: str | None = None
    validated_at: datetime | None = None
    source_reference: str | None = None


class ResourceTable(AuditMixin, table=True):
    __tablename__ = "resources"

    resource_id: str = Field(primary_key=True)
    resource_name: str
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    allocated_hours: int
    capacity_hours: int
    week_start_date: date


class RequirementTable(AuditMixin, table=True):
    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id",
            "project_id",
            name="uq_requirements_id_project",
        ),
    )

    requirement_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    requirement_text: str
    requirement_type: str
    priority: str
    status: str
    owner: str | None = None
    last_updated_date: date | None = None


class TestCaseTable(AuditMixin, table=True):
    __tablename__ = "test_cases"
    __test__ = False

    test_case_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    test_case_name: str
    status: str
    owner: str | None = None
    verification_evidence: str | None = None
    last_updated_date: date | None = None


class TraceLinkTable(AuditMixin, table=True):
    __tablename__ = "trace_links"

    trace_link_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    source_type: str
    source_id: str = Field(index=True)
    target_type: str
    target_id: str = Field(index=True)
    link_type: str


class ChangeRequestTable(AuditMixin, table=True):
    __tablename__ = "change_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["requirement_id", "project_id"],
            ["requirements.requirement_id", "requirements.project_id"],
            name="fk_change_requests_requirement_project",
        ),
    )

    change_request_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    requirement_id: str = Field(index=True)
    change_description: str
    reason: str
    priority: str
    status: str
    requested_by: str | None = None
    requested_date: date


class DecisionTable(AuditMixin, table=True):
    """A recorded delivery decision, its reasoning and what it affects.

    Decisions are kept as first-class records because the reasoning behind a delivery choice is
    routinely lost once the meeting ends. Every related identifier is optional: a decision is
    worth recording even before it is linked to anything.
    """

    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Proposed', 'Approved', 'Rejected', 'Superseded')",
            name="ck_decisions_status",
        ),
    )

    decision_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    title: str
    description: str
    category: str
    decision_date: date
    owner: str
    status: str = Field(index=True)
    rationale: str | None = None
    delivery_impact: str | None = None
    related_milestone_id: str | None = None
    related_risk_id: str | None = None
    related_change_request_id: str | None = None
    related_requirement_id: str | None = None
    approver: str | None = None
    approval_date: date | None = None
    notes: str | None = None


class MeetingNoteTable(AuditMixin, table=True):
    """Raw notes from a delivery meeting, kept as they were written.

    Only surrounding whitespace is trimmed; the wording and the line breaks are left alone.
    Everything EPOS reads out of a note is derived on request, so the original is never rewritten
    and a reader can always check a proposal against the line it came from.
    """

    __tablename__ = "meeting_notes"

    note_id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    title: str
    meeting_date: date
    attendees: str | None = None
    body: str


PROJECT_OWNED_AUDIT_TABLES: tuple[type[SQLModel], ...] = (
    GateCriterionTable,
    GateTable,
    TaskTable,
    DeliverableTable,
    WorkPackageTable,
    MilestoneTable,
    RiskTable,
    DependencyTable,
    ActionTable,
    IssueTable,
    AssumptionTable,
    ResourceTable,
    RequirementTable,
    TestCaseTable,
    TraceLinkTable,
    ChangeRequestTable,
    DecisionTable,
    MeetingNoteTable,
)

# Every record whose identifier can be cited as evidence, with that identifier's column. One
# identifier names one record across all of them, so a citation is never ambiguous.
SOURCE_RECORD_TABLES: tuple[tuple[type[SQLModel], str], ...] = (
    (ProjectTable, "project_id"),
    (WorkPackageTable, "work_package_id"),
    (DeliverableTable, "deliverable_id"),
    (MilestoneTable, "milestone_id"),
    (GateTable, "gate_id"),
    (GateCriterionTable, "criterion_id"),
    (GateReviewTable, "review_id"),
    (TaskTable, "task_id"),
    (RiskTable, "risk_id"),
    (DependencyTable, "dependency_id"),
    (ActionTable, "action_id"),
    (IssueTable, "issue_id"),
    (AssumptionTable, "assumption_id"),
    (ResourceTable, "resource_id"),
    (RequirementTable, "requirement_id"),
    (TestCaseTable, "test_case_id"),
    (TraceLinkTable, "trace_link_id"),
    (ChangeRequestTable, "change_request_id"),
    (DecisionTable, "decision_id"),
    (MeetingNoteTable, "note_id"),
)


class ActivityEventTable(SQLModel, table=True):
    """Append-only audit trail of every write performed through the API."""

    __tablename__ = "activity_events"

    id: int | None = Field(default=None, primary_key=True)
    occurred_at: datetime = Field(default_factory=_utc_now, index=True)
    action: str
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    project_id: str | None = Field(default=None, index=True)
    summary: str
    detail: str | None = None
    changes_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    actor_email: str | None = Field(default=None, index=True)
    actor_name: str | None = None


class UserTable(SQLModel, table=True):
    """A person who can sign in.

    ``password_hash`` is an Argon2id digest. It is never exposed by any response model.
    """

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    full_name: str
    password_hash: str
    role: Role = Field(default=DEFAULT_ROLE)
    job_title: str | None = None
    is_active: bool = Field(default=True)
    # Set by an administrator reset: the temporary password only admits a password change.
    password_change_required: bool = Field(
        default=False, sa_column_kwargs={"server_default": false()}
    )
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    last_login_at: datetime | None = Field(default=None)


class NotificationTable(SQLModel, table=True):
    """Something one person should look at, with a link to the record it concerns."""

    __tablename__ = "notifications"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str
    title: str
    detail: str | None = None
    project_id: str | None = Field(default=None, index=True)
    entity_type: str | None = None
    entity_id: str | None = None
    actor_name: str | None = None
    created_at: datetime = Field(default_factory=_utc_now, index=True)
    read_at: datetime | None = Field(default=None, index=True)


class UserSessionTable(SQLModel, table=True):
    """One signed-in browser or client, so it can be listed and ended on its own."""

    __tablename__ = "user_sessions"

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=_utc_now)
    last_seen_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime
    revoked_at: datetime | None = Field(default=None, index=True)
    user_agent: str | None = None


class InvitationTable(SQLModel, table=True):
    """A one-time, email-bound invitation. Only a hash of the code is stored."""

    __tablename__ = "invitations"

    id: int | None = Field(default=None, primary_key=True)
    code_hash: str = Field(unique=True, index=True)
    email: str = Field(index=True)
    # Stored as the role's value so no second database enum type is needed.
    role: str = Field(default=DEFAULT_ROLE.value)
    created_by: str
    created_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None


class RateLimitEventTable(SQLModel, table=True):
    """One counted request, shared by every application instance using this database."""

    __tablename__ = "rate_limit_events"

    id: int | None = Field(default=None, primary_key=True)
    bucket: str = Field(index=True)
    key_hash: str = Field(index=True)
    occurred_at: datetime = Field(default_factory=_utc_now, index=True)


class ProjectMemberTable(SQLModel, table=True):
    """Assignment of a user to a project, with the part they play on it."""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.project_id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    project_role: str = Field(default="Contributor")
    created_at: datetime = Field(default_factory=_utc_now)


class ConversationTable(SQLModel, table=True):
    """An Ask EPOS conversation belonging to one user."""

    __tablename__ = "conversations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str
    project_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class ConversationMessageTable(SQLModel, table=True):
    """One turn in a conversation.

    ``evidence_json`` holds the deterministic evidence package that supported an answer, so the
    source drawer can be reopened later without recalculating or re-asking the model.
    """

    __tablename__ = "conversation_messages"

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversations.id", index=True)
    role: str
    content: str
    matched_intent: str | None = None
    status: str | None = None
    source_ids_json: str | None = None
    evidence_json: str | None = None
    answer_json: str | None = None
    context_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now, index=True)


class SavedViewTable(SQLModel, table=True):
    """A user's saved filter and column configuration for a table view."""

    __tablename__ = "saved_views"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    surface: str = Field(index=True)
    name: str
    configuration_json: str
    created_at: datetime = Field(default_factory=_utc_now)


class SavedScenarioTable(SQLModel, table=True):
    """A recorded what-if run, kept so a comparison can be revisited."""

    __tablename__ = "saved_scenarios"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    dependency_id: str = Field(index=True)
    additional_delay_days: int
    as_of_date: date
    result_json: str
    created_at: datetime = Field(default_factory=_utc_now, index=True)
