"""Database-backed conversation and project identity regressions without live AI calls."""

from __future__ import annotations

import copy
import json

from api.services import copilot_service
from src.ai_assistant import QUESTION_WHY_PROJECT_BAND, build_evidence_package
from src.config import AI_DISCLAIMER, AzureOpenAISettings
from src.ui_formatting import ANALYSIS_DATE
from tests.api.conftest import url


def test_project_health_evidence_carries_the_database_name(csv_portfolio):
    evidence = build_evidence_package(
        QUESTION_WHY_PROJECT_BAND, csv_portfolio, ANALYSIS_DATE, {"project_id": "P-002"}
    )
    project = csv_portfolio.get_project("P-002")
    assert project is not None
    for record in evidence.records:
        assert record.fields["project_id"] == project.project_id
        assert record.fields["project_name"] == project.project_name


def test_name_based_question_narrows_to_one_project(csv_portfolio):
    portfolio = copy.deepcopy(csv_portfolio)
    portfolio.projects = [
        (
            project.model_copy(update={"project_name": "Humanoid Atlas"})
            if project.project_id == "P-002"
            else project
        )
        for project in portfolio.projects
    ]
    answer = copilot_service.ask("Explain Humanoid Atlas project", portfolio, ANALYSIS_DATE)
    assert answer.matched_intent == QUESTION_WHY_PROJECT_BAND
    assert answer.resolved_project_id == "P-002"
    assert any(record.fields.get("project_name") == "Humanoid Atlas" for record in answer.evidence)


def test_known_nonstandard_project_identifier_is_not_misread(csv_portfolio):
    portfolio = copy.deepcopy(csv_portfolio)
    project = portfolio.projects[0].model_copy(
        update={"project_id": "HP-9062", "project_name": "Humanoid Atlas"}
    )
    portfolio.projects.append(project)
    answer = copilot_service.ask("Explain HP-9062 project", portfolio, ANALYSIS_DATE)
    assert answer.matched_intent == QUESTION_WHY_PROJECT_BAND
    assert answer.resolved_project_id == "HP-9062"


def test_model_prose_uses_recorded_names_without_changing_source_ids(csv_portfolio, monkeypatch):
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )

    def send(_url, _headers, _payload, _timeout):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "executive_summary": "Review P-002.",
                                "key_findings": ["P-002 needs review."],
                                "recommended_actions": [],
                                "source_ids": ["P-002"],
                                "human_review_required": True,
                                "disclaimer": AI_DISCLAIMER,
                            }
                        )
                    }
                }
            ]
        }

    answer = copilot_service.ask("Why is P-002 red?", csv_portfolio, ANALYSIS_DATE, transport=send)
    assert csv_portfolio.get_project("P-002").project_name in answer.executive_summary
    assert answer.source_ids == ["P-002"]


def test_follow_up_retains_project_without_requiring_azure(client):
    first = client.post(url("/copilot/ask"), json={"question": "Why is P-002 red?"}).json()
    second = client.post(
        url("/copilot/ask"),
        json={"question": "Why is it red?", "conversation_id": first["conversation_id"]},
    ).json()
    assert second["status"] != "clarification"
    assert second["matched_intent"] == QUESTION_WHY_PROJECT_BAND
    assert {record["fields"].get("project_id") for record in second["evidence"]} == {"P-002"}


def test_saved_conversation_restores_complete_answer(client):
    answer = client.post(url("/copilot/ask"), json={"question": "List projects"}).json()
    detail = client.get(url(f"/copilot/conversations/{answer['conversation_id']}")).json()
    restored = detail["messages"][1]["answer"]
    assert restored["key_findings"] == answer["key_findings"]
    assert restored["recommended_actions"] == answer["recommended_actions"]
    assert restored["disclaimer"] == answer["disclaimer"]
    assert restored["human_review_required"] == answer["human_review_required"]


def test_switching_project_updates_follow_up_scope(client):
    first = client.post(url("/copilot/ask"), json={"question": "Why is P-002 red?"}).json()
    cid = first["conversation_id"]
    client.post(url("/copilot/ask"), json={"question": "What about P-007?", "conversation_id": cid})
    third = client.post(
        url("/copilot/ask"), json={"question": "Why is it amber?", "conversation_id": cid}
    ).json()
    assert third["context"]["project_id"] == "P-007"
    assert {record["fields"].get("project_id") for record in third["evidence"]} == {"P-007"}


def test_explicit_portfolio_scope_does_not_reuse_old_project(client):
    first = client.post(url("/copilot/ask"), json={"question": "Why is P-002 red?"}).json()
    answer = client.post(
        url("/copilot/ask"),
        json={
            "question": "Which projects need attention across the portfolio?",
            "conversation_id": first["conversation_id"],
        },
    ).json()
    assert answer["matched_intent"] == "projects_needing_attention"
    assert "project_id" not in answer["context"]
    assert len(answer["project_references"]) > 1


def test_saved_history_is_rechecked_after_membership_revocation(pm_client, session, users):
    from sqlmodel import select

    from api.models import ProjectMemberTable, UserTable
    from api.security.permissions import Role

    answer = pm_client.post(url("/copilot/ask"), json={"question": "Why is P-002 red?"}).json()
    user = session.exec(
        select(UserTable).where(UserTable.email == users[Role.PROJECT_MANAGER])
    ).one()
    membership = session.exec(
        select(ProjectMemberTable).where(
            ProjectMemberTable.user_id == user.id, ProjectMemberTable.project_id == "P-002"
        )
    ).one()
    session.delete(membership)
    session.commit()
    assert (
        pm_client.get(url(f"/copilot/conversations/{answer['conversation_id']}")).status_code == 404
    )
    assert (
        pm_client.post(
            url("/copilot/ask"),
            json={"question": "Why is it red?", "conversation_id": answer["conversation_id"]},
        ).status_code
        == 404
    )


def test_history_context_does_not_promote_old_answer_prose_into_evidence(csv_portfolio):
    from src.ai_assistant import build_request_payload

    evidence = build_evidence_package(
        QUESTION_WHY_PROJECT_BAND, csv_portfolio, ANALYSIS_DATE, {"project_id": "P-002"}
    )
    payload = build_request_payload(
        evidence,
        "What should I review?",
        [{"role": "assistant", "content": "Invented prior promise", "project_id": "P-002"}],
    )
    sent = json.loads(payload["messages"][1]["content"])
    assert sent["recent_reference_context"][0]["content"] is None
    assert "Invented prior promise" not in json.dumps(sent)


def test_follow_up_reloads_current_database_records(client, session):
    from api.models import ProjectTable

    first = client.post(url("/copilot/ask"), json={"question": "Why is P-002 red?"}).json()
    project = session.get(ProjectTable, "P-002")
    project.project_name = "Revised synthetic programme"
    session.add(project)
    session.commit()
    answer = client.post(
        url("/copilot/ask"),
        json={"question": "Why is it red?", "conversation_id": first["conversation_id"]},
    ).json()
    assert "Revised synthetic programme" in answer["executive_summary"]


def test_generic_risk_follow_up_returns_all_project_risks(client):
    first = client.post(url("/copilot/ask"), json={"question": "Explain P-002"}).json()
    answer = client.post(
        url("/copilot/ask"),
        json={"question": "What risks does it have?", "conversation_id": first["conversation_id"]},
    ).json()
    risks = client.get(url("/risks"), params={"project_id": "P-002"}).json()
    assert answer["matched_intent"] == "workspace_evidence"
    assert {item["risk_id"] for item in risks} <= set(answer["source_ids"])
    assert answer["context"]["project_id"] == "P-002"


def test_attention_fallback_is_concise_and_keeps_raw_citation_identifiers(csv_portfolio):
    answer = copilot_service.ask("Which projects are at risk?", csv_portfolio, ANALYSIS_DATE)
    summaries = [record for record in answer.evidence if record.record_type == "project_summary"]
    assert len(answer.key_findings) == len(summaries)
    for finding in answer.key_findings:
        if "Main signal:" in finding:
            assert any(f"[{source_id}]" in finding for source_id in answer.source_ids)
