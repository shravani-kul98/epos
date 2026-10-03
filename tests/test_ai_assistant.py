"""Tests for the AI explanation layer.

Every test injects a fake transport or patches configuration; no test makes a network call, and
no test reads .env values.
"""

from __future__ import annotations

import copy
import json
from datetime import date

import pytest

from src import ai_assistant as ai
from src.config import AzureOpenAISettings
from src.data_loader import load_portfolio
from src.schemas import CopilotResponse, EvidencePackage
from src.validators import DataValidationError

AS_OF = date(2026, 8, 25)
DISCLAIMER = "AI-generated decision-support draft; human review required."


def _valid_payload(source_ids: list[str]) -> dict:
    return {
        "executive_summary": "Two projects require attention.",
        "key_findings": ["P-007 status is stale."],
        "recommended_actions": ["Request a status update."],
        "source_ids": source_ids,
        "human_review_required": True,
        "disclaimer": DISCLAIMER,
    }


def _transport_returning(payload: dict):
    def _transport(url, headers, body, timeout):
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    return _transport


def _configured(monkeypatch, api_key="present", endpoint="https://example.invalid/chat"):
    monkeypatch.setattr(
        ai, "get_azure_settings", lambda: AzureOpenAISettings(api_key=api_key, endpoint=endpoint)
    )


# ------------------------------------------------------------------ configuration
@pytest.mark.parametrize(
    ("api_key", "endpoint", "missing"),
    [(None, "https://example.invalid", "API_KEY"), ("present", None, "ENDPOINT")],
)
def test_missing_configuration_is_unavailable(portfolio, monkeypatch, api_key, endpoint, missing):
    _configured(monkeypatch, api_key=api_key, endpoint=endpoint)
    result = ai.ask_epos(ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, AS_OF)
    assert result.status == "unavailable"
    assert result.source_ids == []
    assert any(missing in warning for warning in result.warnings)
    # The message names the variable but never a value.
    assert "present" not in " ".join(result.warnings) + result.executive_summary


def test_both_configured_proceeds(portfolio, monkeypatch):
    _configured(monkeypatch)
    package = ai.build_evidence_package(ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, AS_OF)
    result = ai.ask_epos(
        ai.QUESTION_RISKS_WITHOUT_OWNER,
        portfolio,
        AS_OF,
        transport=_transport_returning(_valid_payload([package.source_ids[0]])),
    )
    assert result.status == "ok"


# ------------------------------------------------------------------ evidence packages
@pytest.mark.parametrize(
    ("question_type", "context"),
    [
        (ai.QUESTION_PROJECTS_NEEDING_ATTENTION, None),
        (ai.QUESTION_WHY_PROJECT_BAND, {"project_id": "P-007"}),
        (ai.QUESTION_RISKS_WITHOUT_OWNER, None),
        (ai.QUESTION_MILESTONES_AT_RISK, None),
        (ai.QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION, None),
        (ai.QUESTION_CHANGE_REQUEST_IMPACT, {"change_request_id": "CR-042"}),
        (ai.QUESTION_WEEKLY_EXECUTIVE_UPDATE, None),
    ],
)
def test_evidence_package_builds_for_every_question_type(portfolio, question_type, context):
    package = ai.build_evidence_package(question_type, portfolio, AS_OF, context)
    assert isinstance(package, EvidencePackage)
    assert package.question_type == question_type
    assert package.records
    assert package.source_ids == sorted(set(package.source_ids))


def test_why_project_band_is_scoped_to_one_project(portfolio):
    package = ai.build_evidence_package(
        ai.QUESTION_WHY_PROJECT_BAND, portfolio, AS_OF, {"project_id": "P-007"}
    )
    assert package.source_ids == ["P-007"]
    joined = json.dumps([r.model_dump() for r in package.records])
    assert "P-002" not in joined


def test_risks_without_owner_includes_underlying_risks(portfolio):
    package = ai.build_evidence_package(ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, AS_OF)
    types = {record.record_type for record in package.records}
    assert types == {"alert", "risk"}

    risk_ids = {r.record_id for r in package.records if r.record_type == "risk"}
    unowned = {r.risk_id for r in portfolio.risks if not r.mitigation_owner}
    assert risk_ids, "the question is about unowned risks, so some must be cited"
    # No false positives: every risk offered as evidence genuinely lacks an owner.
    assert risk_ids <= unowned


def test_requirements_without_verification_includes_requirements_and_tests(portfolio):
    package = ai.build_evidence_package(
        ai.QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION, portfolio, AS_OF
    )
    types = {record.record_type for record in package.records}
    assert "requirement" in types
    assert "alert" in types


def test_change_request_impact_evidence(portfolio):
    package = ai.build_evidence_package(
        ai.QUESTION_CHANGE_REQUEST_IMPACT, portfolio, AS_OF, {"change_request_id": "CR-042"}
    )
    assert package.source_ids == ["CR-042"]
    assert package.records[0].fields["requirement_id"] == "REQ-7001"


def test_unsupported_question_type_raises(portfolio):
    with pytest.raises(DataValidationError) as exc:
        ai.build_evidence_package("nonsense", portfolio, AS_OF)
    assert "nonsense" in str(exc.value)


def test_missing_context_raises(portfolio):
    with pytest.raises(DataValidationError) as exc:
        ai.build_evidence_package(ai.QUESTION_WHY_PROJECT_BAND, portfolio, AS_OF)
    assert "project_id" in str(exc.value)


def test_unknown_project_context_raises(portfolio):
    with pytest.raises(DataValidationError) as exc:
        ai.build_evidence_package(
            ai.QUESTION_WHY_PROJECT_BAND, portfolio, AS_OF, {"project_id": "P-NONE"}
        )
    assert "P-NONE" in str(exc.value)


def test_evidence_package_is_deterministic(portfolio):
    first = ai.build_evidence_package(ai.QUESTION_WEEKLY_EXECUTIVE_UPDATE, portfolio, AS_OF)
    second = ai.build_evidence_package(ai.QUESTION_WEEKLY_EXECUTIVE_UPDATE, portfolio, AS_OF)
    assert first.model_dump() == second.model_dump()


# ------------------------------------------------------------------ request building
def test_request_payload_contains_prompt_schema_and_evidence(portfolio):
    package = ai.build_evidence_package(ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, AS_OF)
    payload = ai.build_request_payload(package)

    assert payload["messages"][0]["role"] == "system"
    assert "Use ONLY the supplied evidence records" in payload["messages"][0]["content"]
    assert DISCLAIMER in payload["messages"][0]["content"]
    # json_schema is the mode confirmed working against the real Azure deployment.
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["name"] == "copilot_response"
    assert payload["response_format"]["json_schema"]["schema"] == ai.RESPONSE_SCHEMA
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["temperature"] == 0
    user_content = payload["messages"][1]["content"]
    assert "R-2001" in user_content
    assert "valid_source_ids" in user_content
    # Only the six model-authored fields are requested.
    assert set(ai.RESPONSE_SCHEMA["required"]) == {
        "executive_summary",
        "key_findings",
        "recommended_actions",
        "source_ids",
        "human_review_required",
        "disclaimer",
    }


def test_request_payload_preserves_natural_wording_beside_the_canonical_intent(portfolio):
    package = ai.build_evidence_package(ai.QUESTION_PROJECTS_NEEDING_ATTENTION, portfolio, AS_OF)
    question = "Compare the health and confidence of P-002 versus P-007"

    payload = ai.build_request_payload(package, question)
    content = json.loads(payload["messages"][1]["content"])

    assert content["question"] == question
    assert content["canonical_question"] == ai.QUESTION_TYPES[package.question_type]


# ------------------------------------------------------------------ response handling
def test_successful_response_is_validated(portfolio, monkeypatch):
    _configured(monkeypatch)
    package = ai.build_evidence_package(ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, AS_OF)
    valid_id = package.source_ids[0]
    result = ai.ask_epos(
        ai.QUESTION_RISKS_WITHOUT_OWNER,
        portfolio,
        AS_OF,
        transport=_transport_returning(_valid_payload([valid_id])),
    )
    assert isinstance(result, CopilotResponse)
    assert result.status == "ok"
    assert result.source_ids == [valid_id]
    assert result.disclaimer == DISCLAIMER
    assert result.human_review_required is True
    assert result.warnings == []


@pytest.mark.parametrize(
    "content",
    ["not json at all", json.dumps({"executive_summary": "missing other fields"})],
)
def test_malformed_response_is_handled(portfolio, monkeypatch, content):
    _configured(monkeypatch)

    def _transport(url, headers, body, timeout):
        return {"choices": [{"message": {"content": content}}]}

    result = ai.ask_epos(ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, AS_OF, transport=_transport)
    assert result.status == "invalid_response"
    assert result.source_ids == []
    assert result.warnings


def test_unexpected_response_shape_is_handled(portfolio, monkeypatch):
    _configured(monkeypatch)
    result = ai.ask_epos(
        ai.QUESTION_RISKS_WITHOUT_OWNER,
        portfolio,
        AS_OF,
        transport=lambda url, headers, body, timeout: {"unexpected": True},
    )
    assert result.status == "invalid_response"


def test_fabricated_source_ids_reject_the_entire_response(portfolio, monkeypatch):
    _configured(monkeypatch)
    package = ai.build_evidence_package(ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, AS_OF)
    valid_id = package.source_ids[0]
    result = ai.ask_epos(
        ai.QUESTION_RISKS_WITHOUT_OWNER,
        portfolio,
        AS_OF,
        transport=_transport_returning(_valid_payload([valid_id, "R-9999"])),
    )
    assert result.status == "invalid_response"
    assert result.source_ids == []
    assert result.key_findings == []
    assert result.recommended_actions == []
    assert "Two projects require attention" not in result.executive_summary
    assert any("R-9999" in warning for warning in result.warnings)


def test_factual_response_without_citations_is_rejected(portfolio, monkeypatch):
    _configured(monkeypatch)

    result = ai.ask_epos(
        ai.QUESTION_RISKS_WITHOUT_OWNER,
        portfolio,
        AS_OF,
        transport=_transport_returning(_valid_payload([])),
    )

    assert result.status == "invalid_response"
    assert result.source_ids == []
    assert result.key_findings == []
    assert result.recommended_actions == []


def test_transport_failure_is_handled(portfolio, monkeypatch):
    _configured(monkeypatch)

    def _boom(url, headers, body, timeout):
        raise TimeoutError("simulated timeout")

    result = ai.ask_epos(ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, AS_OF, transport=_boom)
    assert result.status == "error"
    assert result.source_ids == []
    assert any("TimeoutError" in warning for warning in result.warnings)


def test_no_mutation_of_portfolio(monkeypatch):
    _configured(monkeypatch)
    portfolio = load_portfolio()
    snapshot = copy.deepcopy(portfolio)
    ai.build_evidence_package(ai.QUESTION_WEEKLY_EXECUTIVE_UPDATE, portfolio, AS_OF)
    ai.ask_epos(
        ai.QUESTION_RISKS_WITHOUT_OWNER,
        portfolio,
        AS_OF,
        transport=_transport_returning(_valid_payload([])),
    )
    for attr in ("projects", "milestones", "tasks", "risks", "requirements", "test_cases"):
        after = [r.model_dump() for r in getattr(portfolio, attr)]
        before = [r.model_dump() for r in getattr(snapshot, attr)]
        assert after == before
