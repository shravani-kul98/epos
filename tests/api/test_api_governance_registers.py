"""Issue and assumption register contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import url


def _issue(issue_id: str = "ISS-900", project_id: str = "P-002") -> dict[str, object]:
    return {
        "issue_id": issue_id,
        "project_id": project_id,
        "title": "Qualification fixture unavailable",
        "description": "The validation team cannot complete the planned test sequence.",
        "severity": "High",
        "owner": "Test Lead",
        "raised_date": "2026-08-27",
        "target_resolution_date": "2026-09-04",
        "source_reference": "Meeting note MN-SYNTHETIC, line 4",
    }


def _assumption(assumption_id: str = "ASM-900", project_id: str = "P-002") -> dict[str, object]:
    return {
        "assumption_id": assumption_id,
        "project_id": project_id,
        "assumption_text": "The synthetic supplier fixture will arrive before validation starts.",
        "owner": "Test Project Manager",
        "validation_due_date": "2026-09-01",
        "impact_if_false": "Validation would move beyond the planned gate.",
        "source_reference": "Decision DEC-SYNTHETIC",
    }


class TestIssues:
    def test_issue_starts_open_and_status_cannot_be_supplied(self, pm_client: TestClient) -> None:
        created = pm_client.post(url("/issues"), json=_issue())
        assert created.status_code == 201
        assert created.json()["status"] == "Open"

        forged = _issue("ISS-901") | {"status": "Closed"}
        assert pm_client.post(url("/issues"), json=forged).status_code == 422

    def test_issue_access_is_permissioned_and_project_scoped(
        self,
        client: TestClient,
        pm_client: TestClient,
        engineer_client: TestClient,
    ) -> None:
        assert engineer_client.post(url("/issues"), json=_issue()).status_code == 403
        assert pm_client.post(url("/issues"), json=_issue(project_id="P-011")).status_code == 404

        assert client.post(url("/issues"), json=_issue("ISS-902", "P-011")).status_code == 201
        assert client.post(url("/issues"), json=_issue("ISS-903", "P-002")).status_code == 201
        visible = engineer_client.get(url("/issues")).json()
        assert {row["issue_id"] for row in visible} == {"ISS-903"}
        assert engineer_client.get(url("/issues/ISS-902")).status_code == 404

    def test_issue_transition_records_resolution_and_actor(self, pm_client: TestClient) -> None:
        issue = pm_client.post(url("/issues"), json=_issue()).json()
        in_progress = pm_client.post(
            url("/issues/ISS-900/transition"),
            json={
                "target_status": "In Progress",
                "rationale": "Validation owner accepted the recovery action.",
                "row_version": issue["row_version"],
            },
        ).json()
        resolved = pm_client.post(
            url("/issues/ISS-900/transition"),
            json={
                "target_status": "Resolved",
                "rationale": "The replacement fixture passed incoming inspection.",
                "row_version": in_progress["row_version"],
            },
        )

        assert resolved.status_code == 200
        body = resolved.json()
        assert body["status"] == "Resolved"
        assert body["resolution_summary"] == ("The replacement fixture passed incoming inspection.")
        assert body["resolved_by"] == "Test Project Manager"
        assert body["resolved_at"]

        event = next(
            event
            for event in pm_client.get(url("/activity?project_id=P-002")).json()
            if event["entity_id"] == "ISS-900" and event["action"] == "transitioned"
        )
        assert event["actor_name"] == "Test Project Manager"
        assert "status" in {change["field"] for change in event["changes"]}

    def test_issue_rejects_skipped_and_stale_transitions(self, pm_client: TestClient) -> None:
        issue = pm_client.post(url("/issues"), json=_issue()).json()
        skipped = pm_client.post(
            url("/issues/ISS-900/transition"),
            json={
                "target_status": "Closed",
                "rationale": "Attempted lifecycle skip.",
                "row_version": issue["row_version"],
            },
        )
        assert skipped.status_code == 409

        updated = pm_client.patch(
            url("/issues/ISS-900"),
            json={"owner": "Test Engineer", "row_version": issue["row_version"]},
        )
        assert updated.status_code == 200
        stale = pm_client.post(
            url("/issues/ISS-900/transition"),
            json={
                "target_status": "In Progress",
                "rationale": "Uses a stale view.",
                "row_version": issue["row_version"],
            },
        )
        assert stale.status_code == 409

    def test_issue_patch_cannot_bypass_transition(self, pm_client: TestClient) -> None:
        issue = pm_client.post(url("/issues"), json=_issue()).json()
        response = pm_client.patch(
            url("/issues/ISS-900"),
            json={"status": "Closed", "row_version": issue["row_version"]},
        )
        assert response.status_code == 422


class TestAssumptions:
    def test_assumption_starts_proposed_and_requires_governance_permission(
        self,
        requirements_client: TestClient,
        engineer_client: TestClient,
    ) -> None:
        created = requirements_client.post(url("/assumptions"), json=_assumption())
        assert created.status_code == 201
        assert created.json()["status"] == "Proposed"
        assert (
            engineer_client.post(url("/assumptions"), json=_assumption("ASM-901")).status_code
            == 403
        )

    def test_assumption_validation_records_evidence_and_actor(
        self, requirements_client: TestClient
    ) -> None:
        assumption = requirements_client.post(url("/assumptions"), json=_assumption()).json()
        response = requirements_client.post(
            url("/assumptions/ASM-900/transition"),
            json={
                "target_status": "Validated",
                "evidence": "Synthetic receipt SR-900 confirms the planned arrival date.",
                "row_version": assumption["row_version"],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "Validated"
        assert body["validation_evidence"].startswith("Synthetic receipt")
        assert body["validated_by"] == "Test Requirements Manager"
        assert body["validated_at"]

    def test_assumption_rejects_a_skipped_transition(self, requirements_client: TestClient) -> None:
        assumption = requirements_client.post(url("/assumptions"), json=_assumption()).json()
        response = requirements_client.post(
            url("/assumptions/ASM-900/transition"),
            json={
                "target_status": "Retired",
                "evidence": "Attempted lifecycle skip.",
                "row_version": assumption["row_version"],
            },
        )
        assert response.status_code == 409

    def test_assumption_access_is_project_scoped(
        self, client: TestClient, requirements_client: TestClient
    ) -> None:
        assert (
            client.post(url("/assumptions"), json=_assumption("ASM-902", "P-011")).status_code
            == 201
        )
        assert requirements_client.get(url("/assumptions")).json() == []
        assert requirements_client.get(url("/assumptions/ASM-902")).status_code == 404

    def test_assumption_patch_cannot_bypass_validation(
        self, requirements_client: TestClient
    ) -> None:
        assumption = requirements_client.post(url("/assumptions"), json=_assumption()).json()
        response = requirements_client.patch(
            url("/assumptions/ASM-900"),
            json={"status": "Validated", "row_version": assumption["row_version"]},
        )
        assert response.status_code == 422
