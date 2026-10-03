"""Completion review, notifications, account-owned actions and verification upkeep."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.models import ProjectMemberTable, UserTable
from api.security.permissions import Role
from tests.api.conftest import TEST_ACCOUNTS, url


def _user_id(engine: Engine, role: Role) -> int:
    with Session(engine) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == TEST_ACCOUNTS[role][0])
        ).one()
        return user.id or 0


def _task(client: TestClient, owner_id: int, **extra: Any) -> dict:
    response = client.post(
        url("/tasks"),
        json={
            "project_id": "P-002",
            "milestone_id": "M-202",
            "task_name": "Synthetic review fixture",
            "owner_user_id": owner_id,
            "status": "Not Started",
            "planned_end_date": "2026-10-15",
            "forecast_end_date": "2026-10-15",
            "completion_percent": 0,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _kinds(client: TestClient) -> list[str]:
    return [item["kind"] for item in client.get(url("/notifications")).json()]


class TestCompletionReview:
    def _reported(self, pm: TestClient, engineer: TestClient, engine: Engine) -> dict:
        task = _task(pm, _user_id(engine, Role.ENGINEER), review_required=True)
        progress = engineer.patch(
            url(f"/tasks/{task['task_id']}"),
            json={"completion_percent": 60, "row_version": task["row_version"]},
        ).json()
        completed = engineer.post(
            url(f"/tasks/{task['task_id']}/complete"),
            json={
                "progress_note": "Calibration report filed.",
                "row_version": progress["row_version"],
            },
        )
        assert completed.status_code == 200, completed.text
        return completed.json()

    def test_completion_waits_for_review_and_managers_are_told(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        task = self._reported(pm_client, engineer_client, seeded_engine)

        assert task["status"] == "Complete"
        assert task["review_status"] == "Pending review"
        pending = pm_client.get(url("/tasks"), params={"review_status": "Pending review"}).json()
        assert [item["task_id"] for item in pending] == [task["task_id"]]
        assert "review_requested" in _kinds(pm_client)

    def test_returned_work_resumes_from_the_reported_progress(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        task = self._reported(pm_client, engineer_client, seeded_engine)

        returned = pm_client.post(
            url(f"/tasks/{task['task_id']}/review"),
            json={
                "decision": "return",
                "note": "Attach the signed report.",
                "row_version": task["row_version"],
            },
        )

        assert returned.status_code == 200, returned.text
        body = returned.json()
        assert (body["status"], body["completion_percent"]) == ("In Progress", 60)
        assert body["review_status"] == "Returned"
        assert body["review_note"] == "Attach the signed report."
        assert body["reviewed_by"] == TEST_ACCOUNTS[Role.PROJECT_MANAGER][1]
        assert "review_returned" in _kinds(engineer_client)
        history = engineer_client.get(url(f"/tasks/{task['task_id']}/progress")).json()
        assert history[0]["action"] == "review_returned"
        assert history[0]["note"] == "Attach the signed report."

    def test_accepting_records_the_reviewer(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        task = self._reported(pm_client, engineer_client, seeded_engine)

        accepted = pm_client.post(
            url(f"/tasks/{task['task_id']}/review"),
            json={"decision": "accept", "row_version": task["row_version"]},
        ).json()

        assert accepted["review_status"] == "Accepted"
        assert accepted["status"] == "Complete"
        assert "review_accepted" in _kinds(engineer_client)

    def test_returning_work_needs_a_reason(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        task = self._reported(pm_client, engineer_client, seeded_engine)

        response = pm_client.post(
            url(f"/tasks/{task['task_id']}/review"),
            json={"decision": "return", "row_version": task["row_version"]},
        )

        assert response.status_code == 422

    def test_only_a_pending_task_can_be_reviewed(
        self, pm_client: TestClient, seeded_engine: Engine
    ) -> None:
        task = _task(pm_client, _user_id(seeded_engine, Role.ENGINEER))

        response = pm_client.post(
            url(f"/tasks/{task['task_id']}/review"),
            json={"decision": "accept", "row_version": task["row_version"]},
        )

        assert response.status_code == 409

    def test_an_assignee_cannot_accept_their_own_work(
        self, pm_client: TestClient, sign_in, seeded_engine: Engine
    ) -> None:
        task = _task(pm_client, _user_id(seeded_engine, Role.PROJECT_MANAGER), review_required=True)
        done = pm_client.post(
            url(f"/tasks/{task['task_id']}/complete"), json={"row_version": task["row_version"]}
        ).json()

        own = pm_client.post(
            url(f"/tasks/{task['task_id']}/review"),
            json={"decision": "accept", "row_version": done["row_version"]},
        )
        other = sign_in(Role.ENGINEERING_LEAD).post(
            url(f"/tasks/{task['task_id']}/review"),
            json={"decision": "accept", "row_version": done["row_version"]},
        )

        assert own.status_code == 409
        assert other.status_code == 200

    def test_an_engineer_cannot_review_or_switch_review_off(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        task = self._reported(pm_client, engineer_client, seeded_engine)

        review = engineer_client.post(
            url(f"/tasks/{task['task_id']}/review"),
            json={"decision": "accept", "row_version": task["row_version"]},
        )
        toggle = engineer_client.patch(
            url(f"/tasks/{task['task_id']}"),
            json={"review_required": False, "row_version": task["row_version"]},
        )

        assert review.status_code == 403
        assert toggle.status_code == 403


class TestNotifications:
    def test_assignment_notifies_the_assignee_only(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        _task(pm_client, _user_id(seeded_engine, Role.ENGINEER))

        assert _kinds(engineer_client) == ["task_assigned"]
        assert "task_assigned" not in _kinds(pm_client)
        assert engineer_client.get(url("/notifications/summary")).json() == {"unread": 1}

    def test_a_blocker_reaches_the_projects_managers(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        task = _task(pm_client, _user_id(seeded_engine, Role.ENGINEER))

        engineer_client.patch(
            url(f"/tasks/{task['task_id']}"),
            json={
                "is_blocked": True,
                "progress_note": "Waiting on supplier data.",
                "row_version": task["row_version"],
            },
        )

        blocked = [
            item
            for item in pm_client.get(url("/notifications")).json()
            if item["kind"] == "task_blocked"
        ]
        assert blocked and blocked[0]["detail"] == "Waiting on supplier data."
        assert blocked[0]["entity_id"] == task["task_id"]

    def test_read_state_is_per_person(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        _task(pm_client, _user_id(seeded_engine, Role.ENGINEER))
        _task(pm_client, _user_id(seeded_engine, Role.ENGINEER))
        first = engineer_client.get(url("/notifications")).json()[0]

        assert engineer_client.post(url(f"/notifications/{first['id']}/read")).json()["read_at"]
        assert engineer_client.get(url("/notifications/summary")).json() == {"unread": 1}
        assert pm_client.post(url(f"/notifications/{first['id']}/read")).status_code == 404
        engineer_client.post(url("/notifications/read-all"))
        assert engineer_client.get(url("/notifications"), params={"unread_only": True}).json() == []

    def test_leaving_a_project_hides_its_notifications(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        _task(pm_client, _user_id(seeded_engine, Role.ENGINEER))
        with Session(seeded_engine) as session:
            membership = session.exec(
                select(ProjectMemberTable).where(
                    ProjectMemberTable.user_id == _user_id(seeded_engine, Role.ENGINEER)
                )
            ).one()
            session.delete(membership)
            session.commit()

        assert engineer_client.get(url("/notifications")).json() == []


class TestAccountOwnedActions:
    def _action(self, client: TestClient, owner_id: int | None) -> Any:
        return client.post(
            url("/actions"),
            json={
                "action_id": "A-9001",
                "project_id": "P-002",
                "action_description": "Confirm supplier emissions file",
                "owner_user_id": owner_id,
                "due_date": "2026-10-01",
                "priority": "High",
            },
        )

    def test_an_assigned_action_follows_the_account(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        response = self._action(pm_client, _user_id(seeded_engine, Role.ENGINEER))

        assert response.status_code == 201, response.text
        assert response.json()["owner"] == TEST_ACCOUNTS[Role.ENGINEER][1]
        assert response.json()["owner_user_id"] == _user_id(seeded_engine, Role.ENGINEER)
        assert "action_assigned" in _kinds(engineer_client)

    def test_the_assignee_can_move_their_own_action(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        action = self._action(pm_client, _user_id(seeded_engine, Role.ENGINEER)).json()

        moved = engineer_client.post(
            url("/actions/A-9001/transition"),
            json={
                "target_status": "In Progress",
                "rationale": "Started the check.",
                "row_version": action["row_version"],
            },
        )

        assert moved.status_code == 200, moved.text
        assert moved.json()["status"] == "In Progress"

    def test_nobody_else_without_authority_can_move_it(
        self, pm_client: TestClient, engineer_client: TestClient, seeded_engine: Engine
    ) -> None:
        action = self._action(pm_client, _user_id(seeded_engine, Role.PROJECT_MANAGER)).json()

        moved = engineer_client.post(
            url("/actions/A-9001/transition"),
            json={
                "target_status": "In Progress",
                "rationale": "Not mine.",
                "row_version": action["row_version"],
            },
        )

        assert moved.status_code == 403

    def test_an_assignee_must_be_an_active_project_member(
        self, pm_client: TestClient, seeded_engine: Engine
    ) -> None:
        assert self._action(pm_client, _user_id(seeded_engine, Role.PMO_ANALYST)).status_code == 422


class TestVerificationUpkeep:
    def test_a_requirement_can_be_linked_once_and_unlinked(
        self, requirements_client: TestClient
    ) -> None:
        payload = {
            "project_id": "P-002",
            "requirement_id": "REQ-2002",
            "target_type": "TestCase",
            "target_id": "TC-2001",
        }
        created = requirements_client.post(url("/trace-links"), json=payload)
        assert created.status_code == 201, created.text
        link = created.json()
        assert link["link_type"] == "verified_by"
        assert requirements_client.post(url("/trace-links"), json=payload).status_code == 409

        removed = requirements_client.delete(
            url(f"/trace-links/{link['trace_link_id']}"),
            params={"row_version": link["row_version"]},
        )

        assert removed.status_code == 204
        ids = {
            item["trace_link_id"]
            for item in requirements_client.get(
                url("/trace-links"), params={"project_id": "P-002"}
            ).json()
        }
        assert link["trace_link_id"] not in ids

    def test_a_link_must_stay_inside_its_project(self, requirements_client: TestClient) -> None:
        response = requirements_client.post(
            url("/trace-links"),
            json={
                "project_id": "P-002",
                "requirement_id": "REQ-2001",
                "target_type": "TestCase",
                "target_id": "TC-7001",
            },
        )

        assert response.status_code == 422

    def test_a_pass_needs_evidence(self, requirements_client: TestClient) -> None:
        cases = requirements_client.get(url("/projects/P-002/test-cases")).json()
        case = next(item for item in cases if item["test_case_id"] == "TC-2001")

        failed = requirements_client.patch(
            url("/test-cases/TC-2001"),
            json={"status": "Failed", "row_version": case["row_version"]},
        )
        missing = requirements_client.patch(
            url("/test-cases/TC-2001"),
            json={"status": "Passed", "row_version": failed.json()["row_version"]},
        )
        recorded = requirements_client.patch(
            url("/test-cases/TC-2001"),
            json={
                "status": "Passed",
                "verification_evidence": "EVID-SYN-1",
                "row_version": failed.json()["row_version"],
            },
        )

        assert failed.status_code == 200, failed.text
        # A new result never keeps the evidence of an earlier pass.
        assert failed.json()["verification_evidence"] is None
        assert missing.status_code == 422
        assert recorded.status_code == 200, recorded.text
        assert recorded.json()["verification_evidence"] == "EVID-SYN-1"
        assert recorded.json()["row_version"] == case["row_version"] + 2

    def test_engineers_cannot_change_verification(self, engineer_client: TestClient) -> None:
        response = engineer_client.post(
            url("/trace-links"),
            json={
                "project_id": "P-002",
                "requirement_id": "REQ-2001",
                "target_type": "Task",
                "target_id": "T-2001",
            },
        )

        assert response.status_code == 403

    def test_a_requirement_reference_is_generated_when_omitted(
        self, requirements_client: TestClient
    ) -> None:
        response = requirements_client.post(
            url("/requirements"),
            json={
                "project_id": "P-002",
                "requirement_text": "Report supplier emissions monthly",
                "requirement_type": "Functional",
                "priority": "High",
                "status": "Draft",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["requirement_id"] == "REQ-P-002-001"
