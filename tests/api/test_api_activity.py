"""Activity trail tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.security.permissions import Role
from tests.api.conftest import url

NEW_ACTION = {
    "action_id": "A-900",
    "project_id": "P-002",
    "action_description": "Synthetic follow-up",
    "owner": "A. Engineer",
    "due_date": "2026-09-15",
    "status": "Open",
    "priority": "High",
    "source_reference": "Review",
}


def test_activity_is_empty_before_any_write(client: TestClient) -> None:
    assert client.get(url("/activity")).json() == []


def test_reading_data_records_no_activity(client: TestClient) -> None:
    client.get(url("/projects"))
    client.get(url("/analytics/portfolio"))
    client.get(url("/analytics/traceability"))
    assert client.get(url("/activity")).json() == []


def test_create_is_recorded(client: TestClient) -> None:
    client.post(url("/actions"), json=NEW_ACTION)
    events = client.get(url("/activity")).json()
    assert len(events) == 1
    assert events[0]["action"] == "created"
    assert events[0]["entity_type"] == "Action"
    assert events[0]["entity_id"] == "A-900"


def test_transition_is_recorded_with_the_field_change(client: TestClient) -> None:
    action = client.get(url("/actions")).json()[0]
    action_id = action["action_id"]
    client.post(
        url(f"/actions/{action_id}/transition"),
        json={
            "target_status": "In Progress",
            "rationale": "Engineering work started.",
            "row_version": action["row_version"],
        },
    )
    event = client.get(url("/activity")).json()[0]
    assert event["action"] == "transitioned"
    assert event["detail"] == "Engineering work started."
    assert event["changes"] == [
        {
            "field": "status",
            "label": "Status",
            "before": action["status"],
            "after": "In Progress",
        }
    ]


def test_structured_changes_redact_secret_shaped_fields() -> None:
    from api.services.activity_service import field_changes

    changes = field_changes({"api_key": "old-secret"}, {"api_key": "new-secret"})
    assert changes[0].before == "[redacted]"
    assert changes[0].after == "[redacted]"


def test_stale_action_transition_is_rejected_without_overwriting(client: TestClient) -> None:
    action = client.get(url("/actions")).json()[0]
    first = client.post(
        url(f"/actions/{action['action_id']}/transition"),
        json={
            "target_status": "In Progress",
            "rationale": "Engineering work started.",
            "row_version": action["row_version"],
        },
    )
    assert first.status_code == 200
    assert first.json()["row_version"] == action["row_version"] + 1

    stale = client.post(
        url(f"/actions/{action['action_id']}/transition"),
        json={
            "target_status": "Blocked",
            "rationale": "This request used stale evidence.",
            "row_version": action["row_version"],
        },
    )
    assert stale.status_code == 409
    assert client.get(url(f"/actions/{action['action_id']}")).json()["status"] == "In Progress"


def test_update_with_no_change_records_no_detail(client: TestClient) -> None:
    current = client.get(url("/actions")).json()[0]
    client.patch(
        url(f"/actions/{current['action_id']}"),
        json={"priority": current["priority"], "row_version": current["row_version"]},
    )
    assert client.get(url("/activity")).json()[0]["detail"] is None


def test_action_status_cannot_be_changed_by_patch(client: TestClient) -> None:
    current = client.get(url("/actions")).json()[0]
    response = client.patch(
        url(f"/actions/{current['action_id']}"),
        json={"status": "In Progress", "row_version": current["row_version"]},
    )
    assert response.status_code == 422
    assert client.get(url(f"/actions/{current['action_id']}")).json()["status"] == "Open"


def test_open_action_cannot_skip_directly_to_complete(client: TestClient) -> None:
    current = client.get(url("/actions")).json()[0]
    response = client.post(
        url(f"/actions/{current['action_id']}/transition"),
        json={
            "target_status": "Complete",
            "rationale": "Attempted lifecycle shortcut.",
            "row_version": current["row_version"],
        },
    )
    assert response.status_code == 409
    assert client.get(url(f"/actions/{current['action_id']}")).json()["status"] == "Open"
    assert client.get(url("/activity")).json() == []


def test_delete_is_recorded(client: TestClient) -> None:
    action = client.post(url("/actions"), json=NEW_ACTION).json()
    client.delete(url("/actions/A-900"), params={"row_version": action["row_version"]})
    event = client.get(url("/activity")).json()[0]
    assert event["action"] == "deleted"
    assert event["entity_id"] == "A-900"


def test_events_are_newest_first(client: TestClient) -> None:
    created = client.post(url("/actions"), json=NEW_ACTION).json()
    client.post(
        url("/actions/A-900/transition"),
        json={
            "target_status": "In Progress",
            "rationale": "Engineering work started.",
            "row_version": created["row_version"],
        },
    )
    events = client.get(url("/activity")).json()
    assert [event["action"] for event in events] == ["transitioned", "created"]


def test_activity_can_be_filtered_by_project(client: TestClient) -> None:
    client.post(url("/actions"), json=NEW_ACTION)
    assert client.get(url("/activity"), params={"project_id": "P-002"}).json()
    assert client.get(url("/activity"), params={"project_id": "P-007"}).json() == []


def test_user_administration_activity_is_administrator_only(
    client: TestClient,
    executive_client: TestClient,
    sign_in,
) -> None:
    pmo_client = sign_in(Role.PMO_ANALYST)
    user = next(row for row in client.get(url("/admin/users")).json() if row["role"] == "engineer")
    response = client.patch(
        url(f"/admin/users/{user['id']}/role"), json={"role": "engineering_lead"}
    )
    assert response.status_code == 200

    assert any(event["entity_type"] == "User" for event in client.get(url("/activity")).json())
    assert all(
        event["entity_type"] != "User" for event in executive_client.get(url("/activity")).json()
    )
    assert all(event["entity_type"] != "User" for event in pmo_client.get(url("/activity")).json())


def test_activity_limit_is_respected(client: TestClient) -> None:
    for index in range(3):
        payload = NEW_ACTION | {"action_id": f"A-91{index}"}
        client.post(url("/actions"), json=payload)
    assert len(client.get(url("/activity"), params={"limit": 2}).json()) == 2


def test_invalid_limit_is_rejected(client: TestClient) -> None:
    assert client.get(url("/activity"), params={"limit": 0}).status_code == 422
    assert client.get(url("/activity"), params={"limit": 10000}).status_code == 422


def test_failed_write_records_no_activity(client: TestClient) -> None:
    """A rejected create must leave no audit trail."""
    client.post(url("/actions"), json=NEW_ACTION | {"project_id": "P-000"})
    assert client.get(url("/activity")).json() == []


def test_deleting_a_project_records_one_event(client: TestClient) -> None:
    project = client.get(url("/projects/P-002")).json()
    client.delete(url("/projects/P-002"), params={"row_version": project["row_version"]})
    events = client.get(url("/activity")).json()
    assert len(events) == 1
    assert events[0]["entity_type"] == "Project"
