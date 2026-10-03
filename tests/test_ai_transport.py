"""The shared Azure transport boundary and the grounding checks applied to every reply.

Every test injects a fake transport or a fake session; nothing here opens a network connection.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import pytest
import requests

from src import ai_assistant as ai
from src import ai_trace
from src.config import AI_DISCLAIMER, AzureOpenAISettings
from src.schemas import CopilotResponse
from src.ui_formatting import ANALYSIS_DATE

SECRET = "secret-key-value-that-must-never-appear"
_PAYLOAD: dict[str, Any] = {
    "messages": [{"role": "user", "content": "question text"}],
    "response_format": {"type": "json_schema", "json_schema": {"name": "copilot_response"}},
}


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ai,
        "get_azure_settings",
        lambda: AzureOpenAISettings(api_key=SECRET, endpoint="https://example.invalid/chat"),
    )


def _body(content: object = "{}", **choice: object) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": content}, **choice}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 180, "total_tokens": 1380},
    }


def _recording(response: dict[str, Any]):
    seen: list[dict[str, Any]] = []

    def send(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float):
        seen.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        return response

    send.seen = seen  # type: ignore[attr-defined]
    return send


def _raising(exc: BaseException):
    def send(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float):
        raise exc

    return send


class TestRequestShape:
    def test_explanations_are_bounded_by_default(self) -> None:
        send = _recording(_body())
        ai.complete_structured(_PAYLOAD, send)
        assert send.seen[0]["body"]["max_tokens"] == ai.EXPLANATION_MAX_TOKENS
        assert send.seen[0]["timeout"] == ai.REQUEST_TIMEOUT_SECONDS

    def test_a_caller_limit_is_applied(self) -> None:
        send = _recording(_body())
        ai.complete_structured(_PAYLOAD, send, max_tokens=ai.CLASSIFICATION_MAX_TOKENS)
        assert send.seen[0]["body"]["max_tokens"] == ai.CLASSIFICATION_MAX_TOKENS

    def test_a_payload_limit_is_never_overridden(self) -> None:
        send = _recording(_body())
        ai.complete_structured({**_PAYLOAD, "max_tokens": 77}, send)
        assert send.seen[0]["body"]["max_tokens"] == 77

    def test_the_callers_payload_is_not_mutated(self) -> None:
        payload = json.loads(json.dumps(_PAYLOAD))
        ai.complete_structured(payload, _recording(_body()))
        assert "max_tokens" not in payload


class TestFailureClassification:
    @pytest.mark.parametrize(
        "exc", [requests.ReadTimeout("slow"), requests.ConnectTimeout("slow"), TimeoutError("slow")]
    )
    def test_a_timeout_is_reported_as_a_timeout(self, exc: BaseException) -> None:
        result = ai.complete_structured(_PAYLOAD, _raising(exc))
        assert (result.status, result.failure, result.content) == ("error", "timeout", None)
        assert "timed out" in result.warnings[0]
        assert type(exc).__name__ in result.warnings[0]

    def test_an_http_refusal_reports_only_its_status_code(self) -> None:
        refused = requests.Response()
        refused.status_code = 429
        refused._content = f'{{"error": "{SECRET}"}}'.encode()
        result = ai.complete_structured(
            _PAYLOAD, _raising(requests.HTTPError("429 body", response=refused))
        )
        assert (result.status, result.failure) == ("error", "http_status")
        assert result.warnings == ("Request failed with HTTP 429.",)

    def test_a_short_requested_wait_is_retried_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        waits: list[float] = []
        monkeypatch.setattr(ai.time, "sleep", waits.append)
        busy = requests.Response()
        busy.status_code = 429
        busy.headers["retry-after-ms"] = "250"
        calls: list[int] = []

        def send(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float):
            calls.append(1)
            if len(calls) == 1:
                raise requests.HTTPError("busy", response=busy)
            return _body('{"ok": true}')

        result = ai.complete_structured(_PAYLOAD, send)
        assert result.status == "ok"
        assert waits == [0.25]
        assert len(calls) == 2

    def test_a_long_requested_wait_fails_at_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ai.time, "sleep", lambda _: pytest.fail("must not wait"))
        busy = requests.Response()
        busy.status_code = 429
        busy.headers["retry-after"] = "30"
        result = ai.complete_structured(
            _PAYLOAD, _raising(requests.HTTPError("busy", response=busy))
        )
        assert result.warnings == ("Request failed with HTTP 429.",)

    def test_an_unexpected_transport_error_is_contained(self) -> None:
        result = ai.complete_structured(_PAYLOAD, _raising(RuntimeError(SECRET)))
        assert (result.status, result.failure) == ("error", "transport")
        assert SECRET not in " ".join(result.warnings)

    def test_a_truncated_reply_is_rejected_rather_than_repaired(self) -> None:
        send = _recording(_body('{"executive_summary": "cut', finish_reason="length"))
        result = ai.complete_structured(_PAYLOAD, send)
        assert (result.status, result.failure, result.content) == (
            "invalid_response",
            "truncated",
            None,
        )

    def test_a_filtered_reply_is_rejected(self) -> None:
        result = ai.complete_structured(
            _PAYLOAD, _recording(_body(None, finish_reason="content_filter"))
        )
        assert (result.status, result.failure) == ("invalid_response", "filtered")

    @pytest.mark.parametrize("raw", [{}, {"choices": []}, {"choices": [{}]}, [], "text"])
    def test_a_malformed_body_is_rejected(self, raw: object) -> None:
        result = ai.complete_structured(_PAYLOAD, _recording(raw))  # type: ignore[arg-type]
        assert (result.status, result.failure) == ("invalid_response", "malformed")

    def test_null_content_is_rejected(self) -> None:
        result = ai.complete_structured(_PAYLOAD, _recording(_body(None, finish_reason="stop")))
        assert (result.status, result.failure) == ("invalid_response", "malformed")

    def test_missing_configuration_makes_no_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ai, "get_azure_settings", lambda: AzureOpenAISettings(api_key=None, endpoint=None)
        )
        send = _recording(_body())
        result = ai.complete_structured(_PAYLOAD, send)
        assert (result.status, result.failure) == ("unavailable", "not_configured")
        assert send.seen == []


class TestUsage:
    def test_token_usage_is_captured(self) -> None:
        result = ai.complete_structured(_PAYLOAD, _recording(_body('{"a": 1}')))
        assert (result.prompt_tokens, result.completion_tokens) == (1200, 180)

    @pytest.mark.parametrize(
        "usage", [None, "many", {"prompt_tokens": "12"}, {"prompt_tokens": True}]
    )
    def test_implausible_usage_is_ignored(self, usage: object) -> None:
        body = {"choices": [{"message": {"content": "{}"}}], "usage": usage}
        result = ai.complete_structured(_PAYLOAD, _recording(body))
        assert result.status == "ok"
        assert result.prompt_tokens is None


class TestConnectionReuse:
    def test_one_session_is_reused_within_a_thread(self) -> None:
        assert ai._session() is ai._session()

    def test_threads_do_not_share_a_session(self) -> None:
        sessions: list[requests.Session] = []
        worker = threading.Thread(target=lambda: sessions.append(ai._session()))
        worker.start()
        worker.join()
        assert sessions[0] is not ai._session()

    def test_the_default_transport_posts_through_the_pooled_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []

        class _Reply:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return _body('{"ok": true}')

        class _Session:
            def post(self, url: str, **kwargs: Any) -> _Reply:
                calls.append({"url": url, **kwargs})
                return _Reply()

        monkeypatch.setattr(ai, "_session", lambda: _Session())
        result = ai.complete_structured(_PAYLOAD)
        assert result.status == "ok"
        assert calls[0]["timeout"] == ai.REQUEST_TIMEOUT_SECONDS
        assert calls[0]["json"]["max_tokens"] == ai.EXPLANATION_MAX_TOKENS


class TestTrace:
    def test_model_calls_are_traced_without_content(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.INFO, logger="epos.ai.trace"),
            ai_trace.request_trace() as trace,
            ai_trace.stage("answer"),
        ):
            ai.complete_structured(_PAYLOAD, _recording(_body('{"a": 1}')))
        [call] = trace.model_calls
        assert (call.schema, call.status, call.prompt_tokens) == ("copilot_response", "ok", 1200)
        assert call.prompt_chars == len("question text")
        assert "answer" in trace.stages_ms
        logged = caplog.text
        assert trace.trace_id in logged
        for forbidden in ("question text", SECRET, "example.invalid", '{"a": 1}'):
            assert forbidden not in logged

    def test_calls_outside_a_request_are_not_traced(self) -> None:
        with ai_trace.stage("orphan"):
            result = ai.complete_structured(_PAYLOAD, _recording(_body()))
        assert result.status == "ok"

    def test_trace_ids_are_unique(self) -> None:
        ids = set()
        for _ in range(50):
            with ai_trace.request_trace() as trace:
                ids.add(trace.trace_id)
        assert len(ids) == 50


def _response(**overrides: object) -> CopilotResponse:
    fields: dict[str, Any] = {
        "executive_summary": "Summary.",
        "key_findings": [],
        "recommended_actions": [],
        "source_ids": ["P-002"],
        "human_review_required": True,
        "disclaimer": AI_DISCLAIMER,
    }
    fields.update(overrides)
    return CopilotResponse(**fields)


class TestProseIdentifiers:
    EVIDENCE = json.dumps({"record_id": "P-002", "fields": {"source_ids": "R-2001, M-2002"}})

    def test_identifiers_present_in_evidence_are_accepted(self) -> None:
        response = _response(key_findings=["P-002 has R-2001 and M-2002 open."])
        assert ai.unsupported_identifier_warnings(response, self.EVIDENCE, "evidence") == []

    def test_an_invented_identifier_is_rejected_even_with_valid_citations(self) -> None:
        response = _response(key_findings=["P-002 also depends on D-9999."])
        warnings = ai.unsupported_identifier_warnings(response, self.EVIDENCE, "evidence")
        assert warnings == ["Rejected record identifiers absent from evidence: D-9999"]

    @pytest.mark.parametrize(
        "text", ["GPT-4o explains facts.", "Aligned with ISO 26262.", "Review in Q3.", "UTF-8"]
    )
    def test_ordinary_text_is_not_mistaken_for_an_identifier(self, text: str) -> None:
        response = _response(executive_summary=text)
        assert ai.unsupported_identifier_warnings(response, self.EVIDENCE, "evidence") == []

    def test_a_prefix_of_a_real_identifier_is_not_accepted(self) -> None:
        response = _response(key_findings=["See R-20."])
        assert ai.unsupported_identifier_warnings(response, self.EVIDENCE, "evidence")


class TestEvidenceReuse:
    def test_a_prebuilt_package_is_explained_without_rebuilding(
        self, portfolio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        package = ai.build_evidence_package(
            ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, ANALYSIS_DATE
        )

        def _no_rebuild(*_: object, **__: object):
            raise AssertionError("evidence was rebuilt")

        monkeypatch.setattr(ai, "build_evidence_package", _no_rebuild)
        reply = json.dumps(
            {
                "executive_summary": "Unowned risks need an owner.",
                "key_findings": [],
                "recommended_actions": [],
                "source_ids": package.source_ids[:1],
                "human_review_required": True,
                "disclaimer": AI_DISCLAIMER,
            }
        )
        result = ai.ask_epos(
            ai.QUESTION_RISKS_WITHOUT_OWNER,
            portfolio,
            ANALYSIS_DATE,
            transport=_recording(_body(reply)),
            evidence=package,
        )
        assert result.status == "ok"

    def test_a_package_for_another_question_is_refused(self, portfolio) -> None:
        package = ai.build_evidence_package(
            ai.QUESTION_RISKS_WITHOUT_OWNER, portfolio, ANALYSIS_DATE
        )
        with pytest.raises(ai.DataValidationError):
            ai.ask_epos(ai.QUESTION_MILESTONES_AT_RISK, portfolio, ANALYSIS_DATE, evidence=package)
