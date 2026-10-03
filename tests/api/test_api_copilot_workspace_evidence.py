"""Long-tail workspace answers select records deterministically and explain only those records."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from api.services import workspace_evidence
from src.config import AI_DISCLAIMER, AzureOpenAISettings


def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )


def _model_answer(source_ids: list[str], **overrides: Any) -> dict[str, Any]:
    result = {
        "executive_summary": "The selected project has recorded risks.",
        "key_findings": ["One selected risk is open."],
        "recommended_actions": ["Review the cited risk record."],
        "source_ids": source_ids,
        "human_review_required": True,
        "disclaimer": AI_DISCLAIMER,
    }
    result.update(overrides)
    return result


def _transport(content: object):
    def send(_url: str, _headers: dict[str, str], _body: dict, _timeout: float) -> dict:
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    return send


class TestSelection:
    def test_one_project_never_leaks_another_projects_records(self, csv_portfolio) -> None:
        count, records = workspace_evidence.select(
            csv_portfolio,
            workspace_evidence.Selection(record_type="risk", project_id="P-002"),
        )

        expected = [risk for risk in csv_portfolio.risks if risk.project_id == "P-002"]
        assert count == len(expected)
        assert all(record.fields.get("project_id") == "P-002" for record in records[1:])

    def test_domain_filter_uses_only_stored_project_domains(self, csv_portfolio) -> None:
        count, records = workspace_evidence.select(
            csv_portfolio,
            workspace_evidence.Selection(
                record_type="project", domains=("Digital Engineering", "Test Engineering")
            ),
        )

        assert count == 2
        assert {record.record_id for record in records[1:]} == {"P-007", "P-031"}

    def test_status_filter_reads_stored_status_fields(self, csv_portfolio) -> None:
        count, records = workspace_evidence.select(
            csv_portfolio,
            workspace_evidence.Selection(record_type="risk", status="Open"),
        )

        assert count > 0
        assert all(record.fields["status"] == "Open" for record in records[1:])

    def test_count_is_calculated_before_the_package_cap(self, csv_portfolio) -> None:
        portfolio = copy.deepcopy(csv_portfolio)
        original = portfolio.risks[0]
        portfolio.risks = [
            original.model_copy(update={"risk_id": f"R-X{index:03d}"}) for index in range(55)
        ]

        count, records = workspace_evidence.select(
            portfolio, workspace_evidence.Selection(record_type="risk")
        )

        assert count == 55
        assert len(records) == workspace_evidence._MAX_RECORDS + 1
        assert records[0].fields["matched_count"] == "55"
        assert records[0].fields["records_in_package"] == str(workspace_evidence._MAX_RECORDS)

    def test_selection_metadata_carries_every_applied_filter(self, csv_portfolio) -> None:
        _, records = workspace_evidence.select(
            csv_portfolio,
            workspace_evidence.Selection(
                record_type="task",
                project_id="P-002",
                domains=("Sustainability",),
                status="Blocked",
            ),
        )
        metadata = records[0].fields

        assert metadata["record_type"] == "task"
        assert metadata["project_id"] == "P-002"
        assert json.loads(metadata["project_scope_ids"]) == ["P-002"]
        assert metadata["domains"] == "Sustainability"
        assert metadata["status_filter"] == "Blocked"


class TestPayload:
    def test_the_prompt_forbids_model_calculation(self, csv_portfolio) -> None:
        _, evidence = workspace_evidence.select(
            csv_portfolio, workspace_evidence.Selection(record_type="risk")
        )
        payload = workspace_evidence.build_request_payload("Show all risks", evidence)
        prompt = payload["messages"][0]["content"]

        assert "Do not calculate" in prompt
        assert "deterministic metadata" in prompt
        assert "Cite every factual claim" in prompt

    def test_the_schema_is_strict(self, csv_portfolio) -> None:
        _, evidence = workspace_evidence.select(
            csv_portfolio, workspace_evidence.Selection(record_type="risk")
        )
        payload = workspace_evidence.build_request_payload("Show all risks", evidence)

        assert payload["temperature"] == 0
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["response_format"]["json_schema"]["name"] == "epos_workspace_answer"


class TestAnswer:
    def test_an_empty_selection_never_calls_the_model(self, csv_portfolio) -> None:
        called = False

        def transport(_url, _headers, _body, _timeout):
            nonlocal called
            called = True
            raise AssertionError("must not be called")

        result = workspace_evidence.answer(
            "Show closed risks on P-014",
            csv_portfolio,
            workspace_evidence.Selection(
                record_type="risk", project_id="P-014", status="Impossible status"
            ),
            transport,
        )

        assert result.status == "ok"
        assert result.human_review_required is False
        assert result.source_ids == ["META-WORKSPACE-SELECTION"]
        assert called is False

    def test_a_valid_model_answer_shows_only_cited_evidence(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        _, records = workspace_evidence.select(
            csv_portfolio,
            workspace_evidence.Selection(record_type="risk", project_id="P-002"),
        )
        source_id = records[1].record_id

        result = workspace_evidence.answer(
            "Show every risk for P-002",
            csv_portfolio,
            workspace_evidence.Selection(record_type="risk", project_id="P-002"),
            _transport(_model_answer([source_id])),
        )

        assert result.status == "ok"
        assert result.source_ids == [source_id]
        assert [record.record_id for record in result.evidence] == [source_id]
        assert result.human_review_required is True

    def test_a_fabricated_source_rejects_the_entire_answer(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        _, records = workspace_evidence.select(
            csv_portfolio, workspace_evidence.Selection(record_type="risk")
        )
        valid = records[1].record_id

        result = workspace_evidence.answer(
            "Show every risk",
            csv_portfolio,
            workspace_evidence.Selection(record_type="risk"),
            _transport(_model_answer([valid, "R-INVENTED"])),
        )

        assert result.status == "invalid_response"
        assert result.source_ids == []
        assert result.evidence == []
        assert result.key_findings == []
        assert result.recommended_actions == []
        assert any("R-INVENTED" in warning for warning in result.warnings)

    @pytest.mark.parametrize("content", ["not json", json.dumps({"executive_summary": "partial"})])
    def test_malformed_model_output_is_rejected(
        self, content: str, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)

        def send(_url, _headers, _body, _timeout):
            return {"choices": [{"message": {"content": content}}]}

        result = workspace_evidence.answer(
            "Show every risk",
            csv_portfolio,
            workspace_evidence.Selection(record_type="risk"),
            send,
        )

        assert result.status == "invalid_response"
        assert result.source_ids == []

    def test_transport_failure_is_safe(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)

        def fail(_url, _headers, _body, _timeout):
            raise TimeoutError("simulated")

        result = workspace_evidence.answer(
            "Show every risk",
            csv_portfolio,
            workspace_evidence.Selection(record_type="risk"),
            fail,
        )

        assert result.status == "ok"
        assert result.human_review_required is False
        assert set(result.source_ids) == {record.record_id for record in result.evidence}
        assert all(risk.risk_id in result.source_ids for risk in csv_portfolio.risks)
        assert any("TimeoutError" in warning for warning in result.warnings)
        assert "read directly" in result.warnings[0]
