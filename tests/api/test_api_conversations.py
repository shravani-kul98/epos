"""Conversation history and soft-delete behaviour."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Session, select

from api.models import ProjectTable, RiskTable, TaskTable
from tests.api.conftest import url

QUESTION = "Which risks have no mitigation owner?"


# ------------------------------------------------------------------ conversations
def test_asking_starts_a_conversation(client: TestClient) -> None:
    body = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    assert body["conversation_id"] is not None


def test_conversation_appears_in_the_history(client: TestClient) -> None:
    client.post(url("/copilot/ask"), json={"question": QUESTION})
    conversations = client.get(url("/copilot/conversations")).json()
    assert len(conversations) == 1
    assert conversations[0]["message_count"] == 2


def test_conversation_is_titled_from_the_first_question(client: TestClient) -> None:
    client.post(url("/copilot/ask"), json={"question": QUESTION})
    assert client.get(url("/copilot/conversations")).json()[0]["title"] == QUESTION


def test_a_long_question_produces_a_trimmed_title(client: TestClient) -> None:
    client.post(url("/copilot/ask"), json={"question": "Which risks have no owner " * 20})
    title = client.get(url("/copilot/conversations")).json()[0]["title"]
    assert len(title) <= 60


def test_follow_up_continues_the_same_conversation(client: TestClient) -> None:
    first = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    client.post(
        url("/copilot/ask"),
        json={
            "question": "Which milestones are at risk?",
            "conversation_id": first["conversation_id"],
        },
    )
    conversations = client.get(url("/copilot/conversations")).json()
    assert len(conversations) == 1
    assert conversations[0]["message_count"] == 4


def test_conversation_detail_records_both_turns(client: TestClient) -> None:
    created = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    detail = client.get(url(f"/copilot/conversations/{created['conversation_id']}")).json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == QUESTION


def test_conversation_keeps_the_supporting_evidence(client: TestClient) -> None:
    """The source drawer must reopen later without recalculating or re-asking."""
    created = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    detail = client.get(url(f"/copilot/conversations/{created['conversation_id']}")).json()
    assert detail["messages"][1]["evidence"]


def test_routing_history_excludes_model_authored_prose(client: TestClient, session, users) -> None:
    """Generated assistant text must not be recycled as factual context."""
    from api.models import UserTable
    from api.security.permissions import Role
    from api.services import conversation_service

    created = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    user = session.exec(select(UserTable).where(UserTable.email == users[Role.ADMINISTRATOR])).one()
    history = conversation_service.routing_history(session, user, created["conversation_id"])

    assert history[0]["content"] == QUESTION
    assert history[1]["content"] is None
    assert history[1]["matched_intent"]
    assert history[1]["source_ids"]


def test_clarifications_are_recorded_too(client: TestClient) -> None:
    created = client.post(url("/copilot/ask"), json={"question": "Tell me a joke"}).json()
    detail = client.get(url(f"/copilot/conversations/{created['conversation_id']}")).json()
    assert detail["messages"][1]["status"] == "clarification"


def test_a_conversation_can_be_cleared(client: TestClient) -> None:
    created = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    assert (
        client.delete(url(f"/copilot/conversations/{created['conversation_id']}")).status_code
        == 204
    )
    assert client.get(url("/copilot/conversations")).json() == []


def test_conversations_are_private_to_their_owner(
    client: TestClient, pm_client: TestClient
) -> None:
    created = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    conversation_id = created["conversation_id"]

    assert pm_client.get(url("/copilot/conversations")).json() == []
    assert pm_client.get(url(f"/copilot/conversations/{conversation_id}")).status_code == 404
    assert pm_client.delete(url(f"/copilot/conversations/{conversation_id}")).status_code == 404


def test_another_users_conversation_survives_a_refused_delete(
    client: TestClient, pm_client: TestClient
) -> None:
    created = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    pm_client.delete(url(f"/copilot/conversations/{created['conversation_id']}"))
    assert len(client.get(url("/copilot/conversations")).json()) == 1


def test_unknown_conversation_returns_404(client: TestClient) -> None:
    assert client.get(url("/copilot/conversations/9999")).status_code == 404


def test_replying_into_someone_elses_conversation_is_refused(
    client: TestClient, pm_client: TestClient
) -> None:
    created = client.post(url("/copilot/ask"), json={"question": QUESTION}).json()
    response = pm_client.post(
        url("/copilot/ask"),
        json={"question": QUESTION, "conversation_id": created["conversation_id"]},
    )
    assert response.status_code == 404


# ------------------------------------------------------------------ soft delete
def test_deleted_risk_disappears_from_reads(client: TestClient) -> None:
    risk = client.get(url("/risks")).json()[0]
    risk_id = risk["risk_id"]
    client.delete(url(f"/risks/{risk_id}"), params={"row_version": risk["row_version"]})
    assert client.get(url(f"/risks/{risk_id}")).status_code == 404
    assert risk_id not in {row["risk_id"] for row in client.get(url("/risks")).json()}


def test_deleted_risk_is_retained_for_audit(client: TestClient, engine) -> None:
    risk = client.get(url("/risks")).json()[0]
    risk_id = risk["risk_id"]
    client.delete(url(f"/risks/{risk_id}"), params={"row_version": risk["row_version"]})
    with Session(engine) as session:
        row = session.get(RiskTable, risk_id)
    assert row is not None
    assert row.deleted_at is not None


def test_deleting_a_risk_changes_the_analysis(client: TestClient) -> None:
    """A withdrawn record must no longer influence the scores."""
    before = client.get(url("/analytics/projects/P-002/health")).json()["score"]
    for risk in client.get(url("/risks"), params={"project_id": "P-002"}).json():
        client.delete(url(f"/risks/{risk['risk_id']}"), params={"row_version": risk["row_version"]})
    after = client.get(url("/analytics/projects/P-002/health")).json()["score"]
    assert after != before


def test_deleting_a_project_withdraws_its_children(client: TestClient) -> None:
    project = client.get(url("/projects/P-002")).json()
    client.delete(url("/projects/P-002"), params={"row_version": project["row_version"]})
    assert client.get(url("/tasks"), params={"project_id": "P-002"}).json() == []
    assert client.get(url("/risks"), params={"project_id": "P-002"}).json() == []


def test_deleted_project_leaves_the_portfolio(client: TestClient, csv_portfolio) -> None:
    project = client.get(url("/projects/P-002")).json()
    client.delete(url("/projects/P-002"), params={"row_version": project["row_version"]})
    payload = client.get(url("/analytics/portfolio")).json()
    remaining = set(csv_portfolio.project_ids) - {"P-002"}
    assert {row["project_id"] for row in payload["projects"]} == remaining


def test_a_withdrawn_identifier_cannot_be_reused(client: TestClient) -> None:
    """Reusing an identifier would silently change what historic audit rows refer to."""
    risk = client.get(url("/risks")).json()[0]
    client.delete(url(f"/risks/{risk['risk_id']}"), params={"row_version": risk["row_version"]})
    response = client.post(
        url("/risks"),
        json={
            "risk_id": risk["risk_id"],
            "project_id": risk["project_id"],
            "risk_name": "Reused identifier",
            "probability": 1,
            "impact": 1,
            "status": "Open",
            "due_date": "2026-12-01",
        },
    )
    assert response.status_code == 409


def test_a_withdrawn_milestone_cannot_be_referenced(client: TestClient) -> None:
    milestone = client.get(url("/milestones")).json()[0]
    milestone_id = milestone["milestone_id"]
    client.delete(
        url(f"/milestones/{milestone_id}"),
        params={"row_version": milestone["row_version"]},
    )
    task = client.get(url("/tasks"), params={"project_id": "P-002"}).json()[0]
    response = client.patch(
        url(f"/tasks/{task['task_id']}"),
        json={"milestone_id": milestone_id, "row_version": task["row_version"]},
    )
    assert response.status_code == 422


# ------------------------------------------------------------------ audit provenance
def test_creating_a_record_stores_who_made_it(pm_client: TestClient, engine) -> None:
    pm_client.post(
        url("/projects"),
        json={
            "project_id": "P-960",
            "project_name": "Provenance Check",
            "domain": "Validation",
            "project_manager": "A. Engineer",
            "start_date": "2026-02-01",
            "project_phase": "Design",
            "business_priority": "Medium",
        },
    )
    from api.models import ProjectTable

    with Session(engine) as session:
        row = session.get(ProjectTable, "P-960")
    assert row is not None
    assert row.created_by == "pm@test.example.com"


def test_updating_a_record_stores_who_changed_it(
    engineer_client: TestClient, client: TestClient, engine
) -> None:
    milestone = client.get(url("/projects/P-002/milestones")).json()[0]
    task = client.post(
        url("/tasks"),
        json={
            "task_id": "T-PROVENANCE",
            "project_id": "P-002",
            "milestone_id": milestone["milestone_id"],
            "task_name": "Provenance probe",
            "owner": "Test Engineer",
            "status": "In Progress",
            "planned_end_date": "2026-10-01",
            "forecast_end_date": "2026-10-01",
            "completion_percent": 0,
        },
    ).json()
    task_id = task["task_id"]
    response = engineer_client.patch(
        url(f"/tasks/{task_id}"),
        json={"completion_percent": 80, "row_version": task["row_version"]},
    )
    assert response.status_code == 200
    with Session(engine) as session:
        row = session.get(TaskTable, task_id)
    assert row is not None
    assert row.updated_by == "engineer@test.example.com"


def test_concurrent_updates_use_an_atomic_version_predicate(seeded_engine) -> None:
    with Session(seeded_engine) as first_session, Session(seeded_engine) as second_session:
        first = first_session.get(ProjectTable, "P-002")
        second = second_session.get(ProjectTable, "P-002")
        assert first is not None
        assert second is not None

        first.project_phase = "Verification"
        first.row_version += 1
        second.domain = "Synthetic concurrent overwrite"
        second.row_version += 1

        first_session.commit()
        with pytest.raises(StaleDataError):
            second_session.commit()


def test_activity_names_the_person_responsible(pm_client: TestClient) -> None:
    project = pm_client.get(url("/projects/P-002")).json()
    pm_client.patch(
        url("/projects/P-002"),
        json={"project_phase": "Verification", "row_version": project["row_version"]},
    )
    event = pm_client.get(url("/activity")).json()[0]
    assert event["actor_name"] == "Test Project Manager"
    assert event["headline"].startswith("Test Project Manager ")


def test_activity_reads_as_a_sentence(pm_client: TestClient) -> None:
    """The feed must read as prose, not as a database event."""
    project = pm_client.get(url("/projects/P-002")).json()
    name = project["project_name"]
    pm_client.patch(
        url("/projects/P-002"),
        json={"project_phase": "Verification", "row_version": project["row_version"]},
    )
    headline = pm_client.get(url("/activity")).json()[0]["headline"]
    assert "_" not in headline
    assert headline == f"Test Project Manager updated project {name}"
