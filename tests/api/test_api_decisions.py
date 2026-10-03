"""Decision records, their outcomes and who may set them."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import url


def _payload(decision_id: str = "DEC-001", **overrides) -> dict:
    body = {
        "decision_id": decision_id,
        "project_id": "P-002",
        "title": "Move the pilot to the following quarter",
        "description": "Supplier readiness will not support the current pilot date.",
        "category": "Schedule",
        "decision_date": "2026-08-20",
        "owner": "Alex Morgan",
        "delivery_impact": "Pilot shifts by one quarter.",
        "related_milestone_id": "M-202",
    }
    body.update(overrides)
    return body


def _record_outcome(client: TestClient, decision_id: str, outcome: str, rationale: str):
    decision = client.get(url(f"/decisions/{decision_id}")).json()
    return client.post(
        url(f"/decisions/{decision_id}/outcome"),
        json={
            "outcome": outcome,
            "rationale": rationale,
            "row_version": decision["row_version"],
        },
    )


class TestCreate:
    def test_a_proposed_decision_is_recorded(self, client: TestClient) -> None:
        response = client.post(url("/decisions"), json=_payload())
        assert response.status_code == 201

        body = response.json()
        assert body["decision_id"] == "DEC-001"
        assert body["title"] == "Move the pilot to the following quarter"

    def test_a_new_decision_always_starts_proposed(self, client: TestClient) -> None:
        body = client.post(url("/decisions"), json=_payload("DEC-002")).json()
        assert body["status"] == "Proposed"
        assert body["approver"] is None
        assert body["approval_date"] is None

    def test_a_client_cannot_declare_its_own_outcome(self, client: TestClient) -> None:
        """Status and approver are not part of the create contract, so the request is refused."""
        response = client.post(
            url("/decisions"), json=_payload("DEC-003", status="Approved", approver="Someone")
        )
        assert response.status_code == 422

    def test_an_unknown_project_is_rejected(self, client: TestClient) -> None:
        response = client.post(url("/decisions"), json=_payload("DEC-004", project_id="P-999"))
        assert response.status_code == 404

    def test_a_duplicate_identifier_is_rejected(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-005"))
        assert client.post(url("/decisions"), json=_payload("DEC-005")).status_code == 409

    def test_related_records_are_kept(self, client: TestClient) -> None:
        body = client.post(
            url("/decisions"),
            json=_payload("DEC-006", related_risk_id="R-2001", related_change_request_id="CR-018"),
        ).json()
        assert body["related_risk_id"] == "R-2001"
        assert body["related_change_request_id"] == "CR-018"
        assert body["related_milestone_id"] == "M-202"

    @pytest.mark.parametrize(
        ("decision_id", "field", "record_id"),
        [
            ("DEC-X-M", "related_milestone_id", "M-701"),
            ("DEC-X-R", "related_risk_id", "R-7001"),
            ("DEC-X-C", "related_change_request_id", "CR-042"),
            ("DEC-X-Q", "related_requirement_id", "REQ-7001"),
        ],
    )
    def test_related_records_must_belong_to_the_decisions_project(
        self, client: TestClient, decision_id: str, field: str, record_id: str
    ) -> None:
        response = client.post(
            url("/decisions"),
            json=_payload(decision_id, **{field: record_id}),
        )

        assert response.status_code == 422
        assert "was not found in project P-002" in response.json()["detail"]

    def test_an_update_cannot_attach_a_record_from_another_project(
        self, client: TestClient
    ) -> None:
        created = client.post(url("/decisions"), json=_payload("DEC-007")).json()
        response = client.patch(
            url("/decisions/DEC-007"),
            json={
                "related_risk_id": "R-7001",
                "row_version": created["row_version"],
            },
        )

        assert response.status_code == 422


class TestOutcome:
    @pytest.mark.parametrize("outcome", ["Approved", "Rejected"])
    def test_a_proposed_decision_accepts_an_initial_outcome(
        self, client: TestClient, outcome: str
    ) -> None:
        client.post(url("/decisions"), json=_payload("DEC-010"))
        response = _record_outcome(
            client,
            "DEC-010",
            outcome,
            "Supplier confirmed the revised date.",
        )
        assert response.status_code == 200

        body = response.json()
        assert body["status"] == outcome
        assert body["approver"]
        assert body["approval_date"]
        assert body["rationale"] == "Supplier confirmed the revised date."

    def test_a_proposed_decision_cannot_be_superseded(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-011"))
        response = _record_outcome(
            client, "DEC-011", "Superseded", "No approved decision exists to replace."
        )
        assert response.status_code == 409
        assert client.get(url("/decisions/DEC-011")).json()["status"] == "Proposed"

    def test_a_decision_can_be_superseded(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-014"))
        approved = _record_outcome(
            client, "DEC-014", "Approved", "Approved at the engineering review."
        )
        assert approved.status_code == 200
        body = _record_outcome(
            client, "DEC-014", "Superseded", "Replaced by a later decision."
        ).json()
        assert body["status"] == "Superseded"

    @pytest.mark.parametrize("terminal_status", ["Rejected", "Superseded"])
    def test_a_terminal_decision_cannot_be_rewritten(
        self, client: TestClient, terminal_status: str
    ) -> None:
        client.post(url("/decisions"), json=_payload("DEC-015"))
        if terminal_status == "Superseded":
            _record_outcome(client, "DEC-015", "Approved", "Initially approved.")
        settled = _record_outcome(
            client, "DEC-015", terminal_status, f"Decision is now {terminal_status.lower()}."
        ).json()

        response = _record_outcome(client, "DEC-015", "Approved", "Attempted outcome rewrite.")
        assert response.status_code == 409
        current = client.get(url("/decisions/DEC-015")).json()
        assert current["status"] == terminal_status
        assert current["rationale"] == settled["rationale"]

    def test_an_outcome_without_reasoning_is_refused(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-012"))
        response = _record_outcome(client, "DEC-012", "Approved", "")
        assert response.status_code == 422

    def test_an_unknown_outcome_is_refused(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-013"))
        response = _record_outcome(client, "DEC-013", "Maybe", "Unsure")
        assert response.status_code == 422


class TestQuery:
    def test_decisions_can_be_filtered_by_project(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-020", project_id="P-002"))
        client.post(
            url("/decisions"),
            json=_payload("DEC-021", project_id="P-007", related_milestone_id="M-701"),
        )

        rows = client.get(url("/decisions?project_id=P-007")).json()
        assert {row["project_id"] for row in rows} == {"P-007"}

    def test_decisions_can_be_filtered_by_status(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-022"))
        client.post(url("/decisions"), json=_payload("DEC-023"))
        _record_outcome(client, "DEC-023", "Approved", "Agreed at the review.")

        proposed = client.get(url("/decisions?status=Proposed")).json()
        assert "DEC-022" in {row["decision_id"] for row in proposed}
        assert "DEC-023" not in {row["decision_id"] for row in proposed}

    def test_a_withdrawn_decision_leaves_the_list(self, client: TestClient) -> None:
        decision = client.post(url("/decisions"), json=_payload("DEC-024")).json()
        assert (
            client.delete(
                url("/decisions/DEC-024"),
                params={"row_version": decision["row_version"]},
            ).status_code
            == 204
        )

        rows = client.get(url("/decisions")).json()
        assert "DEC-024" not in {row["decision_id"] for row in rows}

    def test_an_unknown_decision_returns_not_found(self, client: TestClient) -> None:
        assert client.get(url("/decisions/DEC-999")).status_code == 404


class TestActivity:
    def test_every_decision_action_is_recorded_readably(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-030"))
        _record_outcome(
            client,
            "DEC-030",
            "Approved",
            "Agreed with the steering group.",
        )

        events = client.get(url("/activity?project_id=P-002&limit=50")).json()
        summaries = " ".join(event["summary"] for event in events)
        assert "Proposed decision DEC-030" in summaries
        assert "Approved decision DEC-030" in summaries

    def test_the_activity_trail_names_the_person(self, client: TestClient) -> None:
        client.post(url("/decisions"), json=_payload("DEC-031"))
        events = client.get(url("/activity?project_id=P-002&limit=50")).json()
        entry = next(e for e in events if e["entity_id"] == "DEC-031")
        assert entry["actor_name"]
