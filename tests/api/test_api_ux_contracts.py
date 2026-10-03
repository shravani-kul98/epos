"""UX contracts must preserve evidence, identities and authorization."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.models import ProjectMemberTable, TaskTable, UserTable
from api.security.permissions import Role
from tests.api.conftest import url

PROJECT = {
    "project_id": "P-UX",
    "project_name": "Synthetic UX project",
    "domain": "Validation",
    "project_manager": "Test Project Manager",
    "start_date": "2026-08-01",
    "project_phase": "Planning",
    "business_priority": "Medium",
}


def test_blank_project_is_unassessed_in_every_management_contract(empty_client: TestClient) -> None:
    assert empty_client.post(url("/projects"), json=PROJECT).status_code == 201
    detail = empty_client.get(url("/analytics/projects/P-UX")).json()
    assert detail["assessment"]["is_assessed"] is False
    assert detail["assessment"]["source_ids"] == ["P-UX"]
    portfolio = empty_client.get(url("/analytics/portfolio")).json()
    assert portfolio["project_count"] == portfolio["unassessed_count"] == 1
    assert sum(portfolio["health_bands"].values()) == 0
    assert sum(portfolio["confidence_bands"].values()) == 0
    assert portfolio["projects"][0]["assessment"]["is_assessed"] is False
    assert (
        empty_client.get(url("/analytics/portfolio"), params={"health_band": "Amber"}).json()[
            "projects"
        ]
        == []
    )
    report = empty_client.get(url("/analytics/executive-report")).json()
    assert "not yet assessed" in report["headline"]
    section = next(section for section in report["sections"] if section["key"] == "unassessed")
    assert section["items"][0]["source_ids"] == ["P-UX"]
    milestone = empty_client.post(
        url("/milestones"),
        json={
            "project_id": "P-UX",
            "milestone_name": "Recorded checkpoint",
            "status": "Not Started",
            "criticality": "Medium",
        },
    )
    assert milestone.status_code == 201, milestone.text
    assert milestone.json()["milestone_id"] == "M-P-UX-001"
    assert (
        empty_client.get(url("/analytics/projects/P-UX")).json()["assessment"]["is_assessed"]
        is True
    )


def test_references_are_project_scoped_and_do_not_reuse_withdrawn_ids(
    client: TestClient, engine: Engine
) -> None:
    payload = {
        "project_id": "P-002",
        "milestone_id": "M-202",
        "task_name": "Synthetic short reference",
        "status": "Not Started",
        "planned_end_date": "2026-10-15",
        "forecast_end_date": "2026-10-15",
        "completion_percent": 0,
    }
    first = client.post(url("/tasks"), json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["task_id"] == "T-P-002-001"
    assert client.delete(url("/tasks/T-P-002-001"), params={"row_version": 1}).status_code == 204
    second = client.post(url("/tasks"), json=payload)
    assert second.status_code == 201
    assert second.json()["task_id"] == "T-P-002-002"
    with Session(engine) as session:
        assert session.get(TaskTable, "T-2001") is not None


def test_long_project_references_fit_existing_schema(empty_client: TestClient) -> None:
    project_id = "P-" + "A" * 30
    assert (
        empty_client.post(url("/projects"), json={**PROJECT, "project_id": project_id}).status_code
        == 201
    )
    response = empty_client.post(
        url("/milestones"),
        json={
            "project_id": project_id,
            "milestone_name": "Synthetic checkpoint",
            "status": "Not Started",
            "criticality": "Medium",
        },
    )
    assert response.status_code == 201, response.text
    assert len(response.json()["milestone_id"]) <= 32


def test_people_options_are_permission_and_project_scoped(
    sign_in: Callable[[Role], TestClient],
) -> None:
    engineer = sign_in(Role.ENGINEER)
    assert engineer.get(url("/projects/options")).status_code == 403
    assert (
        engineer.get(url("/projects/P-002/people"), params={"purpose": "risk"}).status_code == 403
    )
    lead = sign_in(Role.ENGINEERING_LEAD)
    assert lead.get(url("/projects/P-002/people"), params={"purpose": "risk"}).status_code == 200
    assert lead.get(url("/projects/P-001/people"), params={"purpose": "risk"}).status_code == 404
    requirements = sign_in(Role.REQUIREMENTS_MANAGER)
    assert (
        requirements.get(url("/projects/P-002/people"), params={"purpose": "decision"}).status_code
        == 200
    )
    assert (
        requirements.get(url("/projects/P-002/people"), params={"purpose": "risk"}).status_code
        == 403
    )


def test_selected_manager_gains_project_access_and_is_audited(
    client: TestClient, engine: Engine
) -> None:
    with Session(engine) as session:
        manager = session.exec(
            select(UserTable).where(UserTable.role == Role.PROJECT_MANAGER)
        ).one()
        manager_id = manager.id
    options = client.get(url("/projects/options")).json()
    assert manager_id in {person["user_id"] for person in options["managers"]}
    response = client.post(
        url("/projects"), json={**PROJECT, "project_manager_user_id": manager_id}
    )
    assert response.status_code == 201, response.text
    with Session(engine) as session:
        membership = session.exec(
            select(ProjectMemberTable).where(
                ProjectMemberTable.project_id == "P-UX", ProjectMemberTable.user_id == manager_id
            )
        ).first()
        assert membership is not None
    events = client.get(url("/activity"), params={"project_id": "P-UX"}).json()
    assert any(
        event["entity_type"] == "Project member" and event["action"] == "assigned"
        for event in events
    )
    invalid = client.post(
        url("/projects"),
        json={
            **PROJECT,
            "project_id": "P-UX-INVALID",
            "project_manager_user_id": manager_id,
            "project_manager": "Wrong name",
        },
    )
    assert invalid.status_code == 422
