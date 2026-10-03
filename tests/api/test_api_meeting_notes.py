"""Meeting notes, the follow-ups read out of them, and who may act on those."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import url

BODY = """Attendees: Alex Morgan, Priya Raman
Alex Morgan to confirm the supplier tooling capacity by 2026-09-04.
We agreed to hold the pilot until qualification completes.
Risk: the second source might slip past the qualification window.
Priya walked the team through the current yield numbers.
Action: circulate the revised schedule to the steering group.
Owner: Priya Raman
"""


def _note(note_id: str = "MN-001", **overrides) -> dict:
    body = {
        "note_id": note_id,
        "project_id": "P-002",
        "title": "Weekly delivery review",
        "meeting_date": "2026-08-20",
        "attendees": "Alex Morgan, Priya Raman",
        "body": BODY,
    }
    body.update(overrides)
    return body


def _create(client: TestClient, note_id: str = "MN-001", **overrides) -> dict:
    response = client.post(url("/meeting-notes"), json=_note(note_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _extract(client: TestClient, note_id: str = "MN-001") -> dict:
    response = client.get(url(f"/meeting-notes/{note_id}/extraction"))
    assert response.status_code == 200
    return response.json()


def _kinds(extraction: dict, kind: str) -> list[dict]:
    return [item for item in extraction["proposals"] if item["kind"] == kind]


class TestCapture:
    def test_a_note_keeps_its_wording_and_line_breaks(self, client: TestClient) -> None:
        assert _create(client)["body"] == BODY.strip()

    def test_a_note_needs_a_project_that_exists(self, client: TestClient) -> None:
        response = client.post(url("/meeting-notes"), json=_note("MN-002", project_id="P-999"))

        assert response.status_code == 404

    def test_an_identifier_cannot_be_reused(self, client: TestClient) -> None:
        _create(client, "MN-003")

        assert client.post(url("/meeting-notes"), json=_note("MN-003")).status_code == 409

    def test_a_note_can_be_corrected(self, client: TestClient) -> None:
        note = _create(client, "MN-004")
        response = client.patch(
            url("/meeting-notes/MN-004"),
            json={"title": "Delivery review", "row_version": note["row_version"]},
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Delivery review"

    def test_a_withdrawn_note_disappears(self, client: TestClient) -> None:
        note = _create(client, "MN-005")

        assert (
            client.delete(
                url("/meeting-notes/MN-005"),
                params={"row_version": note["row_version"]},
            ).status_code
            == 204
        )
        assert client.get(url("/meeting-notes/MN-005")).status_code == 404

    def test_notes_can_be_narrowed_to_one_project(self, client: TestClient) -> None:
        _create(client, "MN-006")
        _create(client, "MN-007", project_id="P-007")
        rows = client.get(url("/meeting-notes?project_id=P-007")).json()

        assert [row["note_id"] for row in rows] == ["MN-007"]

    def test_an_unknown_note_is_not_found(self, client: TestClient) -> None:
        assert client.get(url("/meeting-notes/MN-999")).status_code == 404


class TestExtraction:
    def test_a_decision_cue_is_read_as_a_decision(self, client: TestClient) -> None:
        _create(client, "MN-010")
        decisions = _kinds(_extract(client, "MN-010"), "decision")

        assert any("hold the pilot" in item["text"] for item in decisions)

    def test_a_risk_cue_is_read_as_a_risk(self, client: TestClient) -> None:
        _create(client, "MN-011")
        risks = _kinds(_extract(client, "MN-011"), "risk")

        assert any("second source" in item["text"] for item in risks)

    def test_an_action_cue_is_read_as_an_action(self, client: TestClient) -> None:
        _create(client, "MN-012")
        actions = _kinds(_extract(client, "MN-012"), "action")

        assert any("supplier tooling capacity" in item["text"] for item in actions)

    def test_narrative_lines_are_left_alone(self, client: TestClient) -> None:
        _create(client, "MN-013")
        texts = [item["text"] for item in _extract(client, "MN-013")["proposals"]]

        assert not any("walked the team through" in text for text in texts)

    def test_every_proposal_names_the_line_it_came_from(self, client: TestClient) -> None:
        _create(client, "MN-014")
        extraction = _extract(client, "MN-014")
        lines = BODY.strip().splitlines()

        for item in extraction["proposals"]:
            assert 1 <= item["source_line_number"] <= len(lines)
            assert item["matched_phrase"]
            assert item["source_line"]

    def test_an_owner_is_suggested_when_the_line_names_one(self, client: TestClient) -> None:
        _create(client, "MN-015")
        actions = _kinds(_extract(client, "MN-015"), "action")

        assert any(item["suggested_owner"] == "Alex Morgan" for item in actions)

    def test_a_due_date_is_only_suggested_when_it_is_written_down(self, client: TestClient) -> None:
        _create(client, "MN-016")
        proposals = _extract(client, "MN-016")["proposals"]
        dated = [item for item in proposals if item["suggested_due_date"]]

        assert all(item["suggested_due_date"] == "2026-09-04" for item in dated)

    def test_a_line_is_proposed_once_under_its_strongest_cue(self, client: TestClient) -> None:
        _create(client, "MN-017", body="We agreed to accept the risk of a late second source.\n")
        proposals = _extract(client, "MN-017")["proposals"]

        assert len(proposals) == 1
        assert proposals[0]["kind"] == "decision"

    def test_the_counts_match_the_proposals(self, client: TestClient) -> None:
        _create(client, "MN-018")
        extraction = _extract(client, "MN-018")

        assert extraction["action_count"] == len(_kinds(extraction, "action"))
        assert extraction["risk_count"] == len(_kinds(extraction, "risk"))
        assert extraction["decision_count"] == len(_kinds(extraction, "decision"))

    def test_extraction_creates_nothing(self, client: TestClient) -> None:
        before = len(client.get(url("/projects/P-002/actions")).json())
        _create(client, "MN-019")
        _extract(client, "MN-019")

        assert len(client.get(url("/projects/P-002/actions")).json()) == before

    def test_a_note_with_nothing_actionable_proposes_nothing(self, client: TestClient) -> None:
        _create(client, "MN-020", body="Priya presented the yield numbers.\nThe team discussed.\n")

        assert _extract(client, "MN-020")["proposals"] == []


class TestPromotion:
    def test_an_action_is_created_only_when_a_person_promotes_it(self, client: TestClient) -> None:
        _create(client, "MN-030")
        response = client.post(
            url("/meeting-notes/MN-030/promote"),
            json={
                "kind": "action",
                "text": "Confirm the supplier tooling capacity",
                "owner": "Alex Morgan",
                "due_date": "2026-09-04",
                "source_line_number": 2,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["action_description"] == "Confirm the supplier tooling capacity"
        assert body["owner"] == "Alex Morgan"
        assert body["project_id"] == "P-002"

    def test_the_created_record_points_back_at_the_note(self, client: TestClient) -> None:
        _create(client, "MN-031")
        body = client.post(
            url("/meeting-notes/MN-031/promote"),
            json={
                "kind": "action",
                "text": "Circulate the revised schedule",
                "owner": "Priya Raman",
                "source_line_number": 6,
            },
        ).json()

        assert body["source_reference"] == "Meeting note MN-031, line 6"

    def test_a_risk_can_be_promoted(self, client: TestClient) -> None:
        _create(client, "MN-032")
        response = client.post(
            url("/meeting-notes/MN-032/promote"),
            json={
                "kind": "risk",
                "text": "The second source might slip past the qualification window",
                "owner": "Alex Morgan",
                "probability": 4,
                "impact": 3,
                "source_line_number": 4,
            },
        )

        assert response.status_code == 201
        assert response.json()["mitigation_owner"] == "Alex Morgan"
        assert response.json()["severity_score"] == 12

    def test_a_decision_is_promoted_as_proposed_not_as_settled(self, client: TestClient) -> None:
        _create(client, "MN-033")
        response = client.post(
            url("/meeting-notes/MN-033/promote"),
            json={
                "kind": "decision",
                "text": "Hold the pilot until qualification completes",
                "owner": "Alex Morgan",
                "source_line_number": 3,
            },
        )

        assert response.status_code == 201
        assert response.json()["status"] == "Proposed"

    def test_the_promoted_record_uses_the_reviewed_wording_not_the_extracted_line(
        self, client: TestClient
    ) -> None:
        _create(client, "MN-034")
        body = client.post(
            url("/meeting-notes/MN-034/promote"),
            json={
                "kind": "action",
                "text": "Confirm tooling capacity with the second source as well",
                "owner": "Alex Morgan",
                "source_line_number": 2,
            },
        ).json()

        assert (
            body["action_description"] == "Confirm tooling capacity with the second source as well"
        )

    def test_a_line_outside_the_note_is_refused(self, client: TestClient) -> None:
        _create(client, "MN-035")
        response = client.post(
            url("/meeting-notes/MN-035/promote"),
            json={
                "kind": "action",
                "text": "Something that was never written down",
                "owner": "Alex Morgan",
                "source_line_number": 900,
            },
        )

        assert response.status_code == 422

    def test_a_promoted_identifier_never_collides(self, client: TestClient) -> None:
        _create(client, "MN-036")
        first = client.post(
            url("/meeting-notes/MN-036/promote"),
            json={
                "kind": "action",
                "text": "Confirm supplier tooling",
                "owner": "Alex Morgan",
                "source_line_number": 2,
            },
        ).json()
        second = client.post(
            url("/meeting-notes/MN-036/promote"),
            json={
                "kind": "action",
                "text": "Circulate the revised schedule",
                "owner": "Priya Raman",
                "source_line_number": 6,
            },
        ).json()

        assert first["action_id"] != second["action_id"]
        existing = {row["action_id"] for row in client.get(url("/projects/P-002/actions")).json()}
        assert first["action_id"] in existing
        assert second["action_id"] in existing

    def test_promotion_is_written_to_the_audit_trail(self, client: TestClient) -> None:
        _create(client, "MN-037")
        client.post(
            url("/meeting-notes/MN-037/promote"),
            json={
                "kind": "action",
                "text": "Confirm supplier tooling",
                "owner": "Alex Morgan",
                "source_line_number": 2,
            },
        )
        events = client.get(url("/activity?project_id=P-002&limit=50")).json()

        assert any("Promoted Meeting note MN-037" in event["summary"] for event in events)


class TestAuthorisation:
    def test_a_signed_out_visitor_cannot_read_notes(self, anonymous_client: TestClient) -> None:
        assert anonymous_client.get(url("/meeting-notes")).status_code == 401

    def test_an_executive_cannot_capture_a_note(self, executive_client: TestClient) -> None:
        assert executive_client.post(url("/meeting-notes"), json=_note("MN-040")).status_code == 403

    def test_an_engineer_can_capture_a_note(self, engineer_client: TestClient) -> None:
        assert engineer_client.post(url("/meeting-notes"), json=_note("MN-041")).status_code == 201

    def test_an_engineer_cannot_withdraw_a_note(
        self, client: TestClient, engineer_client: TestClient
    ) -> None:
        note = _create(client, "MN-042")

        assert (
            engineer_client.delete(
                url("/meeting-notes/MN-042"),
                params={"row_version": note["row_version"]},
            ).status_code
            == 403
        )

    @pytest.mark.parametrize("kind", ["action", "risk", "decision"])
    def test_an_engineer_cannot_bypass_creation_permissions_through_promotion(
        self, kind: str, client: TestClient, engineer_client: TestClient
    ) -> None:
        _create(client, f"MN-044-{kind}")
        response = engineer_client.post(
            url(f"/meeting-notes/MN-044-{kind}/promote"),
            json={
                "kind": kind,
                "text": "Reviewed follow-up",
                "owner": "Alex Morgan",
                "source_line_number": 2,
                **({"probability": 3, "impact": 3} if kind == "risk" else {}),
            },
        )

        assert response.status_code == 403

    def test_an_executive_cannot_promote_a_proposal(
        self, client: TestClient, executive_client: TestClient
    ) -> None:
        _create(client, "MN-043")
        response = executive_client.post(
            url("/meeting-notes/MN-043/promote"),
            json={
                "kind": "action",
                "text": "Confirm supplier tooling",
                "owner": "Alex Morgan",
                "source_line_number": 2,
            },
        )

        assert response.status_code == 403
