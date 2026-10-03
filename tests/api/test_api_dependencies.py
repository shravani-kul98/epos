"""Governed engineering dependency API contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import url


def _dependency(dependency_id: str = "D-900", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "dependency_id": dependency_id,
        "project_id": "P-002",
        "predecessor_type": "Task",
        "predecessor_id": "T-2002",
        "successor_type": "Milestone",
        "successor_id": "M-203",
        "dependency_name": "Engineering evidence before release gate",
        "relationship_type": "Finish-to-Start",
        "lag_days": 2,
        "status": "On Track",
        "delay_days": 0,
        "criticality": "High",
    }
    payload.update(overrides)
    return payload


def test_complete_dependency_is_created_and_returned(client: TestClient) -> None:
    response = client.post(url("/dependencies"), json=_dependency())
    assert response.status_code == 201
    assert response.json()["schedule_data_complete"] is True
    assert response.json()["row_version"] == 1
    assert client.get(url("/dependencies/D-900")).status_code == 200


def test_legacy_dependency_exposes_unknown_schedule_metadata(client: TestClient) -> None:
    dependency = client.get(url("/dependencies/D-2002")).json()
    assert dependency["relationship_type"] is None
    assert dependency["lag_days"] is None
    assert dependency["schedule_data_complete"] is False


def test_new_internal_dependency_requires_relationship_type_and_lag(
    client: TestClient,
) -> None:
    payload = _dependency()
    payload.pop("relationship_type")
    payload.pop("lag_days")
    response = client.post(url("/dependencies"), json=payload)
    assert response.status_code == 422
    assert "D-900" in response.json()["detail"]


def test_relationship_type_and_lag_cannot_be_recorded_partially(client: TestClient) -> None:
    response = client.post(url("/dependencies"), json=_dependency(lag_days=None))
    assert response.status_code == 422


def test_external_predecessor_can_remain_outside_the_schedulable_network(
    client: TestClient,
) -> None:
    response = client.post(
        url("/dependencies"),
        json=_dependency(
            "D-901",
            predecessor_type="Supplier",
            predecessor_id="SUP-SYNTHETIC",
            successor_type="Task",
            successor_id="T-2004",
            relationship_type=None,
            lag_days=None,
        ),
    )
    assert response.status_code == 201
    assert response.json()["schedule_data_complete"] is False


def test_dependency_endpoints_must_belong_to_the_same_project(client: TestClient) -> None:
    response = client.post(
        url("/dependencies"),
        json=_dependency("D-902", predecessor_id="T-7001"),
    )
    assert response.status_code == 422
    assert "Task T-7001 was not found in project P-002" in response.json()["detail"]


def test_dependency_successor_must_be_schedulable(client: TestClient) -> None:
    response = client.post(
        url("/dependencies"),
        json=_dependency("D-903", successor_type="Supplier", successor_id="SUP-SYNTHETIC"),
    )
    assert response.status_code == 422


def test_dependency_cannot_reference_itself(client: TestClient) -> None:
    response = client.post(
        url("/dependencies"),
        json=_dependency(
            "D-904",
            predecessor_type="Task",
            predecessor_id="T-2001",
            successor_type="Task",
            successor_id="T-2001",
        ),
    )
    assert response.status_code == 422
    assert "D-904" in response.json()["detail"]


def test_duplicate_dependency_edge_is_rejected_with_source_ids(client: TestClient) -> None:
    response = client.post(
        url("/dependencies"),
        json=_dependency(
            "D-905",
            predecessor_id="T-2001",
            successor_type="Task",
            successor_id="T-2002",
        ),
    )
    assert response.status_code == 409
    assert "D-2002" in response.json()["detail"]
    assert "D-905" in response.json()["detail"]


def test_cycle_is_rejected_with_supporting_dependency_ids(client: TestClient) -> None:
    response = client.post(
        url("/dependencies"),
        json=_dependency(
            "D-906",
            predecessor_id="T-2002",
            successor_type="Task",
            successor_id="T-2001",
        ),
    )
    assert response.status_code == 409
    assert "D-2002" in response.json()["detail"]
    assert "D-906" in response.json()["detail"]


def test_legacy_dependency_can_be_completed_by_governed_update(client: TestClient) -> None:
    current = client.get(url("/dependencies/D-2002")).json()
    response = client.patch(
        url("/dependencies/D-2002"),
        json={
            "relationship_type": "Finish-to-Start",
            "lag_days": 0,
            "row_version": current["row_version"],
        },
    )
    assert response.status_code == 200
    assert response.json()["schedule_data_complete"] is True


def test_dependency_update_cannot_create_a_cycle(client: TestClient) -> None:
    created = client.post(url("/dependencies"), json=_dependency()).json()
    response = client.patch(
        url("/dependencies/D-900"),
        json={
            "successor_type": "Task",
            "successor_id": "T-2001",
            "row_version": created["row_version"],
        },
    )
    assert response.status_code == 409
    assert "D-2002" in response.json()["detail"]
    assert "D-900" in response.json()["detail"]


def test_stale_dependency_update_is_rejected(client: TestClient) -> None:
    current = client.get(url("/dependencies/D-2002")).json()
    first = client.patch(
        url("/dependencies/D-2002"),
        json={"status": "Delayed", "row_version": current["row_version"]},
    )
    assert first.status_code == 200

    stale = client.patch(
        url("/dependencies/D-2002"),
        json={"status": "On Track", "row_version": current["row_version"]},
    )
    assert stale.status_code == 409
    assert client.get(url("/dependencies/D-2002")).json()["status"] == "Delayed"


def test_dependency_delete_is_soft_and_audited(client: TestClient) -> None:
    dependency = client.post(url("/dependencies"), json=_dependency()).json()
    assert (
        client.delete(
            url("/dependencies/D-900"),
            params={"row_version": dependency["row_version"]},
        ).status_code
        == 204
    )
    assert client.get(url("/dependencies/D-900")).status_code == 404
    event = client.get(url("/activity")).json()[0]
    assert event["entity_id"] == "D-900"
    assert event["action"] == "deleted"

    duplicate = client.post(url("/dependencies"), json=_dependency("D-907"))
    assert duplicate.status_code == 409
    assert "D-900" in duplicate.json()["detail"]
    assert "D-907" in duplicate.json()["detail"]


def test_dependency_access_is_project_scoped(engineer_client: TestClient) -> None:
    rows = engineer_client.get(url("/dependencies")).json()
    assert rows
    assert {row["project_id"] for row in rows} == {"P-002"}
    assert engineer_client.get(url("/dependencies/D-7001")).status_code == 404
    assert engineer_client.post(url("/dependencies"), json=_dependency()).status_code == 403
