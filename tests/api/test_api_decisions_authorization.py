"""Who may propose a decision, and who may decide one.

Decisions reuse the change-control authorities: proposing carries the same permission as raising a
change request, and recording an outcome carries the same permission as deciding one. These tests
exist so that reuse stays deliberate rather than accidental.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import url

PROPOSAL = {
    "decision_id": "DEC-AUTH-1",
    "project_id": "P-002",
    "title": "Authorisation probe",
    "description": "Recorded by an authorisation test.",
    "category": "Schedule",
    "decision_date": "2026-08-20",
    "owner": "Alex Morgan",
}

OUTCOME = {"outcome": "Approved", "rationale": "Reviewed and accepted."}


def test_an_engineer_cannot_propose_a_decision(engineer_client: TestClient) -> None:
    assert engineer_client.post(url("/decisions"), json=PROPOSAL).status_code == 403


def test_an_engineer_cannot_record_an_outcome(
    engineer_client: TestClient, client: TestClient
) -> None:
    client.post(url("/decisions"), json={**PROPOSAL, "decision_id": "DEC-AUTH-2"})
    response = engineer_client.post(url("/decisions/DEC-AUTH-2/outcome"), json=OUTCOME)
    assert response.status_code == 403


def test_an_engineer_can_still_read_decisions(engineer_client: TestClient) -> None:
    """Read access is deliberately broad: context should not be hidden from the team."""
    assert engineer_client.get(url("/decisions")).status_code == 200


def test_an_executive_cannot_propose_a_decision(executive_client: TestClient) -> None:
    assert executive_client.post(url("/decisions"), json=PROPOSAL).status_code == 403


def test_a_requirements_manager_can_propose_but_not_decide(
    requirements_client: TestClient, client: TestClient
) -> None:
    created = requirements_client.post(
        url("/decisions"), json={**PROPOSAL, "decision_id": "DEC-AUTH-3"}
    )
    assert created.status_code == 201

    response = requirements_client.post(url("/decisions/DEC-AUTH-3/outcome"), json=OUTCOME)
    assert response.status_code == 403


def test_a_project_manager_can_decide_a_proposal_raised_by_someone_else(
    pm_client: TestClient, requirements_client: TestClient
) -> None:
    created = requirements_client.post(
        url("/decisions"), json={**PROPOSAL, "decision_id": "DEC-AUTH-4"}
    )
    assert created.status_code == 201

    response = pm_client.post(
        url("/decisions/DEC-AUTH-4/outcome"),
        json=OUTCOME | {"row_version": created.json()["row_version"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Approved"


def test_a_project_manager_cannot_decide_their_own_proposal(pm_client: TestClient) -> None:
    created = pm_client.post(url("/decisions"), json={**PROPOSAL, "decision_id": "DEC-AUTH-6"})
    assert created.status_code == 201

    response = pm_client.post(
        url("/decisions/DEC-AUTH-6/outcome"),
        json=OUTCOME | {"row_version": created.json()["row_version"]},
    )
    assert response.status_code == 409
    assert "another person" in response.json()["detail"]


def test_a_decision_without_an_identifier_is_given_the_next_reference(
    pm_client: TestClient,
) -> None:
    proposal = {key: value for key, value in PROPOSAL.items() if key != "decision_id"}
    first = pm_client.post(url("/decisions"), json=proposal)
    second = pm_client.post(url("/decisions"), json=proposal)
    assert first.status_code == second.status_code == 201
    first_id, second_id = first.json()["decision_id"], second.json()["decision_id"]
    assert first_id.startswith("DEC-P-002-")
    assert int(second_id.rsplit("-", 1)[1]) == int(first_id.rsplit("-", 1)[1]) + 1


def test_an_engineer_cannot_withdraw_a_decision(
    engineer_client: TestClient, client: TestClient
) -> None:
    decision = client.post(url("/decisions"), json={**PROPOSAL, "decision_id": "DEC-AUTH-5"}).json()
    assert (
        engineer_client.delete(
            url("/decisions/DEC-AUTH-5"),
            params={"row_version": decision["row_version"]},
        ).status_code
        == 403
    )


def test_an_anonymous_caller_cannot_read_decisions(anonymous_client: TestClient) -> None:
    assert anonymous_client.get(url("/decisions")).status_code == 401
