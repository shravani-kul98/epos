"""Governed Work Package, Deliverable, and Task hierarchy API contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import url


def _work_package(work_package_id: str = "WP-900", project_id: str = "P-002") -> dict[str, object]:
    return {
        "work_package_id": work_package_id,
        "project_id": project_id,
        "work_package_name": "Synthetic release evidence package",
        "description": "Groups synthetic engineering evidence for release review.",
        "owner": "Test Lead",
        "accountable_owner": "Test Project Manager",
        "status": "Planned",
        "priority": "High",
    }


def _deliverable(
    deliverable_id: str = "DEL-900",
    work_package_id: str = "WP-900",
    project_id: str = "P-002",
) -> dict[str, object]:
    return {
        "deliverable_id": deliverable_id,
        "project_id": project_id,
        "work_package_id": work_package_id,
        "deliverable_name": "Synthetic verification package",
        "description": "A synthetic, reviewable engineering outcome.",
        "owner": "Test Engineer",
        "accountable_owner": "Test Lead",
        "status": "Planned",
        "priority": "High",
        "acceptance_criteria": "All synthetic checks have recorded evidence.",
        "completion_evidence": None,
    }


def _task(
    task_id: str,
    *,
    deliverable_id: str | None = "DEL-900",
    parent_task_id: str | None = None,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "project_id": "P-002",
        "milestone_id": "M-202",
        "deliverable_id": deliverable_id,
        "parent_task_id": parent_task_id,
        "task_name": f"Synthetic hierarchy task {task_id}",
        "owner": "Test Engineer",
        "status": "Not Started",
        "planned_end_date": "2026-10-01",
        "forecast_end_date": "2026-10-01",
        "completion_percent": 0,
        "is_blocked": False,
    }


def _create_package_and_deliverable(client: TestClient) -> None:
    assert client.post(url("/work-packages"), json=_work_package()).status_code == 201
    assert client.post(url("/deliverables"), json=_deliverable()).status_code == 201


def test_hierarchy_records_support_versioned_crud_and_structured_audit(
    client: TestClient,
) -> None:
    package = client.post(url("/work-packages"), json=_work_package())
    assert package.status_code == 201
    assert package.json()["row_version"] == 1

    deliverable = client.post(url("/deliverables"), json=_deliverable())
    assert deliverable.status_code == 201
    assert deliverable.json()["acceptance_criteria"].startswith("All synthetic")
    assert [
        row["work_package_id"] for row in client.get(url("/projects/P-002/work-packages")).json()
    ] == ["WP-900"]
    assert [
        row["deliverable_id"] for row in client.get(url("/projects/P-002/deliverables")).json()
    ] == ["DEL-900"]

    updated = client.patch(
        url("/work-packages/WP-900"),
        json={"status": "Active", "row_version": package.json()["row_version"]},
    )
    assert updated.status_code == 200
    assert updated.json()["row_version"] == 2

    stale = client.patch(
        url("/work-packages/WP-900"),
        json={"priority": "Low", "row_version": 1},
    )
    assert stale.status_code == 409
    assert client.get(url("/work-packages/WP-900")).json()["priority"] == "High"

    event = client.get(url("/activity")).json()[0]
    assert event["entity_type"] == "Work Package"
    assert event["entity_id"] == "WP-900"
    assert event["changes"] == [
        {"field": "status", "label": "Status", "before": "Planned", "after": "Active"}
    ]


def test_parent_references_must_resolve_within_the_same_project(client: TestClient) -> None:
    assert client.post(url("/work-packages"), json=_work_package()).status_code == 201
    cross_project = client.post(
        url("/deliverables"),
        json=_deliverable(project_id="P-007"),
    )
    assert cross_project.status_code == 422
    assert "WP-900" in cross_project.json()["detail"]

    assert (
        client.post(url("/work-packages"), json=_work_package("WP-701", "P-007")).status_code == 201
    )
    assert (
        client.post(
            url("/deliverables"), json=_deliverable("DEL-701", "WP-701", "P-007")
        ).status_code
        == 201
    )
    wrong_deliverable = client.post(url("/tasks"), json=_task("T-900", deliverable_id="DEL-701"))
    assert wrong_deliverable.status_code == 422
    assert "DEL-701" in wrong_deliverable.json()["detail"]

    wrong_parent = client.post(
        url("/tasks"), json=_task("T-901", deliverable_id=None, parent_task_id="T-7001")
    )
    assert wrong_parent.status_code == 422
    assert "T-7001" in wrong_parent.json()["detail"]


def test_task_hierarchy_rejects_cycles_and_cross_deliverable_parents(
    client: TestClient,
) -> None:
    _create_package_and_deliverable(client)
    assert (
        client.post(url("/deliverables"), json=_deliverable("DEL-901", "WP-900")).status_code == 201
    )
    root = client.post(url("/tasks"), json=_task("T-900"))
    child = client.post(url("/tasks"), json=_task("T-901", parent_task_id="T-900"))
    assert root.status_code == 201
    assert child.status_code == 201
    assert child.json()["parent_task_id"] == "T-900"

    cycle = client.patch(
        url("/tasks/T-900"),
        json={"parent_task_id": "T-901", "row_version": root.json()["row_version"]},
    )
    assert cycle.status_code == 409
    assert "T-900" in cycle.json()["detail"]
    assert "T-901" in cycle.json()["detail"]

    crossed = client.patch(
        url("/tasks/T-901"),
        json={"deliverable_id": "DEL-901", "row_version": child.json()["row_version"]},
    )
    assert crossed.status_code == 409
    assert "T-900" in crossed.json()["detail"]
    assert "T-901" in crossed.json()["detail"]
    assert client.get(url("/tasks/T-901")).json()["deliverable_id"] == "DEL-900"


def test_live_hierarchy_children_protect_their_parents_from_withdrawal(
    client: TestClient,
) -> None:
    _create_package_and_deliverable(client)
    assert client.post(url("/tasks"), json=_task("T-900")).status_code == 201
    assert (
        client.post(url("/tasks"), json=_task("T-901", parent_task_id="T-900")).status_code == 201
    )

    root = client.get(url("/tasks/T-900")).json()
    child = client.get(url("/tasks/T-901")).json()
    deliverable = client.get(url("/deliverables/DEL-900")).json()
    work_package = client.get(url("/work-packages/WP-900")).json()
    task_conflict = client.delete(url("/tasks/T-900"), params={"row_version": root["row_version"]})
    assert task_conflict.status_code == 409
    assert "T-901" in task_conflict.json()["detail"]
    deliverable_conflict = client.delete(
        url("/deliverables/DEL-900"),
        params={"row_version": deliverable["row_version"]},
    )
    assert deliverable_conflict.status_code == 409
    assert "T-900" in deliverable_conflict.json()["detail"]
    package_conflict = client.delete(
        url("/work-packages/WP-900"),
        params={"row_version": work_package["row_version"]},
    )
    assert package_conflict.status_code == 409
    assert "DEL-900" in package_conflict.json()["detail"]

    assert (
        client.delete(url("/tasks/T-901"), params={"row_version": child["row_version"]}).status_code
        == 204
    )
    assert (
        client.delete(url("/tasks/T-900"), params={"row_version": root["row_version"]}).status_code
        == 204
    )
    assert (
        client.delete(
            url("/deliverables/DEL-900"),
            params={"row_version": deliverable["row_version"]},
        ).status_code
        == 204
    )
    assert (
        client.delete(
            url("/work-packages/WP-900"),
            params={"row_version": work_package["row_version"]},
        ).status_code
        == 204
    )
    assert client.get(url("/deliverables/DEL-900")).status_code == 404
    assert client.get(url("/work-packages/WP-900")).status_code == 404


def test_legacy_tasks_keep_optional_hierarchy_links(client: TestClient) -> None:
    task = client.get(url("/tasks/T-2001")).json()
    assert task["deliverable_id"] is None
    assert task["parent_task_id"] is None
    response = client.patch(
        url("/tasks/T-2001"),
        json={"completion_percent": 55, "row_version": task["row_version"]},
    )
    assert response.status_code == 200
    assert response.json()["deliverable_id"] is None
    assert response.json()["parent_task_id"] is None


def test_delivery_hierarchy_access_is_project_scoped(
    client: TestClient, engineer_client: TestClient
) -> None:
    assert client.post(url("/work-packages"), json=_work_package()).status_code == 201
    assert (
        client.post(url("/work-packages"), json=_work_package("WP-701", "P-007")).status_code == 201
    )

    rows = engineer_client.get(url("/work-packages")).json()
    assert {row["work_package_id"] for row in rows} == {"WP-900"}
    assert engineer_client.get(url("/work-packages/WP-701")).status_code == 404
    assert (
        engineer_client.post(url("/work-packages"), json=_work_package("WP-901")).status_code == 403
    )

    visible_search = engineer_client.get(url("/search"), params={"q": "WP-900"}).json()
    hidden_search = engineer_client.get(url("/search"), params={"q": "WP-701"}).json()
    assert [hit["record_id"] for hit in visible_search["hits"]] == ["WP-900"]
    assert hidden_search["hits"] == []


def test_project_withdrawal_includes_delivery_hierarchy_children(client: TestClient) -> None:
    _create_package_and_deliverable(client)
    assert client.post(url("/tasks"), json=_task("T-900")).status_code == 201

    project = client.get(url("/projects/P-002")).json()
    assert (
        client.delete(
            url("/projects/P-002"), params={"row_version": project["row_version"]}
        ).status_code
        == 204
    )
    assert client.get(url("/work-packages"), params={"project_id": "P-002"}).json() == []
    assert client.get(url("/deliverables"), params={"project_id": "P-002"}).json() == []
    assert client.get(url("/tasks/T-900")).status_code == 404
