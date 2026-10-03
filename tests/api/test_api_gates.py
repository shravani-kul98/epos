"""Governed Gate lifecycle, readiness, review, and authorization contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import url


def _gate(
    gate_id: str = "G-900", project_id: str = "P-002", sequence: int = 1
) -> dict[str, object]:
    return {
        "gate_id": gate_id,
        "project_id": project_id,
        "milestone_id": "M-202" if project_id == "P-002" else "M-701",
        "gate_name": f"Synthetic readiness Gate {gate_id}",
        "sequence": sequence,
        "planned_review_date": "2026-10-15",
        "owner": "Test Project Manager",
        "applicable_baseline": "Synthetic baseline BL-1",
    }


def _criterion(
    criterion_id: str = "GC-900", *, evidence_required: bool = True
) -> dict[str, object]:
    return {
        "criterion_id": criterion_id,
        "criterion_type": "Exit",
        "criterion_name": "Synthetic verification evidence accepted",
        "description": "The synthetic verification record has been reviewed.",
        "is_mandatory": True,
        "evidence_required": evidence_required,
    }


def _transition(client: TestClient, gate_id: str, target: str):
    gate = client.get(url(f"/gates/{gate_id}")).json()
    return client.post(
        url(f"/gates/{gate_id}/transition"),
        json={
            "target_status": target,
            "rationale": f"Move synthetic Gate to {target}.",
            "row_version": gate["row_version"],
        },
    )


def _prepare_complete_gate(
    client: TestClient, gate_id: str = "G-900", criterion_id: str = "GC-900"
) -> None:
    assert client.post(url("/gates"), json=_gate(gate_id)).status_code == 201
    assert _transition(client, gate_id, "Preparing").status_code == 200
    criterion = client.post(url(f"/gates/{gate_id}/criteria"), json=_criterion(criterion_id))
    assert criterion.status_code == 201
    assessed = client.post(
        url(f"/gates/{gate_id}/criteria/{criterion_id}/assessment"),
        json={
            "target_status": "Met",
            "rationale": "Synthetic verification record reviewed.",
            "evidence_reference": "EV-900",
            "row_version": criterion.json()["row_version"],
        },
    )
    assert assessed.status_code == 200


def test_gate_readiness_requires_configured_mandatory_evidence(client: TestClient) -> None:
    created = client.post(url("/gates"), json=_gate())
    assert created.status_code == 201
    assert created.json()["status"] == "Not Started"
    assert created.json()["result"] is None
    assert created.json()["review_cycle"] == 1

    empty = client.get(url("/gates/G-900/readiness")).json()
    assert empty["state"] == "Not Ready"
    assert empty["percentage"] is None
    assert empty["blockers"][0]["source_ids"] == ["G-900"]
    assert empty["calculated_at"]
    assert empty["methodology_version"] == "1.0"
    assert empty["applicable_baseline"] == "Synthetic baseline BL-1"

    assert _transition(client, "G-900", "Preparing").status_code == 200
    criterion = client.post(url("/gates/G-900/criteria"), json=_criterion())
    missing_evidence = client.post(
        url("/gates/G-900/criteria/GC-900/assessment"),
        json={
            "target_status": "Met",
            "rationale": "Claimed complete without evidence.",
            "row_version": criterion.json()["row_version"],
        },
    )
    assert missing_evidence.status_code == 409
    assert "GC-900" in missing_evidence.json()["detail"]
    assert _transition(client, "G-900", "Ready for Review").status_code == 409


def test_explicit_human_review_controls_passing_transition(
    client: TestClient, pm_client: TestClient
) -> None:
    _prepare_complete_gate(client)
    ready = client.get(url("/gates/G-900/readiness")).json()
    assert ready["state"] == "Ready for Review"
    assert ready["percentage"] == 100
    assert ready["evidence_references"] == ["EV-900"]

    assert _transition(client, "G-900", "Ready for Review").status_code == 200
    assert _transition(client, "G-900", "In Review").status_code == 200
    assert _transition(client, "G-900", "Passed").status_code == 409

    review = pm_client.post(
        url("/gates/G-900/reviews"),
        json={
            "review_id": "GR-900",
            "outcome": "Approved",
            "rationale": "Synthetic evidence accepted by the human reviewer.",
        },
    )
    assert review.status_code == 201
    assert review.json()["reviewer"] == "Test Project Manager"
    assert review.json()["review_cycle"] == 1
    approved = client.get(url("/gates/G-900/readiness")).json()
    assert approved["state"] == "Approved"
    assert approved["latest_review_id"] == "GR-900"
    assert approved["latest_review_outcome"] == "Approved"

    passed = _transition(client, "G-900", "Passed")
    assert passed.status_code == 200
    assert passed.json()["status"] == "Passed"
    assert passed.json()["result"] == "Passed"
    assert passed.json()["actual_review_date"]
    assert pm_client.patch(url("/gates/G-900/reviews/GR-900"), json={}).status_code == 405
    assert pm_client.delete(url("/gates/G-900/reviews/GR-900")).status_code == 405


def test_nonconditional_review_normalizes_blank_conditions(
    client: TestClient, pm_client: TestClient
) -> None:
    _prepare_complete_gate(client)
    assert _transition(client, "G-900", "Ready for Review").status_code == 200
    assert _transition(client, "G-900", "In Review").status_code == 200

    response = pm_client.post(
        url("/gates/G-900/reviews"),
        json={
            "review_id": "GR-BLANK-CONDITIONS",
            "outcome": "Approved",
            "rationale": "Synthetic evidence accepted by the human reviewer.",
            "conditions": "   ",
        },
    )

    assert response.status_code == 201
    assert response.json()["conditions"] is None


def test_gate_review_rounds_preserve_history_without_poisoning_rework(
    client: TestClient, pm_client: TestClient
) -> None:
    _prepare_complete_gate(client)
    assert _transition(client, "G-900", "Ready for Review").status_code == 200
    assert _transition(client, "G-900", "In Review").status_code == 200
    rejected = pm_client.post(
        url("/gates/G-900/reviews"),
        json={
            "review_id": "GR-REJECTED",
            "outcome": "Rejected",
            "rationale": "Synthetic review found unresolved evidence.",
        },
    )
    assert rejected.status_code == 201
    duplicate = pm_client.post(
        url("/gates/G-900/reviews"),
        json={
            "review_id": "GR-DUPLICATE",
            "outcome": "Approved",
            "rationale": "Attempted rewrite of the same round.",
        },
    )
    assert duplicate.status_code == 409
    assert "GR-REJECTED" in duplicate.json()["detail"]
    assert _transition(client, "G-900", "Failed").status_code == 200

    reopened = _transition(client, "G-900", "Preparing")
    assert reopened.status_code == 200
    assert reopened.json()["review_cycle"] == 2
    readiness = client.get(url("/gates/G-900/readiness")).json()
    assert readiness["state"] == "Ready for Review"
    assert readiness["latest_review_id"] is None
    assert [row["review_id"] for row in client.get(url("/gates/G-900/reviews")).json()] == [
        "GR-REJECTED"
    ]


def test_gate_records_are_scoped_searchable_and_protect_parents(
    client: TestClient, engineer_client: TestClient
) -> None:
    assert client.post(url("/gates"), json=_gate()).status_code == 201
    assert client.post(url("/gates"), json=_gate("G-701", "P-007", 1)).status_code == 201

    assert [row["gate_id"] for row in client.get(url("/projects/P-002/gates")).json()] == ["G-900"]
    assert {row["gate_id"] for row in engineer_client.get(url("/gates")).json()} == {"G-900"}
    assert engineer_client.get(url("/gates/G-701")).status_code == 404
    assert engineer_client.post(url("/gates"), json=_gate("G-901")).status_code == 403
    hits = engineer_client.get(url("/search"), params={"q": "G-900"}).json()["hits"]
    assert [hit["record_id"] for hit in hits] == ["G-900"]
    assert engineer_client.get(url("/search"), params={"q": "G-701"}).json()["hits"] == []

    milestone = client.get(url("/milestones/M-202")).json()
    blocked = client.delete(
        url("/milestones/M-202"), params={"row_version": milestone["row_version"]}
    )
    assert blocked.status_code == 409
    assert "G-900" in blocked.json()["detail"]


def test_gate_updates_are_versioned_and_project_withdrawal_hides_gate_records(
    client: TestClient,
) -> None:
    gate = client.post(url("/gates"), json=_gate()).json()
    updated = client.patch(
        url("/gates/G-900"),
        json={"owner": "Synthetic Gate Owner", "row_version": gate["row_version"]},
    )
    assert updated.status_code == 200
    stale = client.patch(
        url("/gates/G-900"),
        json={"gate_name": "Stale name", "row_version": gate["row_version"]},
    )
    assert stale.status_code == 409

    project = client.get(url("/projects/P-002")).json()
    assert (
        client.delete(
            url("/projects/P-002"), params={"row_version": project["row_version"]}
        ).status_code
        == 204
    )
    assert client.get(url("/gates"), params={"project_id": "P-002"}).json() == []
    assert client.get(url("/gates/G-900")).status_code == 404


def test_withdrawn_gate_still_reserves_its_sequence(client: TestClient) -> None:
    """Regression: a withdrawn Gate must not turn sequence reuse into a server error."""
    gate = client.post(url("/gates"), json=_gate("G-900", sequence=1)).json()
    assert (
        client.delete(url("/gates/G-900"), params={"row_version": gate["row_version"]}).status_code
        == 204
    )

    reused = client.post(url("/gates"), json=_gate("G-901", sequence=1))
    assert reused.status_code == 409
    assert "G-900" in reused.json()["detail"]

    live = client.post(url("/gates"), json=_gate("G-902", sequence=2))
    assert live.status_code == 201
    moved = client.patch(
        url("/gates/G-902"),
        json={"sequence": 1, "row_version": live.json()["row_version"]},
    )
    assert moved.status_code == 409
    assert "G-900" in moved.json()["detail"]
    assert client.get(url("/gates/G-902")).json()["sequence"] == 2
