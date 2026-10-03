"""Authorization tests: what each role may and may not do through the API.

These are the tests that would catch a privilege escalation, so they assert against real requests
rather than against the permission table alone.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from api.models import (
    ChangeRequestTable,
    DecisionTable,
    MeetingNoteTable,
    ProjectMemberTable,
    TraceLinkTable,
    UserTable,
)
from api.security.permissions import Permission, Role
from api.security.project_scope import source_ids_are_authorized
from api.services import semantic_router
from tests.api.conftest import url

NEW_PROJECT = {
    "project_id": "P-950",
    "project_name": "Authorisation Probe",
    "domain": "Validation",
    "project_manager": "A. Engineer",
    "start_date": "2026-01-05",
    "project_phase": "Design",
    "business_priority": "High",
}

NEW_RISK = {
    "risk_id": "R-950",
    "project_id": "P-002",
    "risk_name": "Probe risk",
    "probability": 3,
    "impact": 3,
    "status": "Open",
    "due_date": "2026-10-01",
}

NEW_REQUIREMENT = {
    "requirement_id": "REQ-9500",
    "project_id": "P-002",
    "requirement_text": "The probe shall record its own result.",
    "requirement_type": "Functional",
    "priority": "High",
    "status": "Draft",
}


# ------------------------------------------------------------------ unauthenticated
@pytest.mark.parametrize(
    "path",
    [
        "/projects",
        "/tasks",
        "/risks",
        "/milestones",
        "/requirements",
        "/change-requests",
        "/activity",
        "/analytics/portfolio",
        "/analytics/alerts",
        "/analytics/traceability",
        "/scenarios/dependencies",
        "/copilot/questions",
        "/admin/users",
    ],
)
def test_every_read_requires_a_session(anonymous_client: TestClient, path: str) -> None:
    assert anonymous_client.get(url(path)).status_code == 401


def test_unauthenticated_create_is_refused(anonymous_client: TestClient) -> None:
    assert anonymous_client.post(url("/projects"), json=NEW_PROJECT).status_code == 401


def test_unauthenticated_update_is_refused(anonymous_client: TestClient) -> None:
    assert anonymous_client.patch(url("/projects/P-002"), json={"domain": "X"}).status_code == 401


def test_unauthenticated_delete_is_refused(anonymous_client: TestClient) -> None:
    assert (
        anonymous_client.delete(url("/projects/P-002"), params={"row_version": 1}).status_code
        == 401
    )


def test_unauthenticated_question_is_refused(anonymous_client: TestClient) -> None:
    assert anonymous_client.post(url("/copilot/ask"), json={"question": "Hi"}).status_code == 401


def test_health_check_stays_public(anonymous_client: TestClient) -> None:
    """Readiness must be observable without a session."""
    assert anonymous_client.get(url("/health")).status_code == 200


# ------------------------------------------------------------------ executive
def test_executive_can_read_the_portfolio(executive_client: TestClient) -> None:
    assert executive_client.get(url("/analytics/portfolio")).status_code == 200


def test_executive_can_ask_a_question(executive_client: TestClient) -> None:
    response = executive_client.post(
        url("/copilot/ask"), json={"question": "Which projects need attention?"}
    )
    assert response.status_code == 200


def test_executive_cannot_create_a_project(executive_client: TestClient) -> None:
    assert executive_client.post(url("/projects"), json=NEW_PROJECT).status_code == 403


def test_executive_cannot_edit_a_project(executive_client: TestClient) -> None:
    response = executive_client.patch(url("/projects/P-002"), json={"domain": "Changed"})
    assert response.status_code == 403


def test_executive_cannot_create_a_risk(executive_client: TestClient) -> None:
    assert executive_client.post(url("/risks"), json=NEW_RISK).status_code == 403


def test_executive_cannot_update_a_task(executive_client: TestClient, client: TestClient) -> None:
    task_id = client.get(url("/tasks")).json()[0]["task_id"]
    response = executive_client.patch(url(f"/tasks/{task_id}"), json={"completion_percent": 90})
    assert response.status_code == 403


def test_a_refused_write_changes_nothing(executive_client: TestClient, client: TestClient) -> None:
    before = client.get(url("/projects/P-002")).json()
    executive_client.patch(url("/projects/P-002"), json={"domain": "Changed"})
    assert client.get(url("/projects/P-002")).json() == before


def test_a_refused_write_leaves_no_activity(
    executive_client: TestClient, client: TestClient
) -> None:
    executive_client.post(url("/projects"), json=NEW_PROJECT)
    assert client.get(url("/activity")).json() == []


# ------------------------------------------------------------------ engineer
def _create_engineer_task(client: TestClient) -> dict:
    milestone = client.get(url("/projects/P-002/milestones")).json()[0]
    response = client.post(
        url("/tasks"),
        json={
            "task_id": "T-ENGINEER",
            "project_id": "P-002",
            "milestone_id": milestone["milestone_id"],
            "task_name": "Engineer-owned probe",
            "owner": "Test Engineer",
            "status": "In Progress",
            "planned_end_date": "2026-10-01",
            "forecast_end_date": "2026-10-01",
            "completion_percent": 0,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_engineer_cannot_update_another_owners_work(
    engineer_client: TestClient, client: TestClient
) -> None:
    task = client.get(url("/tasks"), params={"project_id": "P-002"}).json()[0]
    response = engineer_client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"completion_percent": 75, "row_version": task["row_version"]},
    )
    assert response.status_code == 403


def test_engineer_can_flag_a_blocker(engineer_client: TestClient, client: TestClient) -> None:
    task = _create_engineer_task(client)
    assert task["owner_user_id"] is not None
    response = engineer_client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={
            "is_blocked": True,
            "progress_note": "Waiting for the supplier samples.",
            "row_version": task["row_version"],
        },
    )
    assert response.status_code == 200


def test_a_blocker_needs_a_note(engineer_client: TestClient, client: TestClient) -> None:
    task = _create_engineer_task(client)
    response = engineer_client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"is_blocked": True, "row_version": task["row_version"]},
    )
    assert response.status_code == 422
    assert "what is blocking" in response.json()["detail"]


def test_engineer_cannot_change_structural_fields_on_their_task(
    engineer_client: TestClient, client: TestClient
) -> None:
    task = _create_engineer_task(client)

    response = engineer_client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"task_name": "Unauthorized rename", "row_version": task["row_version"]},
    )

    assert response.status_code == 403


def test_engineer_only_sees_projects_they_belong_to(engineer_client: TestClient) -> None:
    projects = engineer_client.get(url("/projects")).json()
    assert {project["project_id"] for project in projects} == {"P-002"}


def test_engineer_cannot_read_or_update_another_projects_task(
    engineer_client: TestClient, client: TestClient
) -> None:
    task = client.get(url("/tasks"), params={"project_id": "P-007"}).json()[0]
    assert engineer_client.get(url(f"/tasks/{task['task_id']}")).status_code == 404
    assert engineer_client.get(url("/projects/P-007/tasks")).status_code == 404
    response = engineer_client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"completion_percent": 75, "row_version": task["row_version"]},
    )
    assert response.status_code == 404


def test_engineer_analytics_are_limited_to_their_projects(
    engineer_client: TestClient,
) -> None:
    dashboard = engineer_client.get(url("/analytics/portfolio")).json()
    assert {project["project_id"] for project in dashboard["projects"]} == {"P-002"}


def test_engineer_cannot_read_another_projects_activity(
    engineer_client: TestClient, client: TestClient
) -> None:
    task = client.get(url("/tasks"), params={"project_id": "P-007"}).json()[0]
    client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"completion_percent": 75, "row_version": task["row_version"]},
    )
    assert engineer_client.get(url("/activity")).json() == []
    assert engineer_client.get(url("/activity"), params={"project_id": "P-007"}).status_code == 404


def test_engineer_search_cannot_return_another_project(
    engineer_client: TestClient,
) -> None:
    response = engineer_client.get(url("/search"), params={"q": "P-007"})
    assert response.status_code == 200
    assert response.json()["hits"] == []


def test_engineer_cannot_ask_in_another_project(engineer_client: TestClient) -> None:
    response = engineer_client.post(
        url("/copilot/ask"),
        json={"question": "What is happening?", "project_id": "P-007"},
    )
    assert response.status_code == 404


def test_project_withdrawal_revokes_membership_and_all_product_records(
    client: TestClient, engineer_client: TestClient, engine
) -> None:
    assert engineer_client.get(url("/change-requests/CR-018")).status_code == 200
    with Session(engine) as session:
        session.add(
            DecisionTable(
                decision_id="DEC-WITHDRAW",
                project_id="P-002",
                title="Withdrawal probe",
                description="Synthetic decision for cascade verification.",
                category="Delivery",
                decision_date=date(2026, 8, 25),
                owner="Test Engineer",
                status="Proposed",
            )
        )
        session.add(
            MeetingNoteTable(
                note_id="MN-WITHDRAW",
                project_id="P-002",
                title="Withdrawal probe",
                meeting_date=date(2026, 8, 25),
                body="Synthetic note for cascade verification.",
            )
        )
        session.commit()

    project = client.get(url("/projects/P-002")).json()
    assert (
        client.delete(
            url("/projects/P-002"), params={"row_version": project["row_version"]}
        ).status_code
        == 204
    )

    assert engineer_client.get(url("/change-requests/CR-018")).status_code == 404
    with Session(engine) as session:
        assert (
            session.exec(
                select(ProjectMemberTable).where(ProjectMemberTable.project_id == "P-002")
            ).all()
            == []
        )
        for table in (
            TraceLinkTable,
            ChangeRequestTable,
            DecisionTable,
            MeetingNoteTable,
        ):
            rows = session.exec(select(table).where(table.project_id == "P-002")).all()
            assert rows, table.__name__
            assert all(row.deleted_at is not None for row in rows), table.__name__


def test_lost_membership_revokes_saved_conversation_access(
    engineer_client: TestClient, engine
) -> None:
    created = engineer_client.post(
        url("/copilot/ask"),
        json={"question": "What is happening?", "project_id": "P-002"},
    )
    assert created.status_code == 200
    conversation_id = created.json()["conversation_id"]

    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == "engineer@test.example.com")
        ).one()
        membership = session.exec(
            select(ProjectMemberTable).where(
                ProjectMemberTable.project_id == "P-002",
                ProjectMemberTable.user_id == user.id,
            )
        ).one()
        session.delete(membership)
        session.commit()

    assert engineer_client.get(url("/copilot/conversations")).json() == []
    assert engineer_client.get(url(f"/copilot/conversations/{conversation_id}")).status_code == 404


def test_lost_membership_revokes_semantically_scoped_conversation_access(
    engineer_client: TestClient, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        semantic_router,
        "interpret",
        lambda *_args, **_kwargs: semantic_router.SemanticRoute(
            status="ok",
            intent="workspace_evidence",
            confidence="high",
            project_id="P-002",
            record_type="risk",
            status_filter="Archived",
        ),
    )
    created = engineer_client.post(
        url("/copilot/ask"), json={"question": "Show only archived risks"}
    )
    assert created.status_code == 200
    assert created.json()["source_ids"] == ["META-WORKSPACE-SELECTION"]
    conversation_id = created.json()["conversation_id"]
    assert engineer_client.get(url("/copilot/conversations")).json()[0]["project_id"] == "P-002"

    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == "engineer@test.example.com")
        ).one()
        membership = session.exec(
            select(ProjectMemberTable).where(
                ProjectMemberTable.project_id == "P-002",
                ProjectMemberTable.user_id == user.id,
            )
        ).one()
        session.delete(membership)
        session.commit()

    assert engineer_client.get(url("/copilot/conversations")).json() == []
    assert engineer_client.get(url(f"/copilot/conversations/{conversation_id}")).status_code == 404


def test_scope_reduction_revokes_portfolio_wide_conversation_access(
    executive_client: TestClient, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        semantic_router,
        "interpret",
        lambda *_args, **_kwargs: semantic_router.SemanticRoute(
            status="ok",
            intent="workspace_evidence",
            confidence="high",
            record_type="risk",
            status_filter="Impossible status",
        ),
    )
    created = executive_client.post(
        url("/copilot/ask"), json={"question": "Show only archived risks"}
    )
    assert created.status_code == 200
    assert created.json()["source_ids"] == ["META-WORKSPACE-SELECTION"]
    conversation_id = created.json()["conversation_id"]
    assert executive_client.get(url(f"/copilot/conversations/{conversation_id}")).status_code == 200

    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == "exec@test.example.com")
        ).one()
        user.role = Role.ENGINEER
        session.add(user)
        session.add(ProjectMemberTable(project_id="P-002", user_id=user.id or 0))
        session.commit()

    assert executive_client.get(url("/copilot/conversations")).json() == []
    assert executive_client.get(url(f"/copilot/conversations/{conversation_id}")).status_code == 404


def test_project_scoped_user_can_read_own_portfolio_wide_conversation(
    engineer_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        semantic_router,
        "interpret",
        lambda *_args, **_kwargs: semantic_router.SemanticRoute(
            status="ok",
            intent="workspace_evidence",
            confidence="high",
            record_type="risk",
            status_filter="Impossible status",
        ),
    )
    created = engineer_client.post(
        url("/copilot/ask"), json={"question": "Show only archived risks"}
    )

    assert created.status_code == 200
    conversation_id = created.json()["conversation_id"]
    assert engineer_client.get(url(f"/copilot/conversations/{conversation_id}")).status_code == 200


def test_unknown_source_ids_fail_closed(engine, engineer_client: TestClient) -> None:
    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == "engineer@test.example.com")
        ).one()
        assert not source_ids_are_authorized(session, user, {"UNKNOWN-SOURCE-ID"})


def test_engineer_cannot_create_a_task(engineer_client: TestClient) -> None:
    payload = {
        "task_id": "T-950",
        "project_id": "P-002",
        "milestone_id": "M-2001",
        "task_name": "Probe task",
        "status": "In Progress",
        "planned_end_date": "2026-10-01",
        "forecast_end_date": "2026-10-05",
        "completion_percent": 0,
    }
    assert engineer_client.post(url("/tasks"), json=payload).status_code == 403


def test_engineer_cannot_delete_a_task(engineer_client: TestClient, client: TestClient) -> None:
    task = client.get(url("/tasks")).json()[0]
    assert (
        engineer_client.delete(
            url(f"/tasks/{task['task_id']}"), params={"row_version": task["row_version"]}
        ).status_code
        == 403
    )


def test_engineer_cannot_manage_risks(engineer_client: TestClient) -> None:
    assert engineer_client.post(url("/risks"), json=NEW_RISK).status_code == 403


def test_engineer_cannot_reach_administration(engineer_client: TestClient) -> None:
    assert engineer_client.get(url("/admin/users")).status_code == 403


def test_engineer_cannot_run_a_scenario(engineer_client: TestClient) -> None:
    response = engineer_client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-7002", "additional_delay_days": 10},
    )
    assert response.status_code == 403


# ------------------------------------------------------------------ requirements manager
def test_requirements_manager_can_create_a_requirement(
    requirements_client: TestClient,
) -> None:
    assert requirements_client.post(url("/requirements"), json=NEW_REQUIREMENT).status_code == 201


def test_requirements_manager_can_raise_a_change_request(
    requirements_client: TestClient,
) -> None:
    payload = {
        "change_request_id": "CR-950",
        "project_id": "P-002",
        "requirement_id": "REQ-2001",
        "change_description": "Probe change",
        "reason": "Authorisation test",
        "priority": "High",
        "status": "Open",
        "requested_date": "2026-08-01",
    }
    assert requirements_client.post(url("/change-requests"), json=payload).status_code in {201, 422}


def test_requirements_manager_cannot_decide_a_change(requirements_client: TestClient) -> None:
    """Raising a change and approving it are deliberately separate authorities."""
    response = requirements_client.post(
        url("/change-requests/CR-042/decision"),
        json={"decision": "Approved", "rationale": "Looks fine"},
    )
    assert response.status_code == 403


def test_requirements_manager_cannot_approve_a_change_through_patch(
    requirements_client: TestClient,
) -> None:
    response = requirements_client.patch(
        url("/change-requests/CR-042"),
        json={"status": "Approved"},
    )
    assert response.status_code == 422


def test_requirements_manager_cannot_create_a_project(requirements_client: TestClient) -> None:
    assert requirements_client.post(url("/projects"), json=NEW_PROJECT).status_code == 403


# ------------------------------------------------------------------ project manager
def test_project_manager_can_create_a_project(pm_client: TestClient) -> None:
    assert pm_client.post(url("/projects"), json=NEW_PROJECT).status_code == 201


def test_project_manager_can_decide_a_change(pm_client: TestClient) -> None:
    change = pm_client.get(url("/change-requests/CR-018")).json()
    response = pm_client.post(
        url("/change-requests/CR-018/decision"),
        json={
            "decision": "Approved",
            "rationale": "Impact reviewed and accepted.",
            "row_version": change["row_version"],
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Approved"


def test_project_manager_can_run_a_scenario(pm_client: TestClient) -> None:
    response = pm_client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-7002", "additional_delay_days": 30},
    )
    assert response.status_code == 200


def test_project_manager_cannot_delete_a_project(pm_client: TestClient) -> None:
    """Deletion is reserved to an administrator even for the project's own manager."""
    assert pm_client.delete(url("/projects/P-002"), params={"row_version": 1}).status_code == 403


def test_project_manager_cannot_manage_users(pm_client: TestClient) -> None:
    assert pm_client.get(url("/admin/users")).status_code == 403


def test_project_manager_administers_members_only_in_assigned_projects(
    pm_client: TestClient, engineer_client: TestClient
) -> None:
    assert pm_client.get(url("/projects/P-001/members")).status_code == 404
    assert engineer_client.get(url("/projects/P-002/members")).status_code == 403

    created = pm_client.post(
        url("/projects/P-007/members"),
        json={
            "user_email": "engineer@test.example.com",
            "project_role": "Integration engineer",
        },
    )
    assert created.status_code == 201
    member = created.json()
    assert member["workspace_role"] == "engineer"
    assert engineer_client.get(url("/projects/P-007")).status_code == 200

    duplicate = pm_client.post(
        url("/projects/P-007/members"),
        json={
            "user_email": "engineer@test.example.com",
            "project_role": "Integration engineer",
        },
    )
    assert duplicate.status_code == 409

    updated = pm_client.patch(
        url(f"/projects/P-007/members/{member['user_id']}"),
        json={"project_role": "Verification engineer"},
    )
    assert updated.status_code == 200
    assert updated.json()["project_role"] == "Verification engineer"

    removed = pm_client.delete(url(f"/projects/P-007/members/{member['user_id']}"))
    assert removed.status_code == 204
    assert engineer_client.get(url("/projects/P-007")).status_code == 404

    events = pm_client.get(url("/activity"), params={"project_id": "P-007"}).json()
    member_events = [event for event in events if event["entity_type"] == "Project member"]
    assert [event["action"] for event in member_events[:3]] == [
        "unassigned",
        "updated",
        "assigned",
    ]


# ------------------------------------------------------------------ administrator
def test_administrator_can_delete_a_project(client: TestClient) -> None:
    project = client.get(url("/projects/P-002")).json()
    assert (
        client.delete(
            url("/projects/P-002"), params={"row_version": project["row_version"]}
        ).status_code
        == 204
    )


def test_administrator_can_list_users(client: TestClient) -> None:
    users = client.get(url("/admin/users")).json()
    assert len(users) == len(Role)


def test_administrator_cannot_demote_themselves(client: TestClient) -> None:
    """A workspace must never be left with no administrator by accident."""
    me = client.get(url("/auth/me")).json()
    response = client.patch(url(f"/admin/users/{me['id']}/role"), json={"role": "engineer"})
    assert response.status_code == 409


def test_administrator_cannot_disable_themselves(client: TestClient) -> None:
    me = client.get(url("/auth/me")).json()
    response = client.patch(url(f"/admin/users/{me['id']}/active"), json={"is_active": False})
    assert response.status_code == 409


def test_role_change_is_recorded(client: TestClient) -> None:
    users = {user["role"]: user for user in client.get(url("/admin/users")).json()}
    target = users[Role.ENGINEER.value]
    client.patch(url(f"/admin/users/{target['id']}/role"), json={"role": "engineering_lead"})

    event = client.get(url("/activity")).json()[0]
    assert event["entity_type"] == "User"
    assert "Engineering Lead" in event["summary"]


def test_roles_endpoint_describes_every_role(client: TestClient) -> None:
    roles = client.get(url("/admin/roles")).json()
    assert {entry["role"] for entry in roles} == {role.value for role in Role}
    for entry in roles:
        assert entry["label"]
        assert Permission.PORTFOLIO_READ.value in entry["permissions"]


# ------------------------------------------------------------------ coverage of the surface
def test_no_mutating_route_is_left_unguarded(client: TestClient) -> None:
    """Every write must require either a permission or be an unauthenticated entry point."""
    paths = client.get("/openapi.json").json()["paths"]
    public = {url("/auth/register"), url("/auth/login")}
    mutating = {"post", "patch", "put", "delete"}

    unguarded: list[tuple[str, str]] = []
    for path, operations in paths.items():
        if path in public:
            continue
        for method, operation in operations.items():
            if method in mutating and not operation.get("security"):
                unguarded.append((path, method))
    assert unguarded == []
