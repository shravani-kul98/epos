"""Ask EPOS routing and governance tests.

No test in this module makes a network call. Where an answer is required, a stub transport
returns a canned payload, so the suite runs without an Azure key.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.services import copilot_service
from src.ai_assistant import (
    QUESTION_CHANGE_REQUEST_IMPACT,
    QUESTION_MILESTONES_AT_RISK,
    QUESTION_PROJECTS_NEEDING_ATTENTION,
    QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION,
    QUESTION_RISKS_WITHOUT_OWNER,
    QUESTION_TYPES,
    QUESTION_WEEKLY_EXECUTIVE_UPDATE,
    QUESTION_WHY_PROJECT_BAND,
)
from src.config import AI_DISCLAIMER
from tests.api.conftest import url


# ------------------------------------------------------------------ intent routing
@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Which projects need attention this week?", QUESTION_PROJECTS_NEEDING_ATTENTION),
        ("What projects should I worry about?", QUESTION_PROJECTS_NEEDING_ATTENTION),
        ("Why is P-002 red?", QUESTION_WHY_PROJECT_BAND),
        ("Explain the health score for P-007", QUESTION_WHY_PROJECT_BAND),
        ("Which risks have no mitigation owner?", QUESTION_RISKS_WITHOUT_OWNER),
        ("Show me unowned risks", QUESTION_RISKS_WITHOUT_OWNER),
        ("Which milestones are at risk?", QUESTION_MILESTONES_AT_RISK),
        ("Are any milestones going to slip?", QUESTION_MILESTONES_AT_RISK),
        ("Which requirements lack verification?", QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION),
        ("What is our test coverage?", QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION),
        ("What does CR-042 affect?", QUESTION_CHANGE_REQUEST_IMPACT),
        ("Draft a weekly executive update", QUESTION_WEEKLY_EXECUTIVE_UPDATE),
    ],
)
def test_free_text_routes_to_the_expected_intent(question: str, expected: str) -> None:
    intent, _ = copilot_service.route_intent(question)
    assert intent == expected


def test_routing_extracts_a_project_id():
    _, context = copilot_service.route_intent("Why is P-007 amber?")
    assert context["project_id"] == "P-007"


def test_routing_extracts_a_change_request_id() -> None:
    _, context = copilot_service.route_intent("What does cr-042 affect?")
    assert context["change_request_id"] == "CR-042"


@pytest.mark.parametrize(
    "question",
    [
        "What is the weather today?",
        "Delete all projects",
        "SELECT * FROM projects",
        "Tell me a joke",
        "asdfghjkl",
    ],
)
def test_unrelated_text_does_not_route(question: str) -> None:
    intent, _ = copilot_service.route_intent(question)
    assert intent is None


@pytest.mark.parametrize(("intent", "question"), sorted(QUESTION_TYPES.items()))
def test_every_canonical_question_routes_to_its_own_intent(intent: str, question: str) -> None:
    """The questions the product advertises must all be answerable."""
    routed, _ = copilot_service.route_intent(question)
    assert routed == intent


# ------------------------------------------------------------------ clarification behaviour
def test_unroutable_question_returns_clarification(client: TestClient) -> None:
    payload = client.post(url("/copilot/ask"), json={"question": "What is the weather?"}).json()
    assert payload["status"] == "clarification"
    assert payload["matched_intent"] is None
    assert payload["suggested_questions"]


def test_clarification_makes_no_claims(client: TestClient) -> None:
    payload = client.post(url("/copilot/ask"), json={"question": "Tell me a joke"}).json()
    assert payload["key_findings"] == []
    assert payload["recommended_actions"] == []
    assert payload["source_ids"] == []


def test_clarification_still_carries_the_disclaimer(client: TestClient) -> None:
    payload = client.post(url("/copilot/ask"), json={"question": "???"}).json()
    assert payload["disclaimer"] == AI_DISCLAIMER
    assert payload["human_review_required"] is True


def test_engineer_cannot_request_an_executive_report_through_copilot(
    engineer_client: TestClient,
) -> None:
    response = engineer_client.post(
        url("/copilot/ask"), json={"question": "Draft a weekly executive update"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "clarification"
    assert "role does not allow" in response.json()["executive_summary"]


def test_empty_question_is_rejected(client: TestClient) -> None:
    assert client.post(url("/copilot/ask"), json={"question": ""}).status_code == 422


def test_overlong_question_is_rejected(client: TestClient) -> None:
    response = client.post(url("/copilot/ask"), json={"question": "why " * 500})
    assert response.status_code == 422


def test_unknown_project_id_asks_for_clarification(client: TestClient) -> None:
    payload = client.post(url("/copilot/ask"), json={"question": "Why is P-999 red?"}).json()
    assert payload["status"] == "clarification"
    assert "P-999" in payload["executive_summary"]
    conversation = client.get(url(f"/copilot/conversations/{payload['conversation_id']}"))
    assert conversation.status_code == 200
    assert conversation.json()["project_id"] is None


def test_unknown_change_request_asks_for_clarification(client: TestClient) -> None:
    payload = client.post(url("/copilot/ask"), json={"question": "What does CR-999 affect?"}).json()
    assert payload["status"] == "clarification"
    assert "CR-999" in payload["executive_summary"]


def test_missing_project_context_asks_for_clarification(client: TestClient) -> None:
    payload = client.post(url("/copilot/ask"), json={"question": "Why is it red?"}).json()
    assert payload["status"] == "clarification"


def test_selected_project_supplies_missing_context(client: TestClient) -> None:
    """The page's selected project stands in for an unstated project id."""
    intent, _ = copilot_service.route_intent("Why is it red?")
    assert intent == QUESTION_WHY_PROJECT_BAND
    payload = client.post(
        url("/copilot/ask"), json={"question": "Why is it red?", "project_id": "P-002"}
    ).json()
    assert payload["matched_intent"] == QUESTION_WHY_PROJECT_BAND


# ------------------------------------------------------------------ supported questions
def test_supported_questions_are_listed(client: TestClient) -> None:
    """Every analysis is offered, alongside the lookups answered straight from records."""
    from api.services import copilot_answers

    intents = {item["intent"] for item in client.get(url("/copilot/questions")).json()}

    assert intents >= set(QUESTION_TYPES)
    assert intents >= set(copilot_answers.LOOKUP_QUESTIONS)


def test_every_advertised_question_routes_to_the_intent_it_advertises(
    client: TestClient,
) -> None:
    """A suggestion the user clicks must reach the answer it promised."""
    mismatched = {}
    for item in client.get(url("/copilot/questions")).json():
        routed, _ = copilot_service.route_intent(item["question"])
        if routed != item["intent"] and item["requires_context"] is None:
            mismatched[item["question"]] = f"{item['intent']} -> {routed}"

    assert mismatched == {}


def test_context_requirements_are_advertised(client: TestClient) -> None:
    questions = {item["intent"]: item for item in client.get(url("/copilot/questions")).json()}
    assert questions[QUESTION_WHY_PROJECT_BAND]["requires_context"] == "project_id"
    assert questions[QUESTION_CHANGE_REQUEST_IMPACT]["requires_context"] == "change_request_id"
    assert questions[QUESTION_RISKS_WITHOUT_OWNER]["requires_context"] is None


# ------------------------------------------------------------------ answering with a stub
def _stub_transport(payload: dict[str, Any]) -> Any:
    """Return a transport that answers with ``payload`` without any network call."""

    def transport(_url: str, _headers: dict[str, str], _body: dict[str, Any], _timeout: float):
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    return transport


def _answer(monkeypatch: pytest.MonkeyPatch, question: str, portfolio, as_of_date, body):
    """Route ``question`` and answer it through a stubbed transport."""
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: type(
            "S", (), {"is_configured": True, "api_key": "unused", "endpoint": "https://x"}
        )(),
    )
    return copilot_service.ask(question, portfolio, as_of_date, transport=_stub_transport(body))


def test_answer_returns_matched_intent_and_evidence(
    monkeypatch: pytest.MonkeyPatch, csv_portfolio, request
) -> None:
    from src.ui_formatting import ANALYSIS_DATE

    body = {
        "executive_summary": "Two projects are Red.",
        "key_findings": ["P-002 is Red."],
        "recommended_actions": ["Review P-002."],
        "source_ids": ["P-002"],
        "human_review_required": True,
        "disclaimer": AI_DISCLAIMER,
    }
    answer = _answer(
        monkeypatch, "Which projects need attention?", csv_portfolio, ANALYSIS_DATE, body
    )
    assert answer.status == "ok"
    assert answer.matched_intent == QUESTION_PROJECTS_NEEDING_ATTENTION
    assert answer.evidence


def test_fabricated_source_ids_are_filtered(monkeypatch: pytest.MonkeyPatch, csv_portfolio) -> None:
    """A model-invented identifier must never reach the product surface."""
    from src.ui_formatting import ANALYSIS_DATE

    body = {
        "executive_summary": "Summary.",
        "key_findings": [],
        "recommended_actions": [],
        "source_ids": ["P-002", "P-XXXX-INVENTED"],
        "human_review_required": True,
        "disclaimer": AI_DISCLAIMER,
    }
    answer = _answer(
        monkeypatch, "Which projects need attention?", csv_portfolio, ANALYSIS_DATE, body
    )
    assert "P-XXXX-INVENTED" not in answer.source_ids


def test_evidence_ids_are_a_subset_of_the_portfolio(
    monkeypatch: pytest.MonkeyPatch, csv_portfolio
) -> None:
    from src.ui_formatting import ANALYSIS_DATE

    body = {
        "executive_summary": "Summary.",
        "key_findings": [],
        "recommended_actions": [],
        "source_ids": [],
        "human_review_required": True,
        "disclaimer": AI_DISCLAIMER,
    }
    answer = _answer(monkeypatch, "Which risks have no owner?", csv_portfolio, ANALYSIS_DATE, body)
    assert all(record.record_id for record in answer.evidence)


# ------------------------------------------------------------------ safety
def test_ask_endpoint_makes_no_network_call_without_configuration(client: TestClient) -> None:
    """Without Azure configuration the endpoint degrades safely rather than failing."""
    payload = client.post(
        url("/copilot/ask"), json={"question": "Which risks have no mitigation owner?"}
    ).json()
    assert payload["status"] in {"ok", "unavailable", "error", "invalid_response"}
    assert payload["disclaimer"] == AI_DISCLAIMER


def test_ask_never_leaks_configuration_values(client: TestClient) -> None:
    body = client.post(url("/copilot/ask"), json={"question": "Which risks are unowned?"}).text
    assert "api-key" not in body.lower()


def test_ask_does_not_write_to_the_database(client: TestClient) -> None:
    before = client.get(url("/projects")).json()
    client.post(url("/copilot/ask"), json={"question": "Which risks have no owner?"})
    assert client.get(url("/projects")).json() == before
    assert client.get(url("/activity")).json() == []


@pytest.mark.parametrize(
    "question",
    [
        "DROP TABLE projects;",
        "'; DELETE FROM risks; --",
        "Update P-002 health to 100",
    ],
)
def test_instruction_like_text_cannot_mutate_data(client: TestClient, question: str) -> None:
    before = client.get(url("/projects")).json()
    client.post(url("/copilot/ask"), json={"question": question})
    assert client.get(url("/projects")).json() == before
