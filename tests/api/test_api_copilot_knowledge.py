"""Documentation answers remain source-grounded and fail closed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from api.services import copilot_knowledge
from src.config import AI_DISCLAIMER, AzureOpenAISettings


def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )


def _model_answer(source_ids: list[str], **overrides: Any) -> dict[str, Any]:
    result = {
        "executive_summary": "EPOS keeps deterministic calculations separate from explanation.",
        "key_findings": ["Its architecture places the AI layer downstream of calculated facts."],
        "recommended_actions": ["Follow the cited architecture source for detail."],
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


class TestRetrieval:
    def test_architecture_questions_retrieve_architecture_documentation(self) -> None:
        records = copilot_knowledge.retrieve("What architecture does EPOS use?")

        assert any(record.fields.get("path") == "docs/architecture.md" for record in records)

    def test_roadmap_questions_retrieve_the_roadmap(self) -> None:
        records = copilot_knowledge.retrieve("What is on the future roadmap?")

        assert any(record.fields.get("path") == "docs/roadmap.md" for record in records)

    def test_a_help_topic_finds_the_section_that_defines_its_term(self) -> None:
        chosen = ["EPOS user guide: What is EPOS", "EPOS user guide: Pages"]
        records = copilot_knowledge.retrieve_help("milestone in EPOS", chosen)

        assert "Glossary" in {record.fields.get("section") for record in records}

    def test_retrieval_reads_only_the_document_allowlist(self) -> None:
        records = copilot_knowledge.retrieve("Explain the system")
        paths = {record.fields.get("path") for record in records if "path" in record.fields}
        allowed = {path for _, _, path in copilot_knowledge._DOCUMENTS}

        assert paths <= allowed
        assert all(".env" not in (path or "") for path in paths)

    def test_test_counts_are_labelled_as_source_inventory_not_execution(self) -> None:
        metadata = copilot_knowledge.retrieve("How many tests exist?")[0]

        assert metadata.record_id == "META-TEST-SOURCE-INVENTORY"
        assert int(metadata.fields["python_test_files"]) > 0
        assert int(metadata.fields["python_test_functions"]) > 0
        assert "do not prove execution" in metadata.fields["meaning"]

    def test_only_a_small_evidence_package_is_selected(self) -> None:
        records = copilot_knowledge.retrieve("Explain architecture, governance, and limitations")

        assert len(records) <= copilot_knowledge._MAX_CHUNKS + 1
        assert all(len(record.fields.get("content", "")) <= 2400 for record in records)


class TestPayload:
    def test_the_request_uses_strict_structured_output(self) -> None:
        records = copilot_knowledge.retrieve("How does the architecture work?")
        payload = copilot_knowledge.build_request_payload("How does it work?", records)
        schema = payload["response_format"]["json_schema"]

        assert schema["strict"] is True
        assert schema["name"] == "epos_knowledge_answer"
        assert payload["temperature"] == 0

    def test_the_prompt_forbids_unsourced_facts_and_calculation(self) -> None:
        records = copilot_knowledge.retrieve("How does the architecture work?")
        payload = copilot_knowledge.build_request_payload("How does it work?", records)
        prompt = payload["messages"][0]["content"]

        assert "ONLY the supplied" in prompt
        assert "Do not calculate" in prompt
        assert "Cite every factual claim" in prompt

    def test_valid_source_ids_are_sent_explicitly(self) -> None:
        records = copilot_knowledge.retrieve("How does the architecture work?")
        payload = copilot_knowledge.build_request_payload("How does it work?", records)
        content = json.loads(payload["messages"][1]["content"])

        assert set(content["valid_source_ids"]) == {record.record_id for record in records}


class TestAnswer:
    def test_a_valid_answer_is_returned_with_its_used_evidence(self, monkeypatch) -> None:
        _configured(monkeypatch)
        records = copilot_knowledge.retrieve("How does the architecture work?")
        source_id = next(
            record.record_id for record in records if record.record_type == "documentation"
        )

        answer = copilot_knowledge.answer(
            "How does the architecture work?", _transport(_model_answer([source_id]))
        )

        assert answer.status == "ok"
        assert answer.source_ids == [source_id]
        assert [record.record_id for record in answer.evidence] == [source_id]
        assert answer.human_review_required is True
        assert answer.disclaimer == AI_DISCLAIMER

    def test_a_fabricated_source_rejects_the_entire_answer(self, monkeypatch) -> None:
        _configured(monkeypatch)
        records = copilot_knowledge.retrieve("How does the architecture work?")
        valid = records[1].record_id

        answer = copilot_knowledge.answer(
            "How does the architecture work?",
            _transport(_model_answer([valid, "DOC-INVENTED-99"])),
        )

        assert answer.status == "invalid_response"
        assert answer.source_ids == []
        assert answer.evidence == []
        assert answer.key_findings == []
        assert answer.recommended_actions == []
        assert any("DOC-INVENTED-99" in warning for warning in answer.warnings)

    @pytest.mark.parametrize("content", ["not json", json.dumps({"executive_summary": "partial"})])
    def test_malformed_output_is_rejected(self, content: str, monkeypatch) -> None:
        _configured(monkeypatch)

        def send(_url, _headers, _body, _timeout):
            return {"choices": [{"message": {"content": content}}]}

        answer = copilot_knowledge.answer("Explain the architecture", send)

        assert answer.status == "invalid_response"
        assert answer.source_ids == []
        assert answer.evidence == []

    def test_transport_failure_is_safe(self, monkeypatch) -> None:
        _configured(monkeypatch)

        def fail(_url, _headers, _body, _timeout):
            raise TimeoutError("simulated")

        answer = copilot_knowledge.answer("Explain the architecture", fail)

        assert answer.status == "error"
        assert answer.source_ids == []
        assert "TimeoutError" in answer.warnings[0]

    def test_missing_configuration_is_safe(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.ai_assistant.get_azure_settings",
            lambda: AzureOpenAISettings(api_key=None, endpoint=None),
        )

        answer = copilot_knowledge.answer("Explain the architecture")

        assert answer.status == "unavailable"
        assert answer.source_ids == []
