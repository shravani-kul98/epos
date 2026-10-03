"""AI may explain deterministic scenarios but cannot replace or alter their facts."""

from __future__ import annotations

import json
from typing import Any

import pytest

from api.services import analytics_service, scenario_explanation
from src.config import AI_DISCLAIMER, AzureOpenAISettings
from tests.api.conftest import ANALYSIS_DATE


def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )


def _response(**overrides: Any) -> dict[str, Any]:
    result = {
        "executive_summary": "Completion moves later; review the recorded propagation path.",
        "key_findings": ["The deterministic scenario moved a recorded completion date."],
        "recommended_actions": ["Review the controlling dependency with its owner."],
        "source_ids": ["SCENARIO-D-2002-90D"],
        "human_review_required": True,
        "disclaimer": AI_DISCLAIMER,
    }
    result.update(overrides)
    return result


def _transport(content: object):
    def send(_url: str, _headers: dict[str, str], _body: dict, _timeout: float) -> dict:
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    return send


@pytest.fixture
def scenario(csv_portfolio):
    return analytics_service.run_scenario("D-2002", 90, csv_portfolio, ANALYSIS_DATE)


def test_a_grounded_explanation_is_returned(
    scenario, csv_portfolio, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configured(monkeypatch)

    answer = scenario_explanation.explain(scenario, csv_portfolio, _transport(_response()))

    assert answer.status == "ok"
    assert answer.human_review_required is True
    assert answer.disclaimer == AI_DISCLAIMER
    assert answer.source_ids == ["SCENARIO-D-2002-90D"]
    assert answer.evidence[0].record_type == "deterministic_scenario_result"


def test_a_fabricated_source_id_rejects_all_model_authored_content(
    scenario, csv_portfolio, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configured(monkeypatch)

    answer = scenario_explanation.explain(
        scenario,
        csv_portfolio,
        _transport(
            _response(
                executive_summary="Invented model summary.",
                key_findings=["Invented model finding."],
                source_ids=["FAKE-900"],
            )
        ),
    )

    assert answer.status == "invalid_response"
    assert "Invented model summary" not in answer.executive_summary
    assert "Invented model finding" not in " ".join(answer.key_findings)
    assert "FAKE-900" not in answer.source_ids


def test_an_invented_number_is_rejected_even_with_a_valid_source_id(
    scenario, csv_portfolio, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configured(monkeypatch)

    answer = scenario_explanation.explain(
        scenario,
        csv_portfolio,
        _transport(
            _response(
                executive_summary="Completion moves by 9999 days.",
                source_ids=["SCENARIO-D-2002-90D"],
            )
        ),
    )

    assert answer.status == "invalid_response"
    assert "9999" not in answer.executive_summary
    assert any("numeric claims" in warning for warning in answer.warnings)


def test_the_deterministic_scenario_record_must_be_cited(
    scenario, csv_portfolio, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configured(monkeypatch)
    valid_record_id = next(source_id for source_id in scenario.source_ids if source_id != "P-002")

    answer = scenario_explanation.explain(
        scenario,
        csv_portfolio,
        _transport(_response(source_ids=[valid_record_id])),
    )

    assert answer.status == "invalid_response"
    assert any("deterministic scenario result" in warning for warning in answer.warnings)


def test_malformed_model_output_is_rejected(
    scenario, csv_portfolio, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configured(monkeypatch)

    answer = scenario_explanation.explain(
        scenario, csv_portfolio, _transport({"executive_summary": "incomplete"})
    )

    assert answer.status == "invalid_response"
    assert answer.human_review_required is True


def test_unavailable_ai_preserves_the_deterministic_result(
    scenario, csv_portfolio, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key=None, endpoint=None),
    )

    answer = scenario_explanation.explain(scenario, csv_portfolio)

    assert answer.status == "unavailable"
    assert scenario.explanation in answer.key_findings
    assert answer.evidence[0].fields["calculation_version"] == "2.0"


def test_scenario_content_is_declared_untrusted_data(scenario) -> None:
    evidence = [scenario_explanation._scenario_evidence(scenario)]
    payload = scenario_explanation._payload("Explain it", evidence)
    system = payload["messages"][0]["content"]

    assert "untrusted data" in system
    assert "do not calculate" in system
    assert "do not" in system and "invent" in system


def test_payload_contains_only_calculated_scenario_and_selected_evidence(scenario) -> None:
    evidence = [scenario_explanation._scenario_evidence(scenario)]
    payload = scenario_explanation._payload("Explain it", evidence)
    user_content = json.loads(payload["messages"][1]["content"])

    assert user_content["valid_source_ids"] == ["SCENARIO-D-2002-90D"]
    assert len(user_content["records"]) == 1
    assert user_content["records"][0]["fields"]["calculation_version"] == "2.0"
