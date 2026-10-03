"""CRUD endpoint tests, including validation and referential integrity."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from src.risk_engine import ALERT_BLOCKED_TASK, ALERT_UNOWNED_RISK
from tests.api.conftest import url

NEW_PROJECT = {
    "project_id": "P-900",
    "project_name": "Synthetic Test Rig",
    "domain": "Validation",
    "project_manager": "A. Engineer",
    "start_date": "2026-01-05",
    "baseline_end_date": "2026-12-01",
    "forecast_end_date": "2026-12-15",
    "status_update_date": "2026-08-20",
    "project_phase": "Design",
    "business_priority": "High",
}

NEW_RISK = {
    "risk_id": "R-900",
    "project_id": "P-002",
    "risk_name": "Synthetic supplier risk",
    "probability": 4,
    "impact": 5,
    "status": "Open",
    "mitigation_owner": "A. Engineer",
    "mitigation_status": "In Progress",
    "due_date": "2026-10-01",
}


# ------------------------------------------------------------------ projects
def test_list_projects_returns_seeded_projects(client: TestClient, csv_portfolio) -> None:
    projects = client.get(url("/projects")).json()
    assert {project["project_id"] for project in projects} == set(csv_portfolio.project_ids)


def test_get_project_returns_one_record(client: TestClient) -> None:
    project = client.get(url("/projects/P-002")).json()
    assert project["project_id"] == "P-002"


def test_get_unknown_project_returns_404(client: TestClient) -> None:
    assert client.get(url("/projects/P-000")).status_code == 404


def test_create_project_persists_it(client: TestClient) -> None:
    response = client.post(url("/projects"), json=NEW_PROJECT)
    assert response.status_code == 201
    assert client.get(url("/projects/P-900")).status_code == 200


def test_create_duplicate_project_is_rejected(client: TestClient) -> None:
    client.post(url("/projects"), json=NEW_PROJECT)
    assert client.post(url("/projects"), json=NEW_PROJECT).status_code == 409


def test_commit_time_integrity_race_is_translated_to_conflict(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_integrity_error(_: Session) -> None:
        raise IntegrityError("INSERT", {}, RuntimeError("synthetic unique race"))

    monkeypatch.setattr(Session, "commit", raise_integrity_error)

    response = client.post(url("/projects"), json=NEW_PROJECT)

    assert response.status_code == 409
    assert response.json()["detail"] == "The write conflicted with current database state."


def test_create_project_with_blank_name_is_rejected(client: TestClient) -> None:
    payload = NEW_PROJECT | {"project_name": ""}
    assert client.post(url("/projects"), json=payload).status_code == 422


def test_create_project_with_unknown_field_is_rejected(client: TestClient) -> None:
    payload = NEW_PROJECT | {"unexpected_field": "value"}
    assert client.post(url("/projects"), json=payload).status_code == 422


def test_update_project_changes_only_supplied_fields(client: TestClient) -> None:
    before = client.get(url("/projects/P-002")).json()
    updated = client.patch(
        url("/projects/P-002"),
        json={"project_phase": "Verification", "row_version": before["row_version"]},
    ).json()
    assert updated["project_phase"] == "Verification"
    assert updated["project_name"] == before["project_name"]


def test_update_project_rejects_null_for_required_field(client: TestClient) -> None:
    before = client.get(url("/projects/P-002")).json()

    response = client.patch(
        url("/projects/P-002"),
        json={"project_name": None, "row_version": before["row_version"]},
    )

    assert response.status_code == 422
    assert client.get(url("/projects/P-002")).json()["project_name"] == before["project_name"]


def test_update_unknown_project_returns_404(client: TestClient) -> None:
    assert (
        client.patch(url("/projects/P-000"), json={"domain": "X", "row_version": 1}).status_code
        == 404
    )


def test_delete_project_removes_its_children(client: TestClient) -> None:
    project = client.get(url("/projects/P-002")).json()
    assert (
        client.delete(
            url("/projects/P-002"), params={"row_version": project["row_version"]}
        ).status_code
        == 204
    )
    assert client.get(url("/projects/P-002")).status_code == 404
    assert client.get(url("/tasks"), params={"project_id": "P-002"}).json() == []
    assert client.get(url("/risks"), params={"project_id": "P-002"}).json() == []


def test_delete_unknown_project_returns_404(client: TestClient) -> None:
    assert client.delete(url("/projects/P-000"), params={"row_version": 1}).status_code == 404


def test_milestone_with_live_task_cannot_be_withdrawn(client: TestClient) -> None:
    milestone = client.get(url("/milestones/M-202")).json()
    response = client.delete(
        url("/milestones/M-202"), params={"row_version": milestone["row_version"]}
    )

    assert response.status_code == 409
    assert "T-2001" in response.json()["detail"]


def test_task_with_live_dependency_cannot_be_withdrawn(client: TestClient) -> None:
    task = client.get(url("/tasks/T-2001")).json()
    response = client.delete(url("/tasks/T-2001"), params={"row_version": task["row_version"]})

    assert response.status_code == 409
    assert "D-2002" in response.json()["detail"]


def test_requirement_with_live_change_cannot_be_withdrawn(client: TestClient) -> None:
    requirement = client.get(url("/requirements/REQ-2002")).json()
    response = client.delete(
        url("/requirements/REQ-2002"),
        params={"row_version": requirement["row_version"]},
    )

    assert response.status_code == 409
    assert "CR-018" in response.json()["detail"]


# ------------------------------------------------------------------ child collections
def test_project_child_collections_are_scoped(client: TestClient) -> None:
    for path in ("milestones", "tasks", "risks", "actions", "requirements", "test-cases"):
        rows = client.get(url(f"/projects/P-002/{path}")).json()
        assert rows, path
        assert {row["project_id"] for row in rows} == {"P-002"}, path


def test_child_collection_for_unknown_project_returns_404(client: TestClient) -> None:
    assert client.get(url("/projects/P-000/tasks")).status_code == 404


def test_resources_expose_utilisation(client: TestClient) -> None:
    resources = client.get(url("/projects/P-002/resources")).json()
    for resource in resources:
        expected = round(resource["allocated_hours"] * 100 / resource["capacity_hours"], 1)
        assert resource["utilisation_percent"] == expected
        assert resource["is_overallocated"] == (
            resource["allocated_hours"] > resource["capacity_hours"]
        )


# ------------------------------------------------------------------ risks
def test_create_risk_persists_it(client: TestClient) -> None:
    response = client.post(url("/risks"), json=NEW_RISK)
    assert response.status_code == 201
    assert response.json()["severity_score"] == 20


def test_create_risk_for_unknown_project_is_rejected(client: TestClient) -> None:
    payload = NEW_RISK | {"project_id": "P-000"}
    assert client.post(url("/risks"), json=payload).status_code == 404


def test_risk_probability_must_be_within_one_to_five(client: TestClient) -> None:
    assert client.post(url("/risks"), json=NEW_RISK | {"probability": 6}).status_code == 422
    assert client.post(url("/risks"), json=NEW_RISK | {"probability": 0}).status_code == 422


def test_assigning_a_mitigation_owner_clears_the_unowned_risk_alert(client: TestClient) -> None:
    """A real control action must change the deterministic analysis."""
    alerts = client.get(url("/analytics/alerts")).json()
    unowned = [a for a in alerts if a["alert_type"] == ALERT_UNOWNED_RISK]
    assert unowned, "expected a seeded unowned risk"
    alert = unowned[0]
    risk_id = next(sid for sid in alert["source_ids"] if sid.startswith("R-"))
    risk = client.get(url(f"/risks/{risk_id}")).json()

    assert (
        client.patch(
            url(f"/risks/{risk_id}"),
            json={"mitigation_owner": "A. Engineer", "row_version": risk["row_version"]},
        ).status_code
        == 200
    )

    after = client.get(url("/analytics/alerts")).json()
    remaining = [
        a for a in after if a["alert_type"] == ALERT_UNOWNED_RISK and risk_id in a["source_ids"]
    ]
    assert remaining == []


def test_delete_risk_removes_it(client: TestClient) -> None:
    risk = client.post(url("/risks"), json=NEW_RISK).json()
    assert (
        client.delete(url("/risks/R-900"), params={"row_version": risk["row_version"]}).status_code
        == 204
    )
    assert client.get(url("/risks/R-900")).status_code == 404


def test_delete_rejects_a_stale_row_version(client: TestClient) -> None:
    created = client.post(url("/risks"), json=NEW_RISK).json()
    updated = client.patch(
        url("/risks/R-900"),
        json={"mitigation_owner": "Synthetic Owner", "row_version": created["row_version"]},
    )
    assert updated.status_code == 200

    stale_delete = client.delete(
        url("/risks/R-900"), params={"row_version": created["row_version"]}
    )

    assert stale_delete.status_code == 409
    assert client.get(url("/risks/R-900")).status_code == 200


# ------------------------------------------------------------------ tasks
def test_task_completion_must_be_a_percentage(client: TestClient) -> None:
    task = client.get(url("/tasks")).json()[0]
    assert (
        client.patch(
            url(f"/tasks/{task['task_id']}"),
            json={"completion_percent": 101, "row_version": task["row_version"]},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            url(f"/tasks/{task['task_id']}"),
            json={"completion_percent": -1, "row_version": task["row_version"]},
        ).status_code
        == 422
    )


def test_task_cannot_reference_an_unknown_milestone(client: TestClient) -> None:
    task = client.get(url("/tasks")).json()[0]
    response = client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"milestone_id": "M-000", "row_version": task["row_version"]},
    )
    assert response.status_code == 422


def test_task_cannot_be_created_under_another_projects_milestone(
    client: TestClient,
) -> None:
    response = client.post(
        url("/tasks"),
        json={
            "task_id": "T-900",
            "project_id": "P-002",
            "milestone_id": "M-701",
            "task_name": "Cross-project hierarchy probe",
            "status": "Not Started",
            "planned_end_date": "2026-10-01",
            "forecast_end_date": "2026-10-01",
            "completion_percent": 0,
        },
    )
    assert response.status_code == 422
    assert "Milestone M-701 was not found in project P-002" in response.json()["detail"]


def test_task_cannot_move_under_another_projects_milestone(client: TestClient) -> None:
    task = client.get(url("/tasks/T-2001")).json()
    response = client.patch(
        url("/tasks/T-2001"),
        json={"milestone_id": "M-701", "row_version": task["row_version"]},
    )
    assert response.status_code == 422
    assert "Milestone M-701 was not found in project P-002" in response.json()["detail"]


def test_delivery_schedule_facts_are_returned_by_the_api(client: TestClient) -> None:
    milestone = client.post(
        url("/milestones"),
        json={
            "milestone_id": "M-900",
            "project_id": "P-002",
            "milestone_name": "Synthetic completion milestone",
            "baseline_date": "2026-09-10",
            "forecast_date": "2026-09-14",
            "actual_date": "2026-09-12",
            "status": "Complete",
            "criticality": "High",
        },
    )
    assert milestone.status_code == 201
    assert milestone.json()["forecast_variance_days"] == 4
    assert milestone.json()["actual_variance_days"] == 2

    task = client.post(
        url("/tasks"),
        json={
            "task_id": "T-901",
            "project_id": "P-002",
            "milestone_id": "M-900",
            "task_name": "Synthetic schedule task",
            "status": "Complete",
            "planned_start_date": "2026-09-01",
            "forecast_start_date": "2026-09-03",
            "actual_start_date": "2026-09-02",
            "planned_end_date": "2026-09-10",
            "forecast_end_date": "2026-09-15",
            "actual_end_date": "2026-09-12",
            "completion_percent": 100,
        },
    )
    assert task.status_code == 201
    assert task.json()["forecast_start_variance_days"] == 2
    assert task.json()["forecast_finish_variance_days"] == 5
    assert task.json()["actual_start_variance_days"] == 1
    assert task.json()["actual_finish_variance_days"] == 2


def test_task_create_rejects_an_inverted_schedule(client: TestClient) -> None:
    response = client.post(
        url("/tasks"),
        json={
            "task_id": "T-902",
            "project_id": "P-002",
            "milestone_id": "M-202",
            "task_name": "Inverted schedule probe",
            "status": "Not Started",
            "planned_start_date": "2026-10-02",
            "planned_end_date": "2026-10-01",
            "forecast_end_date": "2026-10-01",
            "completion_percent": 0,
        },
    )
    assert response.status_code == 422


def test_task_update_validates_dates_against_the_complete_record(client: TestClient) -> None:
    task = client.get(url("/tasks/T-2001")).json()
    response = client.patch(
        url("/tasks/T-2001"),
        json={
            "forecast_start_date": "2026-08-11",
            "row_version": task["row_version"],
        },
    )
    assert response.status_code == 422
    assert client.get(url("/tasks/T-2001")).json()["forecast_start_date"] is None


def test_unblocking_a_task_clears_its_alert(client: TestClient) -> None:
    """The engine treats a task as blocked by flag or by status, so a real unblock clears both."""
    alerts = client.get(url("/analytics/alerts")).json()
    blocked = [a for a in alerts if a["alert_type"] == ALERT_BLOCKED_TASK]
    assert blocked, "expected a seeded blocked task"
    task_id = next(sid for sid in blocked[0]["source_ids"] if sid.startswith("T-"))
    task = client.get(url(f"/tasks/{task_id}")).json()

    response = client.patch(
        url(f"/tasks/{task_id}"),
        json={
            "is_blocked": False,
            "status": "In Progress",
            "row_version": task["row_version"],
        },
    )
    assert response.status_code == 200

    after = client.get(url("/analytics/alerts")).json()
    remaining = [
        a for a in after if a["alert_type"] == ALERT_BLOCKED_TASK and task_id in a["source_ids"]
    ]
    assert remaining == []


def test_clearing_only_the_blocked_flag_leaves_a_blocked_status_alert(client: TestClient) -> None:
    """Data must stay honest: a task still marked Blocked keeps its alert."""
    alerts = client.get(url("/analytics/alerts")).json()
    blocked = [a for a in alerts if a["alert_type"] == ALERT_BLOCKED_TASK]
    task_id = next(sid for sid in blocked[0]["source_ids"] if sid.startswith("T-"))
    task = client.get(url(f"/tasks/{task_id}")).json()
    assert task["status"] == "Blocked"

    client.patch(
        url(f"/tasks/{task_id}"),
        json={"is_blocked": False, "row_version": task["row_version"]},
    )

    after = client.get(url("/analytics/alerts")).json()
    assert [
        a for a in after if a["alert_type"] == ALERT_BLOCKED_TASK and task_id in a["source_ids"]
    ]


# ------------------------------------------------------------------ change requests
def test_change_request_must_reference_a_known_requirement(client: TestClient) -> None:
    payload = {
        "change_request_id": "CR-900",
        "project_id": "P-002",
        "requirement_id": "REQ-0000",
        "change_description": "Synthetic change",
        "reason": "Testing",
        "priority": "High",
        "status": "Open",
        "requested_date": "2026-08-01",
    }
    assert client.post(url("/change-requests"), json=payload).status_code == 422


def test_change_request_requirement_must_belong_to_its_project(client: TestClient) -> None:
    payload = {
        "change_request_id": "CR-901",
        "project_id": "P-002",
        "requirement_id": "REQ-7001",
        "change_description": "Synthetic cross-project change",
        "reason": "Testing",
        "priority": "High",
        "requested_date": "2026-08-01",
    }
    assert client.post(url("/change-requests"), json=payload).status_code == 422


def test_change_request_requester_comes_from_authenticated_actor(client: TestClient) -> None:
    payload = {
        "change_request_id": "CR-902",
        "project_id": "P-002",
        "requirement_id": "REQ-2001",
        "change_description": "Synthetic requester provenance change",
        "reason": "Testing",
        "priority": "High",
        "requested_date": "2026-08-01",
    }
    forged = client.post(url("/change-requests"), json={**payload, "requested_by": "Forged"})
    assert forged.status_code == 422

    response = client.post(url("/change-requests"), json=payload)
    assert response.status_code == 201
    assert response.json()["requested_by"] == "Test Administrator"


def test_change_request_impact_matches_known_values(client: TestClient) -> None:
    impact = client.get(url("/change-requests/CR-042/impact")).json()
    assert impact["requirement_id"] == "REQ-7001"
    assert impact["estimated_schedule_impact_days"] == 15
    assert impact["risk_level"] == "Critical"


def test_change_request_impact_carries_evidence(client: TestClient) -> None:
    impact = client.get(url("/change-requests/CR-042/impact")).json()
    assert impact["source_ids"]
    assert impact["explanation"].strip()


def test_impact_for_unknown_change_request_returns_404(client: TestClient) -> None:
    assert client.get(url("/change-requests/CR-000/impact")).status_code == 404


# ------------------------------------------------------------------ filtering
def test_collections_can_be_filtered_by_project(client: TestClient) -> None:
    for path in ("risks", "tasks", "actions", "milestones", "requirements", "change-requests"):
        rows = client.get(url(f"/{path}"), params={"project_id": "P-007"}).json()
        assert {row["project_id"] for row in rows} == {"P-007"}, path


def test_filtering_by_unknown_project_returns_empty(client: TestClient) -> None:
    assert client.get(url("/risks"), params={"project_id": "P-000"}).json() == []
