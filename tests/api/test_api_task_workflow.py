"""Account-based assignment and completion through the governed API."""

from collections.abc import Callable
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api import clock
from api.models import ProjectMemberTable, UserTable
from api.security.permissions import Role
from tests.api.conftest import TEST_ACCOUNTS, TEST_PASSWORD, url


def _engineer_id(engine: Engine) -> int:
    with Session(engine) as session:
        user = session.exec(select(UserTable).where(UserTable.role == Role.ENGINEER)).one()
        assert user.id is not None
        return user.id


def _new_task(client: TestClient, owner_id: int | None = None) -> dict:
    response = client.post(
        url("/tasks"),
        json={
            "project_id": "P-002",
            "milestone_id": "M-202",
            "task_name": "Recorded synthetic validation work",
            "owner_user_id": owner_id,
            "status": "Not Started",
            "planned_end_date": "2026-10-15",
            "forecast_end_date": "2026-10-15",
            "completion_percent": 0,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_pmo_assigns_account_and_engineer_completes_task(
    sign_in: Callable[[Role], TestClient], engineer_client: TestClient, engine: Engine
) -> None:
    pmo = sign_in(Role.PMO_ANALYST)
    owner_id = _engineer_id(engine)
    task = _new_task(pmo, owner_id)
    assert task["task_id"].startswith("T-")
    assert task["owner_user_id"] == owner_id
    assert task["owner"] == "Test Engineer"

    completion = engineer_client.post(
        url(f"/tasks/{task['task_id']}/complete"), json={"row_version": task["row_version"]}
    )
    assert completion.status_code == 200, completion.text
    completed = completion.json()
    assert completed["status"] == "Complete"
    assert completed["completion_percent"] == 100
    assert completed["is_blocked"] is False
    assert completed["actual_start_date"] is None
    assert completed["actual_end_date"] is None
    assert completed["last_updated_date"] == clock.utc_today().isoformat()
    assert pmo.get(url(f"/tasks/{task['task_id']}")).json() == completed
    events = pmo.get(url("/activity"), params={"project_id": "P-002"}).json()
    event = next(row for row in events if row["entity_id"] == task["task_id"])
    assert event["action"] == "completed"
    assert event["actor_name"] == "Test Engineer"
    assert {change["field"] for change in event["changes"]} >= {"status", "completion_percent"}


def test_reassignment_and_unassignment_are_account_based(
    client: TestClient, engine: Engine
) -> None:
    task = _new_task(client)
    assigned = client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"owner_user_id": _engineer_id(engine), "row_version": task["row_version"]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["owner"] == "Test Engineer"
    cleared = client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"owner_user_id": None, "row_version": assigned.json()["row_version"]},
    )
    assert cleared.status_code == 200
    assert cleared.json()["owner_user_id"] is None
    assert cleared.json()["owner"] is None


@pytest.mark.parametrize("invalid_owner", ["missing", "inactive", "nonmember", "read_only"])
def test_invalid_assignment_is_rejected(
    client: TestClient, engine: Engine, invalid_owner: str
) -> None:
    owner_id = _engineer_id(engine)
    with Session(engine) as session:
        user = session.get(UserTable, owner_id)
        assert user is not None
        if invalid_owner == "inactive":
            user.is_active = False
        elif invalid_owner == "read_only":
            user.role = Role.EXECUTIVE
        elif invalid_owner == "nonmember":
            member = session.exec(
                select(ProjectMemberTable).where(ProjectMemberTable.user_id == owner_id)
            ).one()
            session.delete(member)
        session.add(user)
        session.commit()
    task = _new_task(client)
    response = client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={
            "owner_user_id": 999999 if invalid_owner == "missing" else owner_id,
            "row_version": task["row_version"],
        },
    )
    assert response.status_code == 422
    assert client.get(url(f"/tasks/{task['task_id']}")).json()["owner_user_id"] is None


def test_duplicate_names_do_not_make_account_assignment_ambiguous(
    client: TestClient, engine: Engine, test_password_hash: str
) -> None:
    owner_id = _engineer_id(engine)
    with Session(engine) as session:
        other = UserTable(
            email="other-engineer@test.example.com",
            full_name="Test Engineer",
            password_hash=test_password_hash,
            role=Role.ENGINEER,
        )
        session.add(other)
        session.flush()
        session.add(ProjectMemberTable(project_id="P-002", user_id=other.id or 0))
        session.commit()
    assert _new_task(client, owner_id)["owner_user_id"] == owner_id


def test_engineer_cannot_reassign_or_complete_other_work(
    client: TestClient, engineer_client: TestClient, engine: Engine
) -> None:
    task = _new_task(client)
    assert (
        engineer_client.post(
            url(f"/tasks/{task['task_id']}/complete"), json={"row_version": task["row_version"]}
        ).status_code
        == 403
    )
    assigned = _new_task(client, _engineer_id(engine))
    assert (
        engineer_client.patch(
            url(f"/tasks/{assigned['task_id']}"),
            json={"owner_user_id": None, "row_version": assigned["row_version"]},
        ).status_code
        == 403
    )


def test_completion_rejects_stale_version(client: TestClient, engine: Engine) -> None:
    task = _new_task(client, _engineer_id(engine))
    endpoint = url(f"/tasks/{task['task_id']}/complete")
    assert client.post(endpoint, json={"row_version": task["row_version"]}).status_code == 200
    assert client.post(endpoint, json={"row_version": task["row_version"]}).status_code == 409


def test_progress_and_completion_are_consistent(client: TestClient, engine: Engine) -> None:
    task = _new_task(client, _engineer_id(engine))
    blocked = client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={
            "is_blocked": True,
            "progress_note": "Test rig unavailable.",
            "row_version": task["row_version"],
        },
    ).json()
    assert blocked["status"] == "Blocked"
    completed = client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"completion_percent": 100, "row_version": blocked["row_version"]},
    ).json()
    assert completed["status"] == "Complete"
    assert completed["is_blocked"] is False
    reopened = client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"status": "In Progress", "row_version": completed["row_version"]},
    ).json()
    assert reopened["status"] == "In Progress"
    assert reopened["completion_percent"] == 0


def test_member_picker_and_assignment_options_are_permission_scoped(
    sign_in: Callable[[Role], TestClient], engineer_client: TestClient
) -> None:
    lead = sign_in(Role.ENGINEERING_LEAD)
    options = lead.get(url("/projects/P-002/assignees"))
    assert options.status_code == 200, options.text
    assert "Test Engineer" in {row["full_name"] for row in options.json()}
    assert "Test Requirements Manager" not in {row["full_name"] for row in options.json()}
    assert lead.get(url("/projects/P-002/member-candidates")).status_code == 403
    assert lead.get(url("/projects/P-001/assignees")).status_code == 404
    assert engineer_client.get(url("/projects/P-002/assignees")).status_code == 403


def test_pmo_can_add_registered_member_by_account_id(
    sign_in: Callable[[Role], TestClient], engine: Engine
) -> None:
    pmo = sign_in(Role.PMO_ANALYST)
    owner_id = _engineer_id(engine)
    options = pmo.get(url("/projects/P-007/member-candidates"))
    assert options.status_code == 200, options.text
    candidate = next(row for row in options.json() if row["user_id"] == owner_id)
    assert set(candidate) == {"user_id", "email", "full_name", "workspace_role", "role_label"}
    response = pmo.post(
        url("/projects/P-007/members"),
        json={"user_id": owner_id, "project_role": "Contributor"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_active"] is True
    assert owner_id not in {
        row["user_id"] for row in pmo.get(url("/projects/P-007/member-candidates")).json()
    }


def test_reassign_open_tasks_before_removing_membership(client: TestClient, engine: Engine) -> None:
    owner_id = _engineer_id(engine)
    task = _new_task(client, owner_id)
    endpoint = url(f"/projects/P-002/members/{owner_id}")
    response = client.delete(endpoint)
    assert response.status_code == 409
    assert task["task_id"] in response.json()["detail"]


def test_empty_workspace_supports_full_assignment_journey(
    empty_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = date(2026, 9, 22)
    monkeypatch.setattr(clock, "utc_today", lambda: today)
    assert empty_client.get(url("/projects")).json() == []
    login = empty_client.post(
        url("/auth/login"),
        json={"email": TEST_ACCOUNTS[Role.PMO_ANALYST][0], "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    pmo_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    registration = empty_client.post(
        url("/auth/register"),
        json={
            "email": "new-engineer@test.example.com",
            "full_name": "New Synthetic Engineer",
            "password": TEST_PASSWORD,
        },
    )
    assert registration.status_code == 201, registration.text
    engineer = registration.json()["user"]
    engineer_headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    assert engineer["role"] == "engineer"
    created = empty_client.post(
        url("/projects"),
        headers=pmo_headers,
        json={
            "project_id": "P-WORKFLOW-EMPTY",
            "project_name": "New synthetic delivery programme",
            "domain": "Synthetic validation",
            "project_manager": "Test PMO Analyst",
            "start_date": "2026-09-01",
            "project_phase": "Planning",
            "business_priority": "Medium",
        },
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["project_id"]
    milestone = empty_client.post(
        url("/milestones"),
        headers=pmo_headers,
        json={
            "project_id": project_id,
            "milestone_name": "Synthetic validation checkpoint",
            "baseline_date": "2026-10-15",
            "forecast_date": "2026-10-15",
            "status": "Not Started",
            "criticality": "Medium",
        },
    )
    assert milestone.status_code == 201, milestone.text
    assert milestone.json()["milestone_id"].startswith("M-")
    assert empty_client.get(url("/projects"), headers=engineer_headers).json() == []
    member = empty_client.post(
        url(f"/projects/{project_id}/members"),
        headers=pmo_headers,
        json={"user_id": engineer["id"], "project_role": "Contributor"},
    )
    assert member.status_code == 201, member.text
    task = empty_client.post(
        url("/tasks"),
        headers=pmo_headers,
        json={
            "project_id": project_id,
            "milestone_id": milestone.json()["milestone_id"],
            "task_name": "Newly assigned synthetic validation",
            "owner_user_id": engineer["id"],
            "status": "Not Started",
            "completion_percent": 0,
            "planned_end_date": "2026-10-15",
            "forecast_end_date": "2026-10-15",
        },
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["task_id"]
    project_dashboard = empty_client.get(
        url(f"/analytics/projects/{project_id}"), headers=pmo_headers
    )
    assert project_dashboard.status_code == 200, project_dashboard.text
    assert project_dashboard.json()["health"]["as_of_date"] == today.isoformat()
    portfolio_dashboard = empty_client.get(url("/analytics/portfolio"), headers=pmo_headers)
    assert portfolio_dashboard.status_code == 200, portfolio_dashboard.text
    assert portfolio_dashboard.json()["as_of_date"] == today.isoformat()
    assert empty_client.get(url("/health")).json()["analysis_date"] == today.isoformat()
    historical = empty_client.get(
        url(f"/analytics/projects/{project_id}"),
        headers=pmo_headers,
        params={"as_of_date": "2026-08-25"},
    )
    assert historical.status_code == 422
    assigned = empty_client.get(url("/tasks"), headers=engineer_headers).json()
    assert [row["task_id"] for row in assigned] == [task_id]
    assert assigned[0]["owner_user_id"] == engineer["id"]
    completed = empty_client.post(
        url(f"/tasks/{task_id}/complete"),
        headers=engineer_headers,
        json={"row_version": assigned[0]["row_version"]},
    )
    assert completed.status_code == 200, completed.text
    manager_view = empty_client.get(url(f"/projects/{project_id}/tasks"), headers=pmo_headers)
    assert manager_view.json()[0]["status"] == "Complete"
    project_dashboard = empty_client.get(
        url(f"/analytics/projects/{project_id}"), headers=pmo_headers
    )
    assert project_dashboard.status_code == 200, project_dashboard.text
    events = empty_client.get(url("/activity"), headers=pmo_headers).json()
    assert any(
        event["action"] == "completed"
        and event["entity_id"] == task_id
        and event["actor_name"] == engineer["full_name"]
        for event in events
    )
    removed = empty_client.delete(
        url(f"/projects/{project_id}/members/{engineer['id']}"), headers=pmo_headers
    )
    assert removed.status_code == 204
    assert empty_client.get(url(f"/tasks/{task_id}"), headers=engineer_headers).status_code == 404
