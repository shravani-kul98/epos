"""Governance, account-security and validation rules added by the repository review."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.main import create_app
from api.models import ActivityEventTable, ProjectTable, UserSessionTable, UserTable
from api.security.permissions import Role
from api.security.rate_limit import (
    REGISTRATIONS_PER_CLIENT,
    SIGN_IN_FAILURES_PER_ACCOUNT,
    SlidingWindowLimit,
)
from api.security.tokens import SESSION_MAX_HOURS, create_access_token
from api.services.delta_service import _SOURCES as DELTA_SOURCES
from api.static_files import SECURITY_HEADERS, mount_frontend
from src.risk_engine import ALERT_STALE_STATUS
from src.validators import DataValidationError
from tests.api.conftest import ANALYSIS_DATE_ISO, TEST_ACCOUNTS, TEST_PASSWORD, url

NEW_PASSWORD = "a-fresh-passphrase-for-tests-73"
WRONG_PASSWORD = "not-the-right-password-19"
NEW_ACCOUNT = {
    "email": "newcomer@test.example.com",
    "full_name": "New Comer",
    "password": "a-strong-enough-password-42",
}
NOTE_BODY = """Attendees: Alex Morgan, Priya Raman
Alex Morgan to confirm the supplier tooling capacity by 2026-09-04.
We agreed to hold the pilot until qualification completes.
Risk: the second source might slip past the qualification window.
"""


# ------------------------------------------------------------------ helpers
def _user(engine: Engine, role: Role) -> UserTable:
    with Session(engine) as session:
        statement = select(UserTable).where(UserTable.email == TEST_ACCOUNTS[role][0])
        return session.exec(statement).one()


def _login(client: TestClient, role: Role, password: str = TEST_PASSWORD):
    return client.post(
        url("/auth/login"), json={"email": TEST_ACCOUNTS[role][0], "password": password}
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _decision(decision_id: str, **overrides: object) -> dict[str, object]:
    return {
        "decision_id": decision_id,
        "project_id": "P-002",
        "title": "Hold the pilot for qualification",
        "description": "Qualification evidence is not complete yet.",
        "category": "Schedule",
        "decision_date": "2026-08-20",
        "owner": "Alex Morgan",
        **overrides,
    }


def _issue(issue_id: str) -> dict[str, object]:
    return {
        "issue_id": issue_id,
        "project_id": "P-002",
        "title": "Qualification fixture unavailable",
        "description": "The validation team cannot complete the planned test sequence.",
        "severity": "High",
        "owner": "Test Lead",
        "raised_date": "2026-08-20",
        "target_resolution_date": "2026-09-04",
    }


def _assumption(assumption_id: str) -> dict[str, object]:
    return {
        "assumption_id": assumption_id,
        "project_id": "P-002",
        "assumption_text": "The synthetic supplier fixture will arrive before validation starts.",
        "owner": "Test Project Manager",
        "validation_due_date": "2026-09-01",
        "impact_if_false": "Validation would move beyond the planned gate.",
    }


def _note(note_id: str) -> dict[str, object]:
    return {
        "note_id": note_id,
        "project_id": "P-002",
        "title": "Weekly delivery review",
        "meeting_date": "2026-08-20",
        "attendees": "Alex Morgan, Priya Raman",
        "body": NOTE_BODY,
    }


def _action_promotion(text: str = "Confirm supplier tooling") -> dict[str, object]:
    return {"kind": "action", "text": text, "owner": "Alex Morgan", "source_line_number": 2}


def _assign_task(client: TestClient, owner_id: int) -> dict:
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


def _search(client: TestClient, query: str) -> list[dict]:
    response = client.get(url("/search"), params={"q": query, "limit": 50})
    assert response.status_code == 200
    return response.json()["hits"]


def _age_records(engine: Engine, days: int) -> None:
    """Move every stored record back in time so a delta window can see past it."""
    moment = datetime.now(UTC) - timedelta(days=days)
    with Session(engine) as session:
        for table in (ProjectTable, *(source.table for source in DELTA_SOURCES)):
            for row in session.exec(select(table)).all():
                row.created_at = moment
                row.updated_at = moment
                session.add(row)
        session.commit()


# ------------------------------------------------------------------ governance
class TestChangeRequestGovernance:
    def test_a_decided_change_cannot_be_decided_again(self, client: TestClient) -> None:
        change = client.get(url("/change-requests/CR-042")).json()
        assert change["status"] == "Approved"

        response = client.post(
            url("/change-requests/CR-042/decision"),
            json={
                "decision": "Rejected",
                "rationale": "Overturning the earlier approval.",
                "row_version": change["row_version"],
            },
        )

        assert response.status_code == 409
        assert client.get(url("/change-requests/CR-042")).json()["status"] == "Approved"

    def test_a_decided_change_cannot_be_rewritten(self, client: TestClient) -> None:
        change = client.get(url("/change-requests/CR-042")).json()
        response = client.patch(
            url("/change-requests/CR-042"),
            json={"change_description": "Reworded later", "row_version": change["row_version"]},
        )

        assert response.status_code == 409

    def test_a_change_cited_by_a_decision_cannot_be_withdrawn(self, client: TestClient) -> None:
        cited = _decision("DEC-950", related_change_request_id="CR-018")
        assert client.post(url("/decisions"), json=cited).status_code == 201
        change = client.get(url("/change-requests/CR-018")).json()

        response = client.delete(
            url("/change-requests/CR-018"), params={"row_version": change["row_version"]}
        )

        assert response.status_code == 409


class TestDecisionGovernance:
    def _decide(self, client: TestClient, decision_id: str) -> dict:
        created = client.post(url("/decisions"), json=_decision(decision_id)).json()
        response = client.post(
            url(f"/decisions/{decision_id}/outcome"),
            json={
                "outcome": "Approved",
                "rationale": "Qualification data reviewed.",
                "row_version": created["row_version"],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_a_decided_record_can_no_longer_be_edited(self, client: TestClient) -> None:
        decided = self._decide(client, "DEC-951")
        response = client.patch(
            url("/decisions/DEC-951"),
            json={"title": "Quietly reworded", "row_version": decided["row_version"]},
        )

        assert response.status_code == 409

    def test_the_approval_date_is_the_server_date(self, client: TestClient) -> None:
        assert self._decide(client, "DEC-952")["approval_date"] == ANALYSIS_DATE_ISO

    def test_an_outcome_needs_a_meaningful_rationale(self, client: TestClient) -> None:
        created = client.post(url("/decisions"), json=_decision("DEC-953")).json()
        response = client.post(
            url("/decisions/DEC-953/outcome"),
            json={"outcome": "Approved", "rationale": "ok", "row_version": created["row_version"]},
        )

        assert response.status_code == 422


class TestAssumptionGovernance:
    def _validated(self, client: TestClient, assumption_id: str) -> dict:
        created = client.post(url("/assumptions"), json=_assumption(assumption_id)).json()
        response = client.post(
            url(f"/assumptions/{assumption_id}/transition"),
            json={
                "target_status": "Validated",
                "evidence": "Synthetic receipt SR-950 confirms the arrival date.",
                "row_version": created["row_version"],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_a_validated_statement_cannot_be_reworded(self, client: TestClient) -> None:
        validated = self._validated(client, "ASM-950")
        response = client.patch(
            url("/assumptions/ASM-950"),
            json={
                "assumption_text": "A different claim entirely.",
                "row_version": validated["row_version"],
            },
        )

        assert response.status_code == 409

    def test_a_validated_assumption_can_still_change_owner(self, client: TestClient) -> None:
        validated = self._validated(client, "ASM-951")
        response = client.patch(
            url("/assumptions/ASM-951"),
            json={"owner": "Test Lead", "row_version": validated["row_version"]},
        )

        assert response.status_code == 200
        assert response.json()["owner"] == "Test Lead"

    def test_a_retired_assumption_is_frozen(self, client: TestClient) -> None:
        validated = self._validated(client, "ASM-952")
        retired = client.post(
            url("/assumptions/ASM-952/transition"),
            json={
                "target_status": "Retired",
                "evidence": "The supplier fixture arrived as planned.",
                "row_version": validated["row_version"],
            },
        ).json()
        response = client.patch(
            url("/assumptions/ASM-952"),
            json={"owner": "Test Lead", "row_version": retired["row_version"]},
        )

        assert response.status_code == 409


class TestRiskGovernance:
    def test_closing_a_risk_requires_a_reason(self, client: TestClient) -> None:
        risk = client.get(url("/risks/R-2001")).json()
        refused = client.patch(
            url("/risks/R-2001"), json={"status": "Closed", "row_version": risk["row_version"]}
        )
        assert refused.status_code == 422

        closed = client.patch(
            url("/risks/R-2001"),
            json={
                "status": "Closed",
                "mitigation_status": "Complete",
                "rationale": "The second source is now qualified.",
                "row_version": risk["row_version"],
            },
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "Closed"
        events = client.get(url("/activity"), params={"project_id": "P-002"}).json()
        assert any(event["detail"] == "The second source is now qualified." for event in events)

    def test_a_risk_with_open_mitigation_cannot_be_closed(self, client: TestClient) -> None:
        risk = client.get(url("/risks/R-2001")).json()
        assert risk["mitigation_status"] == "Not Started"
        refused = client.patch(
            url("/risks/R-2001"),
            json={
                "status": "Closed",
                "rationale": "The second source is now qualified.",
                "row_version": risk["row_version"],
            },
        )
        assert refused.status_code == 422
        assert "Complete or Not Required" in refused.json()["detail"]

        accepted = client.patch(
            url("/risks/R-2001"),
            json={
                "status": "Accepted",
                "rationale": "The exposure is tolerated for this release.",
                "row_version": risk["row_version"],
            },
        )
        assert accepted.status_code == 200

    def test_an_unrecognised_status_is_refused(self, client: TestClient) -> None:
        risk = client.get(url("/risks/R-2001")).json()
        response = client.patch(
            url("/risks/R-2001"), json={"status": "Monitoring", "row_version": risk["row_version"]}
        )

        assert response.status_code == 422

    def test_a_status_alias_is_stored_in_its_canonical_spelling(self, client: TestClient) -> None:
        risk = client.get(url("/risks/R-2001")).json()
        response = client.patch(
            url("/risks/R-2001"),
            json={"status": "in mitigation", "row_version": risk["row_version"]},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "Mitigating"

    def test_a_new_risk_receives_a_server_reference(self, client: TestClient) -> None:
        response = client.post(
            url("/risks"),
            json={
                "project_id": "P-002",
                "risk_name": "Synthetic tooling risk",
                "probability": 2,
                "impact": 3,
                "status": "Open",
                "due_date": "2026-10-01",
            },
        )

        assert response.status_code == 201
        assert response.json()["risk_id"].startswith("R-")

    def test_a_risk_cited_by_a_decision_cannot_be_withdrawn(self, client: TestClient) -> None:
        cited = _decision("DEC-954", related_risk_id="R-2001")
        assert client.post(url("/decisions"), json=cited).status_code == 201
        risk = client.get(url("/risks/R-2001")).json()

        response = client.delete(url("/risks/R-2001"), params={"row_version": risk["row_version"]})

        assert response.status_code == 409


# ------------------------------------------------------------------ identifiers and inputs
class TestIdentifiers:
    def _action(self, action_id: str) -> dict[str, object]:
        return {
            "action_id": action_id,
            "project_id": "P-002",
            "action_description": "Chase the supplier for tooling dates",
            "due_date": "2026-09-30",
            "priority": "High",
        }

    def test_an_identifier_is_unique_across_record_types(self, client: TestClient) -> None:
        response = client.post(url("/actions"), json=self._action("R-2001"))

        assert response.status_code == 409
        assert "already used" in response.json()["detail"]

    def test_an_identifier_cannot_carry_path_characters(self, client: TestClient) -> None:
        assert client.post(url("/actions"), json=self._action("A/../900")).status_code == 422

    def test_access_is_checked_before_an_identifier_is_revealed(
        self, pm_client: TestClient
    ) -> None:
        """Outside their projects a caller learns nothing, not even that an identifier is taken."""
        payload = self._action("R-2001") | {"project_id": "P-011"}

        assert pm_client.post(url("/actions"), json=payload).status_code == 404


class TestReportedDates:
    def test_a_future_status_date_is_refused(self, client: TestClient) -> None:
        project = client.get(url("/projects/P-002")).json()
        response = client.patch(
            url("/projects/P-002"),
            json={"status_update_date": "2026-09-30", "row_version": project["row_version"]},
        )

        assert response.status_code == 422

    def test_a_status_update_is_dated_by_the_server(self, client: TestClient) -> None:
        project = client.get(url("/projects/P-002")).json()
        response = client.post(
            url("/projects/P-002/status-update"), json={"row_version": project["row_version"]}
        )

        assert response.status_code == 200
        assert response.json()["status_update_date"] == ANALYSIS_DATE_ISO

    def test_a_requirement_is_dated_by_the_server(self, client: TestClient) -> None:
        payload = {
            "requirement_id": "REQ-2950",
            "project_id": "P-002",
            "requirement_text": "The fixture shall log its temperature.",
            "requirement_type": "Functional",
            "priority": "High",
            "status": "Approved",
        }
        created = client.post(url("/requirements"), json=payload)
        assert created.status_code == 201, created.text
        assert created.json()["last_updated_date"] == ANALYSIS_DATE_ISO

        backdated = payload | {"requirement_id": "REQ-2951", "last_updated_date": "2020-01-01"}
        assert client.post(url("/requirements"), json=backdated).status_code == 422

    def test_a_dependency_lag_is_bounded(self, client: TestClient) -> None:
        response = client.post(
            url("/dependencies"),
            json={
                "dependency_id": "D-950",
                "project_id": "P-002",
                "predecessor_type": "Task",
                "predecessor_id": "T-2002",
                "successor_type": "Milestone",
                "successor_id": "M-203",
                "dependency_name": "Evidence before the release gate",
                "relationship_type": "Finish-to-Start",
                "lag_days": 4000,
                "status": "On Track",
                "delay_days": 0,
                "criticality": "High",
            },
        )

        assert response.status_code == 422


class TestProjectManagement:
    def test_a_new_project_starts_with_a_status_date(self, client: TestClient) -> None:
        response = client.post(
            url("/projects"),
            json={
                "project_id": "P-951",
                "project_name": "Status date probe",
                "domain": "Validation",
                "project_manager": "A. Engineer",
                "start_date": "2026-08-01",
                "project_phase": "Design",
                "business_priority": "High",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["status_update_date"] == ANALYSIS_DATE_ISO
        alerts = client.get(url("/analytics/alerts"), params={"project_id": "P-951"}).json()
        assert not [alert for alert in alerts if alert["alert_type"] == ALERT_STALE_STATUS]

    def test_a_manager_can_be_chosen_by_account(
        self, client: TestClient, seeded_engine: Engine
    ) -> None:
        manager = _user(seeded_engine, Role.PMO_ANALYST)
        project = client.get(url("/projects/P-011")).json()
        response = client.patch(
            url("/projects/P-011"),
            json={"project_manager_user_id": manager.id, "row_version": project["row_version"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["project_manager"] == manager.full_name
        members = client.get(url("/projects/P-011/members")).json()
        assert manager.id in {member["user_id"] for member in members}

    def test_a_manager_must_be_able_to_manage_projects(
        self, client: TestClient, seeded_engine: Engine
    ) -> None:
        engineer = _user(seeded_engine, Role.ENGINEER)
        project = client.get(url("/projects/P-011")).json()
        response = client.patch(
            url("/projects/P-011"),
            json={"project_manager_user_id": engineer.id, "row_version": project["row_version"]},
        )

        assert response.status_code == 422


class TestMeetingNotePromotion:
    def test_a_note_is_frozen_once_a_follow_up_is_promoted(self, client: TestClient) -> None:
        note = client.post(url("/meeting-notes"), json=_note("MN-950")).json()
        promoted = client.post(url("/meeting-notes/MN-950/promote"), json=_action_promotion())
        assert promoted.status_code == 201

        rewritten = client.patch(
            url("/meeting-notes/MN-950"),
            json={"body": "Rewritten afterwards.", "row_version": note["row_version"]},
        )
        assert rewritten.status_code == 409

        retitled = client.patch(
            url("/meeting-notes/MN-950"),
            json={
                "title": "Weekly delivery review (corrected)",
                "row_version": note["row_version"],
            },
        )
        assert retitled.status_code == 200

    def test_the_same_follow_up_cannot_be_promoted_twice(self, client: TestClient) -> None:
        client.post(url("/meeting-notes"), json=_note("MN-951"))
        first = client.post(url("/meeting-notes/MN-951/promote"), json=_action_promotion())
        second = client.post(url("/meeting-notes/MN-951/promote"), json=_action_promotion())

        assert first.status_code == 201
        assert second.status_code == 409
        assert first.json()["action_id"] in second.json()["detail"]

    def test_a_promoted_risk_needs_its_assessed_scores(self, client: TestClient) -> None:
        client.post(url("/meeting-notes"), json=_note("MN-952"))
        response = client.post(
            url("/meeting-notes/MN-952/promote"),
            json={
                "kind": "risk",
                "text": "The second source may slip",
                "owner": "Alex Morgan",
                "source_line_number": 4,
            },
        )

        assert response.status_code == 422

    def test_scores_are_refused_for_anything_but_a_risk(self, client: TestClient) -> None:
        client.post(url("/meeting-notes"), json=_note("MN-953"))
        response = client.post(
            url("/meeting-notes/MN-953/promote"),
            json=_action_promotion() | {"probability": 3, "impact": 3},
        )

        assert response.status_code == 422


# ------------------------------------------------------------------ accounts and sessions
class TestAccountAdministration:
    def test_an_account_with_open_work_cannot_be_disabled(
        self, client: TestClient, seeded_engine: Engine
    ) -> None:
        engineer = _user(seeded_engine, Role.ENGINEER)
        task = _assign_task(client, engineer.id or 0)
        response = client.patch(
            url(f"/admin/users/{engineer.id}/active"), json={"is_active": False}
        )

        assert response.status_code == 409
        assert task["task_id"] in response.json()["detail"]

    def test_open_work_keeps_a_role_that_can_update_it(
        self, client: TestClient, seeded_engine: Engine
    ) -> None:
        engineer = _user(seeded_engine, Role.ENGINEER)
        _assign_task(client, engineer.id or 0)
        response = client.patch(url(f"/admin/users/{engineer.id}/role"), json={"role": "executive"})

        assert response.status_code == 409

    def test_an_account_without_open_work_can_be_disabled(
        self, client: TestClient, seeded_engine: Engine
    ) -> None:
        engineer = _user(seeded_engine, Role.ENGINEER)
        response = client.patch(
            url(f"/admin/users/{engineer.id}/active"), json={"is_active": False}
        )

        assert response.status_code == 200

    def test_a_reset_issues_a_one_time_password_and_ends_sessions(
        self,
        client: TestClient,
        anonymous_client: TestClient,
        engineer_client: TestClient,
        seeded_engine: Engine,
    ) -> None:
        engineer = _user(seeded_engine, Role.ENGINEER)
        response = client.post(url(f"/admin/users/{engineer.id}/reset-password"))
        assert response.status_code == 200
        temporary = response.json()["temporary_password"]

        assert engineer_client.get(url("/auth/me")).status_code == 401
        assert _login(anonymous_client, Role.ENGINEER, temporary).status_code == 200
        with Session(seeded_engine) as session:
            events = session.exec(select(ActivityEventTable)).all()
        assert events
        assert all(temporary not in f"{event.summary} {event.detail}" for event in events)

    def test_an_administrator_resets_their_own_password_elsewhere(
        self, client: TestClient, seeded_engine: Engine
    ) -> None:
        administrator = _user(seeded_engine, Role.ADMINISTRATOR)

        assert (
            client.post(url(f"/admin/users/{administrator.id}/reset-password")).status_code == 409
        )


class TestSessions:
    def test_changing_a_password_ends_existing_sessions(
        self, anonymous_client: TestClient, engineer_client: TestClient
    ) -> None:
        response = engineer_client.post(
            url("/auth/change-password"),
            json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 204
        assert engineer_client.get(url("/auth/me")).status_code == 401
        assert _login(anonymous_client, Role.ENGINEER, NEW_PASSWORD).status_code == 200
        assert _login(anonymous_client, Role.ENGINEER).status_code == 401

    def test_the_new_password_must_differ_from_the_current_one(
        self, engineer_client: TestClient
    ) -> None:
        response = engineer_client.post(
            url("/auth/change-password"),
            json={"current_password": TEST_PASSWORD, "new_password": TEST_PASSWORD},
        )

        assert response.status_code == 422

    def test_a_session_can_be_refreshed(self, engineer_client: TestClient) -> None:
        response = engineer_client.post(url("/auth/refresh"))

        assert response.status_code == 200
        token = response.json()["access_token"]
        assert engineer_client.get(url("/auth/me"), headers=_bearer(token)).status_code == 200

    def test_a_refresh_cannot_outlast_the_maximum_session(
        self, anonymous_client: TestClient, seeded_engine: Engine
    ) -> None:
        engineer = _user(seeded_engine, Role.ENGINEER)
        signed_in_long_ago = datetime.now(UTC) - timedelta(hours=SESSION_MAX_HOURS + 1)
        with Session(seeded_engine) as session:
            session.add(
                UserSessionTable(
                    id="long-running-session",
                    user_id=engineer.id or 0,
                    created_at=signed_in_long_ago,
                    last_seen_at=signed_in_long_ago,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            session.commit()
        token = create_access_token(
            engineer.id or 0,
            engineer.email,
            engineer.role,
            password_hash=engineer.password_hash,
            authenticated_at=signed_in_long_ago,
            session_record_id="long-running-session",
        )

        assert anonymous_client.get(url("/auth/me"), headers=_bearer(token)).status_code == 200
        assert (
            anonymous_client.post(url("/auth/refresh"), headers=_bearer(token)).status_code == 401
        )

    def test_a_token_not_bound_to_a_password_is_refused(
        self, anonymous_client: TestClient, seeded_engine: Engine
    ) -> None:
        engineer = _user(seeded_engine, Role.ENGINEER)
        token = create_access_token(engineer.id or 0, engineer.email, engineer.role)

        assert anonymous_client.get(url("/auth/me"), headers=_bearer(token)).status_code == 401


class TestRegistrationPolicy:
    def test_self_registration_can_be_turned_off(
        self, anonymous_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EPOS_SELF_REGISTRATION", "false")

        assert anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT).status_code == 403

    def test_registration_can_be_limited_to_approved_domains(
        self, anonymous_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EPOS_REGISTRATION_EMAIL_DOMAINS", "approved.example.com")
        approved = NEW_ACCOUNT | {"email": "newcomer@approved.example.com"}

        assert anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT).status_code == 403
        assert anonymous_client.post(url("/auth/register"), json=approved).status_code == 201

    def test_a_refused_duplicate_does_not_name_the_account(
        self, anonymous_client: TestClient
    ) -> None:
        anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT)
        response = anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT)

        assert response.status_code == 409
        detail = response.json()["detail"].lower()
        assert NEW_ACCOUNT["email"] not in detail
        assert "registered" not in detail
        assert "exists" not in detail


class TestRequestLimits:
    def _fail(self, client: TestClient, times: int) -> None:
        for _ in range(times):
            assert _login(client, Role.ENGINEER, WRONG_PASSWORD).status_code == 401

    def test_repeated_failures_pause_sign_in_for_the_account(
        self, anonymous_client: TestClient
    ) -> None:
        self._fail(anonymous_client, SIGN_IN_FAILURES_PER_ACCOUNT)
        response = _login(anonymous_client, Role.ENGINEER)

        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0
        assert _login(anonymous_client, Role.PROJECT_MANAGER).status_code == 200

    def test_a_successful_sign_in_clears_earlier_failures(
        self, anonymous_client: TestClient
    ) -> None:
        self._fail(anonymous_client, SIGN_IN_FAILURES_PER_ACCOUNT - 1)
        assert _login(anonymous_client, Role.ENGINEER).status_code == 200

        self._fail(anonymous_client, SIGN_IN_FAILURES_PER_ACCOUNT - 1)
        assert _login(anonymous_client, Role.ENGINEER).status_code == 200

    def test_refusals_are_logged_without_the_address_or_password(
        self, anonymous_client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="api.routers.auth"):
            self._fail(anonymous_client, SIGN_IN_FAILURES_PER_ACCOUNT)
            _login(anonymous_client, Role.ENGINEER)

        messages = [r.getMessage() for r in caplog.records if r.name == "api.routers.auth"]
        assert any(message.startswith("Sign-in refused") for message in messages)
        assert any(message.startswith("Sign-in paused") for message in messages)
        email = TEST_ACCOUNTS[Role.ENGINEER][0]
        assert all(email not in message and WRONG_PASSWORD not in message for message in messages)

    def test_limits_can_be_switched_off(
        self, seeded_engine: Engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EPOS_RATE_LIMITS", "false")
        with TestClient(create_app()) as unlimited:
            self._fail(unlimited, SIGN_IN_FAILURES_PER_ACCOUNT + 1)
            assert _login(unlimited, Role.ENGINEER).status_code == 200

    def test_registrations_are_limited_per_network(self, anonymous_client: TestClient) -> None:
        statuses = [
            anonymous_client.post(url("/auth/register"), json=NEW_ACCOUNT).status_code
            for _ in range(REGISTRATIONS_PER_CLIENT + 1)
        ]

        assert statuses[0] == 201
        assert statuses[1:-1] == [409] * (REGISTRATIONS_PER_CLIENT - 1)
        assert statuses[-1] == 429

    def test_assistant_questions_are_limited_per_account(self, client: TestClient) -> None:
        client.app.state.rate_limits.assistant_user = SlidingWindowLimit(1, 300)
        question = {"question": "Which projects need attention?"}

        assert client.post(url("/copilot/ask"), json=question).status_code == 200
        limited = client.post(url("/copilot/ask"), json=question)
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers


# ------------------------------------------------------------------ discovery and operations
class TestDiscovery:
    def test_issues_assumptions_and_meeting_notes_can_be_searched(self, client: TestClient) -> None:
        assert client.post(url("/issues"), json=_issue("ISS-950")).status_code == 201
        assert client.post(url("/assumptions"), json=_assumption("ASM-953")).status_code == 201
        assert client.post(url("/meeting-notes"), json=_note("MN-954")).status_code == 201

        expected = {
            "fixture unavailable": ("issue", "/projects/P-002?tab=issues"),
            "fixture will arrive": ("assumption", "/projects/P-002?tab=assumptions"),
            "weekly delivery review": ("meeting_note", "/projects/P-002?tab=meetings"),
        }
        for query, (record_type, path) in expected.items():
            hit = _search(client, query)[0]
            assert (hit["record_type"], hit["path"]) == (record_type, path)

    def test_dependencies_can_be_searched(self, client: TestClient) -> None:
        hit = _search(client, "D-2002")[0]

        assert hit["record_type"] == "dependency"
        assert hit["path"].endswith("?tab=work")

    def test_a_new_issue_appears_in_the_project_delta(
        self, client: TestClient, seeded_engine: Engine
    ) -> None:
        _age_records(seeded_engine, days=400)
        assert client.post(url("/issues"), json=_issue("ISS-951")).status_code == 201

        body = client.get(url("/projects/P-002/delta"), params={"days": 7}).json()

        assert "issues" in [group["key"] for group in body["groups"]]


class TestOperations:
    def test_a_decided_change_is_not_reported_as_open_against_its_requirement(
        self, client: TestClient
    ) -> None:
        matrix = client.get(url("/analytics/traceability"), params={"project_id": "P-007"}).json()
        row = next(row for row in matrix["rows"] if row["requirement_id"] == "REQ-7001")

        assert client.get(url("/change-requests/CR-042")).json()["status"] == "Approved"
        assert "CR-042" not in row["open_change_request_ids"]

    def test_health_reports_whether_the_schema_is_current(
        self, anonymous_client: TestClient
    ) -> None:
        assert anonymous_client.get(url("/health")).json()["schema_current"] is True

    def test_stored_data_that_fails_validation_is_a_service_failure(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(*_: object, **__: object) -> None:
            raise DataValidationError(["T-2001: synthetic inconsistency"])

        monkeypatch.setattr("api.routers.analytics.calculate_project_health", fail)

        assert client.get(url("/analytics/projects/P-002/health")).status_code == 503
        requested = client.get(
            url("/analytics/projects/P-002/health"), params={"as_of_date": ANALYSIS_DATE_ISO}
        )
        assert requested.status_code == 422

    def test_the_served_interface_carries_security_headers(self, tmp_path: Path) -> None:
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
        (dist / "assets" / "app-abc123.js").write_text("export {};", encoding="utf-8")
        app = FastAPI()
        assert mount_frontend(app, "/api/v1", dist)

        with TestClient(app) as browser:
            shell = browser.get("/projects/P-002")
            asset = browser.get("/assets/app-abc123.js")

        for response in (shell, asset):
            assert response.status_code == 200
            for header, value in SECURITY_HEADERS.items():
                assert response.headers[header] == value
        assert "frame-ancestors 'none'" in shell.headers["Content-Security-Policy"]
        assert shell.headers["Cache-Control"] == "no-cache"
        assert "immutable" in asset.headers["Cache-Control"]

    def test_a_new_release_shell_is_never_mistaken_for_the_previous_one(
        self, tmp_path: Path
    ) -> None:
        dist = tmp_path / "dist"
        dist.mkdir()
        index = dist / "index.html"
        index.write_text('<script src="/assets/index-AAAA1111.js"></script>', encoding="utf-8")
        released = index.stat().st_mtime_ns
        app = FastAPI()
        assert mount_frontend(app, "/api/v1", dist)

        with TestClient(app) as browser:
            first = browser.get("/")
            # Same length and the same file date, as the hosting platform presents them.
            index.write_text('<script src="/assets/index-BBBB2222.js"></script>', encoding="utf-8")
            os.utime(index, ns=(released, released))
            second = browser.get("/", headers={"If-None-Match": first.headers["ETag"]})

        assert second.status_code == 200
        assert "index-BBBB2222.js" in second.text
        assert second.headers["ETag"] != first.headers["ETag"]
        assert second.headers["content-type"].startswith("text/html")
        assert "last-modified" not in second.headers
