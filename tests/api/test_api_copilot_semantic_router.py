"""Azure-assisted intent classification stays narrow, validated, and optional."""

from __future__ import annotations

import json
from typing import Any

import pytest

from api.services import semantic_router
from src.config import AzureOpenAISettings


def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )


def _content(**overrides: Any) -> dict[str, Any]:
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


def _transport(content: object):
    def send(_url: str, _headers: dict[str, str], _body: dict, _timeout: float) -> dict:
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    return send


class TestPayload:
    def test_the_model_can_only_choose_an_allowlisted_intent(self, csv_portfolio) -> None:
        payload = semantic_router.build_route_payload("what is happening", csv_portfolio, None, {})
        schema = payload["response_format"]["json_schema"]

        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["properties"]["intent"]["enum"]) == set(
            semantic_router._ALLOWED_INTENTS
        )

    def test_the_payload_contains_vocabulary_not_project_analysis(self, csv_portfolio) -> None:
        payload = semantic_router.build_route_payload(
            "list engineering projects", csv_portfolio, "list_projects", {}
        )
        content = json.loads(payload["messages"][1]["content"])

        assert content["question"] == "list engineering projects"
        assert set(content["known_domains"]) == {
            project.domain for project in csv_portfolio.projects
        }
        assert {item["project_id"] for item in content["known_projects"]} == set(
            csv_portfolio.project_ids
        )
        assert "health_score" not in payload["messages"][1]["content"]

    def test_the_prompt_forbids_answering_and_calculation(self, csv_portfolio) -> None:
        payload = semantic_router.build_route_payload("why is P-002 red", csv_portfolio, None, {})
        prompt = payload["messages"][0]["content"]

        assert "Do not answer" in prompt
        assert "Do not calculate" in prompt
        assert "Never invent" in prompt


class TestValidation:
    def test_a_high_confidence_route_is_usable(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)
        result = semantic_router.interpret(
            "what is happening", csv_portfolio, None, {}, _transport(_content())
        )

        assert result.is_usable_with(None)
        assert result.intent == "projects_needing_attention"

    def test_medium_confidence_is_usable_when_local_routing_agrees(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        result = semantic_router.interpret(
            "list engineering projects",
            csv_portfolio,
            "list_projects",
            {},
            _transport(
                _content(intent="list_projects", confidence="medium", domain_filter="engineering")
            ),
        )

        assert result.is_usable_with("list_projects")
        assert result.domain_filter == "Digital Engineering|Test Engineering"

    def test_medium_confidence_cannot_override_a_conflicting_local_route(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        result = semantic_router.interpret(
            "list projects",
            csv_portfolio,
            "list_projects",
            {},
            _transport(_content(intent="my_tasks", confidence="medium")),
        )

        assert not result.is_usable_with("list_projects")

    def test_an_invented_project_is_removed(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)
        result = semantic_router.interpret(
            "status of Atlantis",
            csv_portfolio,
            None,
            {},
            _transport(_content(intent="why_project_band", project_id="P-9999")),
        )

        assert result.project_id is None
        assert any("outside the current portfolio" in warning for warning in result.warnings)

    def test_an_invented_change_request_is_removed(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)
        result = semantic_router.interpret(
            "impact of the made up change",
            csv_portfolio,
            None,
            {},
            _transport(_content(intent="change_request_impact", change_request_id="CR-9999")),
        )

        assert result.change_request_id is None
        assert any("unknown change request" in warning for warning in result.warnings)

    def test_an_unknown_domain_is_removed(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)
        result = semantic_router.interpret(
            "projects in astronomy",
            csv_portfolio,
            None,
            {},
            _transport(_content(intent="list_projects", domain_filter="Astronomy")),
        )

        assert result.domain_filter is None
        assert any("outside the current portfolio" in warning for warning in result.warnings)

    def test_scenario_inputs_are_validated_against_records_and_engine_bounds(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        result = semantic_router.interpret(
            "What if D-2001 slips by 10 days?",
            csv_portfolio,
            None,
            {},
            _transport(
                _content(
                    intent="scenario_analysis",
                    dependency_id="D-2001",
                    additional_delay_days=10,
                )
            ),
        )

        assert result.dependency_id == "D-2001"
        assert result.additional_delay_days == 10

    def test_invented_or_out_of_range_scenario_inputs_are_removed(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        result = semantic_router.interpret(
            "What if the unknown dependency slips by 9999 days?",
            csv_portfolio,
            None,
            {},
            _transport(
                _content(
                    intent="scenario_analysis",
                    dependency_id="D-9999",
                    additional_delay_days=9999,
                )
            ),
        )

        assert result.dependency_id is None
        assert result.additional_delay_days is None
        assert any("unknown dependency" in warning for warning in result.warnings)
        assert any("supported range" in warning for warning in result.warnings)

    def test_a_project_name_resolves_only_on_an_exact_unique_match(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        name = csv_portfolio.projects[0].project_name
        result = semantic_router.interpret(
            f"how is {name}",
            csv_portfolio,
            None,
            {},
            _transport(_content(intent="why_project_band", project_name=name)),
        )

        assert result.project_id == csv_portfolio.projects[0].project_id

    @pytest.mark.parametrize(
        "invalid",
        [
            "not json",
            json.dumps({"intent": "invented"}),
            json.dumps(_content(intent="invented")),
            json.dumps(_content(confidence="certain")),
        ],
    )
    def test_malformed_or_outside_output_is_rejected(
        self, invalid: str, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)

        def send(_url, _headers, _body, _timeout):
            return {"choices": [{"message": {"content": invalid}}]}

        result = semantic_router.interpret("what is happening", csv_portfolio, None, {}, send)

        assert result.status == "invalid_response"
        assert result.intent is None

    def test_a_transport_failure_becomes_a_safe_result(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)

        def fail(_url, _headers, _body, _timeout):
            raise TimeoutError("simulated")

        result = semantic_router.interpret("what is happening", csv_portfolio, None, {}, fail)

        assert result.status == "error"
        assert result.intent is None
        assert "TimeoutError" in result.warnings[0]

    def test_unconfigured_azure_is_not_an_exception(self, csv_portfolio, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.ai_assistant.get_azure_settings",
            lambda: AzureOpenAISettings(api_key=None, endpoint=None),
        )

        result = semantic_router.interpret("what is happening", csv_portfolio, None, {})

        assert result.status == "unavailable"
        assert result.intent is None


class TestWhenUsed:
    def test_unmatched_language_uses_semantic_interpretation(self) -> None:
        assert semantic_router.should_interpret("what is happening", None)

    def test_a_domain_modifier_uses_semantic_interpretation(self) -> None:
        assert semantic_router.should_interpret(
            "list projects from the engineering domain only", "list_projects"
        )

    def test_an_obvious_unmodified_lookup_stays_local(self) -> None:
        assert not semantic_router.should_interpret("list projects", "list_projects")

    def test_project_comparison_uses_semantic_interpretation(self) -> None:
        assert semantic_router.should_interpret("Compare P-002 versus P-007", "why_project_band")

    def test_a_guessed_local_match_uses_semantic_interpretation(self) -> None:
        # "What should I plan next?" scores only on the word "project" and would otherwise be
        # answered as a request to list projects.
        assert semantic_router.should_interpret(
            "what should i plan for the radar project and what is my next step",
            "list_projects",
            False,
            1,
        )

    def test_a_strong_local_match_still_stays_local(self) -> None:
        assert not semantic_router.should_interpret("list projects", "list_projects", False, 2)
