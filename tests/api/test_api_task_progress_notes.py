"""Progress notes an assignee records with a task update or its completion."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.models import UserTable
from api.security.permissions import Role
from tests.api.conftest import TEST_ACCOUNTS, url


def _engineer_id(engine: Engine) -> int:
    with Session(engine) as session:
        statement = select(UserTable).where(UserTable.email == TEST_ACCOUNTS[Role.ENGINEER][0])
        user = session.exec(statement).one()
        assert user.id is not None
        return user.id


def _assigned_task(client: TestClient, engine: Engine) -> dict:
    response = client.post(
        url("/tasks"),
        json={
            "project_id": "P-002",
            "milestone_id": "M-202",
            "task_name": "Synthetic fixture calibration",
            "owner_user_id": _engineer_id(engine),
            "status": "Not Started",
            "planned_end_date": "2026-10-15",
            "forecast_end_date": "2026-10-15",
            "completion_percent": 0,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _history(client: TestClient, task_id: str) -> list[dict]:
    response = client.get(url(f"/tasks/{task_id}/progress"))
    assert response.status_code == 200, response.text
    return response.json()


def test_an_assignee_reports_partial_progress_with_a_note(
    client: TestClient, engineer_client: TestClient, seeded_engine: Engine
) -> None:
    task = _assigned_task(client, seeded_engine)
    response = engineer_client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={
            "completion_percent": 30,
            "progress_note": "Fixture wiring done; calibration runs next.",
            "row_version": task["row_version"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["completion_percent"] == 30
    latest = _history(engineer_client, task["task_id"])[0]
    assert latest["note"] == "Fixture wiring done; calibration runs next."
    assert latest["actor_name"] == "Test Engineer"
    fields = {change["field"]: change for change in latest["changes"]}
    assert (fields["completion_percent"]["before"], fields["completion_percent"]["after"]) == (
        0,
        30,
    )
    assert "progress_note" not in fields
    assert "last_updated_date" not in fields


def test_a_note_alone_is_a_progress_report(
    client: TestClient, engineer_client: TestClient, seeded_engine: Engine
) -> None:
    task = _assigned_task(client, seeded_engine)
    response = engineer_client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={
            "progress_note": "Still waiting for the supplier fixture.",
            "row_version": task["row_version"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["row_version"] == task["row_version"] + 1
    assert response.json()["completion_percent"] == 0
    latest = _history(engineer_client, task["task_id"])[0]
    assert (latest["note"], latest["changes"]) == ("Still waiting for the supplier fixture.", [])
    feed = client.get(url("/activity"), params={"project_id": "P-002"}).json()
    assert feed[0]["headline"].startswith("Test Engineer reported progress on task")
    assert feed[0]["detail"] == "Note: Still waiting for the supplier fixture."


def test_completion_can_carry_a_note(
    client: TestClient, engineer_client: TestClient, seeded_engine: Engine
) -> None:
    task = _assigned_task(client, seeded_engine)
    response = engineer_client.post(
        url(f"/tasks/{task['task_id']}/complete"),
        json={
            "row_version": task["row_version"],
            "progress_note": "Calibrated and verified on bench 3.",
        },
    )

    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["completion_percent"]) == ("Complete", 100)
    latest = _history(client, task["task_id"])[0]
    assert (latest["action"], latest["note"]) == (
        "completed",
        "Calibrated and verified on bench 3.",
    )


def test_completion_still_works_without_a_note(
    client: TestClient, engineer_client: TestClient, seeded_engine: Engine
) -> None:
    task = _assigned_task(client, seeded_engine)
    response = engineer_client.post(
        url(f"/tasks/{task['task_id']}/complete"), json={"row_version": task["row_version"]}
    )

    assert response.status_code == 200
    assert _history(client, task["task_id"])[0]["note"] is None


def test_a_blank_or_oversized_note_is_refused(
    client: TestClient, engineer_client: TestClient, seeded_engine: Engine
) -> None:
    task = _assigned_task(client, seeded_engine)
    for note in ("   ", "x" * 1001):
        response = engineer_client.patch(
            url(f"/tasks/{task['task_id']}"),
            json={"progress_note": note, "row_version": task["row_version"]},
        )
        assert response.status_code == 422


def test_the_history_begins_with_the_task_being_created(
    client: TestClient, seeded_engine: Engine
) -> None:
    task = _assigned_task(client, seeded_engine)

    assert [entry["action"] for entry in _history(client, task["task_id"])] == ["created"]


def test_the_history_of_an_unknown_task_is_not_found(client: TestClient) -> None:
    assert client.get(url("/tasks/T-UNKNOWN/progress")).status_code == 404
