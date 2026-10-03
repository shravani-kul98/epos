"""Semantic interpretation feeds deterministic retrieval and grounded explanation."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from api.services import copilot_service, semantic_router
from src.config import AI_DISCLAIMER, AzureOpenAISettings
from src.ui_formatting import ANALYSIS_DATE


def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )


def _route(**overrides: Any) -> dict[str, Any]:
    result = {
        "intent": "projects_needing_attention",
        "secondary_intent": None,
        "confidence": "high",
        "project_id": None,
        "project_name": None,
        "change_request_id": None,
        "domain_filter": None,
        "record_type": None,
        "status_filter": None,
        "dependency_id": None,
        "additional_delay_days": None,
        "clarification": None,
    }
    result.update(overrides)
    return result


def _answer(source_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "executive_summary": "Several projects need attention.",
        "key_findings": ["The evidence contains delivery issues requiring review."],
        "recommended_actions": ["Open the cited records before deciding."],
        "source_ids": source_ids or [],
        "human_review_required": True,
        "disclaimer": AI_DISCLAIMER,
    }


def _response(content: object) -> dict:
    return {"choices": [{"message": {"content": json.dumps(content)}}]}


def _dispatch(route: dict[str, Any], answer: dict[str, Any] | None = None):
    calls: list[str] = []

    def send(_url: str, _headers: dict[str, str], body: dict, _timeout: float) -> dict:
        name = body["response_format"]["json_schema"]["name"]
        calls.append(name)
        if name == "epos_semantic_route":
            return _response(route)
        if name in {
            "copilot_response",
            "epos_knowledge_answer",
            "epos_workspace_answer",
        }:
            if answer is not None:
                return _response(answer)
            content = json.loads(body["messages"][1]["content"])
            return _response(_answer(content.get("valid_source_ids", [])[:1]))
        raise AssertionError(f"unexpected schema {name}")

    send.calls = calls
    return send


class TestRequestedExamples:
    def test_what_does_this_application_do(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)
        transport = _dispatch(_route(intent="application_capabilities"))

        result = copilot_service.ask(
            "What does this application do", csv_portfolio, ANALYSIS_DATE, transport=transport
        )

        assert result.status == "ok"
        assert result.matched_intent == "application_capabilities"
        assert result.human_review_required is False
        assert transport.calls == ["epos_semantic_route"]

    def test_whats_happening_is_classified_then_answered_from_engine_evidence(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _dispatch(_route(intent="projects_needing_attention"))

        result = copilot_service.ask(
            "whats happening", csv_portfolio, ANALYSIS_DATE, transport=transport
        )

        assert result.status == "ok"
        assert result.matched_intent == "projects_needing_attention"
        assert result.human_review_required is True
        assert result.evidence
        assert transport.calls == ["epos_semantic_route", "copilot_response"]

    def test_domain_filtered_projects_are_selected_by_python(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _dispatch(
            _route(
                intent="list_projects",
                confidence="medium",
                domain_filter="engineering",
            )
        )

        result = copilot_service.ask(
            "list projects from the domaain of engineering only",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=transport,
        )

        assert result.status == "ok"
        assert result.matched_intent == "list_projects"
        assert result.human_review_required is False
        assert set(result.source_ids) == {"P-007", "P-031"}
        assert {item.fields["domain"] for item in result.evidence} == {
            "Digital Engineering",
            "Test Engineering",
        }
        assert transport.calls == ["epos_semantic_route"]

    def test_generic_record_question_is_classified_selected_and_grounded(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _dispatch(
            _route(
                intent="workspace_evidence",
                project_id="P-002",
                record_type="risk",
            )
        )

        result = copilot_service.ask(
            "Show every risk for P-002",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=transport,
        )

        assert result.status == "ok"
        assert result.matched_intent == "workspace_evidence"
        assert result.human_review_required is True
        assert set(transport.calls) == {"epos_semantic_route", "epos_workspace_answer"}

    def test_scenario_question_routes_to_the_deterministic_engine(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _dispatch(
            _route(
                intent="scenario_analysis",
                dependency_id="D-2001",
                additional_delay_days=10,
            )
        )

        result = copilot_service.ask(
            "What if dependency D-2001 slips by 10 days?",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=transport,
            can_run_scenarios=True,
        )

        assert result.status == "ok"
        assert result.matched_intent == "scenario_analysis"
        assert result.human_review_required is False
        assert result.source_ids[0] == "SCENARIO-D-2001-10D"
        assert transport.calls == ["epos_semantic_route"]

    def test_project_comparison_keeps_the_users_exact_instruction(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        captured: dict[str, object] = {}

        def send(_url, _headers, body, _timeout):
            name = body["response_format"]["json_schema"]["name"]
            if name == "epos_semantic_route":
                return _response(_route(intent="projects_needing_attention"))
            captured.update(json.loads(body["messages"][1]["content"]))
            return _response(_answer())

        question = "Compare the health and confidence of P-002 versus P-007"
        result = copilot_service.ask(
            question,
            csv_portfolio,
            ANALYSIS_DATE,
            transport=send,
        )

        assert result.matched_intent == "projects_needing_attention"
        assert captured["question"] == question
        assert captured["canonical_question"] == "Which projects need attention this week?"


class TestComposition:
    def test_two_record_questions_are_answered_independently(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _dispatch(
            _route(
                intent="blocked_work",
                secondary_intent="portfolio_capacity",
            )
        )

        result = copilot_service.ask(
            "What is blocked, and also who is overloaded?",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=transport,
        )

        blocked = {task.task_id for task in csv_portfolio.tasks if task.is_blocked}
        overloaded = {
            resource.resource_id
            for resource in csv_portfolio.resources
            if resource.is_overallocated
        }
        assert result.status == "ok"
        assert result.matched_intent == "blocked_work + portfolio_capacity"
        assert set(result.source_ids) == blocked | overloaded
        assert result.human_review_required is False
        assert transport.calls == ["epos_semantic_route"]

    def test_explicit_project_id_beats_a_conflicting_model_selector(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _dispatch(_route(intent="why_project_band", project_id="P-007"), _answer())

        result = copilot_service.ask(
            "Status of P-002 only", csv_portfolio, ANALYSIS_DATE, transport=transport
        )

        assert result.matched_intent == "why_project_band"
        assert any(record.record_id == "P-002" for record in result.evidence)

    def test_an_invented_required_project_cannot_reach_the_answer_model(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _dispatch(_route(intent="why_project_band", project_id="P-9999"))

        result = copilot_service.ask(
            "How is the Atlantis programme?",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=transport,
        )

        assert result.status == "clarification"
        assert result.source_ids == []
        assert transport.calls == ["epos_semantic_route"]

    def test_malformed_semantic_output_does_not_drop_an_unresolved_filter(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)

        def malformed(_url, _headers, _body, _timeout):
            return {"choices": [{"message": {"content": "not json"}}]}

        result = copilot_service.ask(
            "list projects from the domain only", csv_portfolio, ANALYSIS_DATE, transport=malformed
        )

        assert result.status == "ok"
        assert result.matched_intent == "list_projects"
        assert result.source_ids == []
        # The unresolved filter must be reported, not widened into "here is everything".
        assert "so no projects are listed" in result.executive_summary
        for domain in sorted({project.domain for project in csv_portfolio.projects}):
            assert domain in result.executive_summary

    def test_known_domain_filter_survives_a_semantic_transport_failure(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)

        def fail(_url, _headers, _body, _timeout):
            raise TimeoutError("simulated")

        result = copilot_service.ask(
            "list projects from engineering only",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=fail,
        )

        assert set(result.source_ids) == {"P-007", "P-031"}

    def test_semantic_interpretation_never_mutates_the_portfolio(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        before = copy.deepcopy(csv_portfolio)
        transport = _dispatch(_route(intent="list_projects", domain_filter="engineering"))

        copilot_service.ask(
            "list projects from engineering only",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=transport,
        )

        for collection in (
            "projects",
            "milestones",
            "tasks",
            "risks",
            "requirements",
            "change_requests",
        ):
            assert [item.model_dump() for item in getattr(csv_portfolio, collection)] == [
                item.model_dump() for item in getattr(before, collection)
            ]

    def test_out_of_scope_is_helpful_not_confident(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)
        transport = _dispatch(_route(intent=semantic_router.OUT_OF_SCOPE))

        result = copilot_service.ask(
            "recommend a restaurant near me",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=transport,
        )

        assert result.status == "clarification"
        assert result.matched_intent is None
        assert "outside EPOS" in result.executive_summary
        assert result.suggested_questions

    def test_an_architecture_question_uses_grounded_documentation(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _dispatch(_route(intent=semantic_router.EPOS_KNOWLEDGE))

        result = copilot_service.ask(
            "How is the application architecture organised?",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=transport,
        )

        assert result.status == "ok"
        assert result.matched_intent == semantic_router.EPOS_KNOWLEDGE
        assert result.human_review_required is True
        assert result.source_ids
        assert all(source_id.startswith(("DOC-", "META-")) for source_id in result.source_ids)
        assert transport.calls[-1] == "epos_knowledge_answer"

    def test_a_follow_up_uses_bounded_conversation_context(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        captured: dict[str, object] = {}

        def send(_url, _headers, body, _timeout):
            name = body["response_format"]["json_schema"]["name"]
            content = json.loads(body["messages"][1]["content"])
            if name == "epos_semantic_route":
                captured.update(content)
                return _response(_route(intent="why_project_band", project_id="P-002"))
            return _response(_answer())

        history = [
            {
                "role": "user",
                "content": "Which projects need attention?",
                "matched_intent": None,
                "source_ids": None,
            },
            {
                "role": "assistant",
                "content": None,
                "matched_intent": "projects_needing_attention",
                "source_ids": "P-002,P-007",
            },
        ]
        result = copilot_service.ask(
            "What about that project?",
            csv_portfolio,
            ANALYSIS_DATE,
            transport=send,
            conversation_context=history,
        )

        assert result.matched_intent == "why_project_band"
        assert captured["recent_conversation"] == history
        assert any(record.record_id == "P-002" for record in result.evidence)
