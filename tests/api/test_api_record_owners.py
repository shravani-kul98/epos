"""Owner accounts on governed records, assignment answers and separation of duties."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.models import UserTable
from api.security.permissions import Role
from tests.api.conftest import TEST_ACCOUNTS, url


def _user_id(engine: Engine, role: Role) -> int:
    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == TEST_ACCOUNTS[role][0])
        ).one()
        return user.id or 0


def _notifications(client: TestClient, kind: str) -> list[dict]:
    return [item for item in client.get(url("/notifications")).json() if item["kind"] == kind]


def _task(client: TestClient, owner_id: int | None) -> dict:
    response = client.post(
        url("/tasks"),
        json={
            "project_id": "P-002",
            "milestone_id": "M-202",
            "task_name": "Synthetic assignment fixture",
            "owner_user_id": owner_id,
            "status": "Not Started",
            "planned_end_date": "2026-10-15",
            "forecast_end_date": "2026-10-15",
            "completion_percent": 0,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _answer(client: TestClient, task: dict, decision: str, note: str | None = None):
    body: dict[str, object] = {"decision": decision, "row_version": task["row_version"]}
    if note is not None:
        body["note"] = note
    return client.post(url(f"/tasks/{task['task_id']}/assignment"), json=body)


class TestAssignmentAnswers:
    def test_new_work_waits_for_the_assignee_to_accept(
        self, pm_client: TestClient, engineer_client: TestClient, engine: Engine
    ) -> None:
        task = _task(pm_client, _user_id(engine, Role.ENGINEER))
        assert task["assignment_status"] == "Pending"
        assert [n["read_at"] for n in _notifications(engineer_client, "task_assigned")] == [None]

        accepted = _answer(engineer_client, task, "accept")

        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["assignment_status"] == "Accepted"
        assert accepted.json()["assignment_responded_at"] is not None
        assert all(n["read_at"] for n in _notifications(engineer_client, "task_assigned"))
        assert len(_notifications(pm_client, "assignment_accepted")) == 1

    def test_declining_needs_a_reason_and_returns_the_work_to_the_manager(
        self, pm_client: TestClient, engineer_client: TestClient, engine: Engine
    ) -> None:
        task = _task(pm_client, _user_id(engine, Role.ENGINEER))
        assert _answer(engineer_client, task, "decline").status_code == 422

        declined = _answer(engineer_client, task, "decline", "On leave for the whole window.")

        assert declined.status_code == 200, declined.text
        assert declined.json()["assignment_status"] == "Declined"
        assert declined.json()["owner_user_id"] is None
        assert declined.json()["assignment_note"] == "On leave for the whole window."
        [notice] = _notifications(pm_client, "assignment_declined")
        assert notice["detail"] == "On leave for the whole window."

    def test_only_the_assignee_answers_and_only_once(
        self, pm_client: TestClient, engineer_client: TestClient, engine: Engine
    ) -> None:
        task = _task(pm_client, _user_id(engine, Role.ENGINEER))
        assert _answer(pm_client, task, "accept").status_code == 403

        accepted = _answer(engineer_client, task, "accept").json()
        assert _answer(engineer_client, accepted, "accept").status_code == 409

    def test_work_you_assign_to_yourself_is_already_accepted(
        self, pm_client: TestClient, engine: Engine
    ) -> None:
        task = _task(pm_client, _user_id(engine, Role.PROJECT_MANAGER))
        assert task["assignment_status"] == "Accepted"

    def test_reassignment_asks_the_new_assignee_again(
        self, pm_client: TestClient, engineer_client: TestClient, engine: Engine
    ) -> None:
        task = _task(pm_client, _user_id(engine, Role.ENGINEER))
        accepted = _answer(engineer_client, task, "accept").json()
        reassigned = pm_client.patch(
            url(f"/tasks/{task['task_id']}"),
            json={
                "owner_user_id": _user_id(engine, Role.PROJECT_MANAGER),
                "row_version": accepted["row_version"],
            },
        )
        assert reassigned.status_code == 200, reassigned.text
        assert reassigned.json()["assignment_status"] == "Accepted"


class TestOwnerAccounts:
    RISK = {
        "project_id": "P-002",
        "risk_name": "Synthetic supplier risk",
        "probability": 4,
        "impact": 5,
        "status": "Open",
        "mitigation_owner": "Placeholder name",
        "mitigation_status": "In Progress",
        "due_date": "2026-10-01",
    }

    def test_a_linked_risk_owner_is_named_from_the_account_and_told(
        self, pm_client: TestClient, engineer_client: TestClient, engine: Engine
    ) -> None:
        engineer_id = _user_id(engine, Role.ENGINEER)
        created = pm_client.post(
            url("/risks"), json=self.RISK | {"mitigation_owner_user_id": engineer_id}
        )

        assert created.status_code == 201, created.text
        risk = created.json()
        assert risk["mitigation_owner_user_id"] == engineer_id
        assert risk["mitigation_owner"] == TEST_ACCOUNTS[Role.ENGINEER][1]
        [notice] = _notifications(engineer_client, "risk_assigned")
        assert notice["entity_id"] == risk["risk_id"]

    def test_an_owner_must_be_able_to_see_the_project(
        self, pm_client: TestClient, engine: Engine
    ) -> None:
        # The engineer is a member of P-002 only.
        response = pm_client.post(
            url("/risks"),
            json=self.RISK
            | {"project_id": "P-007", "mitigation_owner_user_id": _user_id(engine, Role.ENGINEER)},
        )
        assert response.status_code == 422
        assert "can access this project" in response.json()["detail"]

    def test_retyping_the_owner_name_drops_the_account_link(
        self, pm_client: TestClient, engine: Engine
    ) -> None:
        risk = pm_client.post(
            url("/risks"),
            json=self.RISK | {"mitigation_owner_user_id": _user_id(engine, Role.ENGINEER)},
        ).json()
        renamed = pm_client.patch(
            url(f"/risks/{risk['risk_id']}"),
            json={"mitigation_owner": "External supplier", "row_version": risk["row_version"]},
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["mitigation_owner_user_id"] is None
        assert renamed.json()["mitigation_owner"] == "External supplier"

    def test_issue_and_assumption_owners_are_told_too(
        self, pm_client: TestClient, engineer_client: TestClient, engine: Engine
    ) -> None:
        engineer_id = _user_id(engine, Role.ENGINEER)
        issue = pm_client.post(
            url("/issues"),
            json={
                "project_id": "P-002",
                "title": "Qualification fixture unavailable",
                "description": "The validation team cannot complete the planned test sequence.",
                "severity": "High",
                "owner": "Placeholder name",
                "owner_user_id": engineer_id,
                "raised_date": "2026-08-27",
                "target_resolution_date": "2026-09-04",
            },
        )
        assumption = pm_client.post(
            url("/assumptions"),
            json={
                "project_id": "P-002",
                "assumption_text": "The supplier fixture arrives before validation starts.",
                "owner": "Placeholder name",
                "owner_user_id": engineer_id,
                "validation_due_date": "2026-09-01",
                "impact_if_false": "Validation would move beyond the planned gate.",
            },
        )
        assert issue.status_code == 201, issue.text
        assert assumption.status_code == 201, assumption.text
        assert issue.json()["owner"] == TEST_ACCOUNTS[Role.ENGINEER][1]
        assert len(_notifications(engineer_client, "issue_assigned")) == 1
        assert len(_notifications(engineer_client, "assumption_assigned")) == 1


class TestSeparationOfDuties:
    CHANGE = {
        "project_id": "P-002",
        "requirement_id": "REQ-2001",
        "change_description": "Tighten the thermal margin",
        "reason": "Separation-of-duties test",
        "priority": "High",
        "status": "Open",
        "requested_date": "2026-08-01",
    }

    def test_whoever_raised_a_change_cannot_decide_it(
        self, pm_client: TestClient, client: TestClient
    ) -> None:
        raised = pm_client.post(url("/change-requests"), json=self.CHANGE)
        assert raised.status_code == 201, raised.text
        change = raised.json()
        decision = {
            "decision": "Approved",
            "rationale": "Impact reviewed.",
            "row_version": change["row_version"],
        }

        own = pm_client.post(
            url(f"/change-requests/{change['change_request_id']}/decision"), json=decision
        )
        assert own.status_code == 409
        assert "another person" in own.json()["detail"]

        independent = client.post(
            url(f"/change-requests/{change['change_request_id']}/decision"), json=decision
        )
        assert independent.status_code == 200, independent.text


class TestLifecycleReasons:
    def test_starting_an_issue_needs_no_reason_but_resolving_it_does(
        self, pm_client: TestClient
    ) -> None:
        issue = pm_client.post(
            url("/issues"),
            json={
                "project_id": "P-002",
                "title": "Fixture calibration overdue",
                "description": "Calibration lapsed before the test window.",
                "severity": "Medium",
                "owner": "Test Project Manager",
                "raised_date": "2026-08-27",
                "target_resolution_date": "2026-09-04",
            },
        ).json()
        endpoint = url(f"/issues/{issue['issue_id']}/transition")

        started = pm_client.post(
            endpoint, json={"target_status": "In Progress", "row_version": issue["row_version"]}
        )
        assert started.status_code == 200, started.text

        resolving = pm_client.post(
            endpoint,
            json={"target_status": "Resolved", "row_version": started.json()["row_version"]},
        )
        assert resolving.status_code == 422


class TestServerAllocatedReferences:
    def test_a_meeting_note_without_an_identifier_gets_the_next_reference(
        self, pm_client: TestClient
    ) -> None:
        note = {
            "project_id": "P-002",
            "title": "Weekly delivery review",
            "meeting_date": "2026-08-20",
            "body": "Alex will confirm the supplier date by Friday.",
        }
        first = pm_client.post(url("/meeting-notes"), json=note)
        second = pm_client.post(url("/meeting-notes"), json=note)
        assert first.status_code == second.status_code == 201, first.text
        assert first.json()["note_id"] == "MN-P-002-001"
        assert second.json()["note_id"] == "MN-P-002-002"
