"""Repeatable, offline benchmark of the Ask EPOS AI pipeline.

No network call is made. Every Azure request is answered by an injected fake transport, so the
figures below are split into two clearly different kinds:

* MEASURED locally: wall-clock processing time of the real ``copilot_service.ask`` path (routing,
  evidence building, validation, presentation), model calls per request, prompt sizes, response
  validation outcomes and the status produced for each fault case.
* SIMULATED: end-to-end latency including model time. Model time is not measured; it is estimated
  from a fixed, documented cost model applied to the prompts the pipeline actually built.

The classifier is an oracle that returns the corpus label, so routing agreement is an upper bound
on what the local rules plus a perfect classifier achieve, not a measurement of Azure accuracy.

Usage:
    python scripts/benchmark_ai_pipeline.py --label baseline --repeat 3
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from api.services import copilot_service, semantic_router  # noqa: E402
from src import ai_assistant  # noqa: E402
from src.config import AI_DISCLAIMER, AzureOpenAISettings  # noqa: E402
from src.data_loader import load_portfolio  # noqa: E402
from src.ui_formatting import ANALYSIS_DATE  # noqa: E402
from tests.eval.corpus import ALL_CASES  # noqa: E402

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "test-results"

# Simulated model cost model (assumption, not measurement). Roughly four characters per token.
_CHARS_PER_TOKEN = 4
_BASE_MS = 300.0
_MS_PER_1K_INPUT_TOKENS = 40.0
_MS_PER_OUTPUT_TOKEN = 15.0
_OUTPUT_TOKENS = {"epos_semantic_route": 60, "default": 350}


@dataclass
class _Call:
    schema: str
    prompt_chars: int
    max_tokens: int | None


@dataclass
class _Recorder:
    """Fake Azure transport: oracle classifier, citing explainer, optional fault injection."""

    labels: dict[str, str | None]
    fault: str | None = None
    calls: list[_Call] = field(default_factory=list)

    def __call__(
        self, url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        schema = body["response_format"]["json_schema"]["name"]
        user = json.loads(body["messages"][-1]["content"])
        self.calls.append(
            _Call(
                schema=schema,
                prompt_chars=sum(len(message["content"]) for message in body["messages"]),
                max_tokens=body.get("max_tokens"),
            )
        )
        if schema == "epos_semantic_route":
            return _completion(self._route(user["question"]))
        if self.fault == "timeout":
            raise requests.Timeout("simulated timeout")
        if self.fault == "http_error":
            raise requests.HTTPError("simulated 500")
        valid = list(user.get("valid_source_ids") or [])
        content: dict[str, Any] = {
            "executive_summary": "Simulated explanation of the supplied records.",
            "key_findings": [f"Recorded evidence is available [{valid[0]}]."] if valid else [],
            "recommended_actions": ["Review the cited records."],
            "source_ids": valid[:2],
            "human_review_required": True,
            "disclaimer": AI_DISCLAIMER,
        }
        if self.fault == "fabricated_source":
            content["source_ids"] = [*valid[:1], "R-9999"]
        elif self.fault == "malformed":
            return _completion("not json")
        elif self.fault == "extra_property":
            content["confidence"] = "high"
        elif self.fault == "false_review":
            content["human_review_required"] = False
            content["disclaimer"] = "Verified."
        return _completion(json.dumps(content))

    def _route(self, question: str) -> str:
        expected = self.labels.get(question)
        intent = expected or semantic_router.OUT_OF_SCOPE
        return json.dumps(
            {
                "intent": intent,
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
        )


def _completion(content: str) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _simulated_ms(call: _Call) -> float:
    input_tokens = call.prompt_chars / _CHARS_PER_TOKEN
    output_tokens = _OUTPUT_TOKENS.get(call.schema, _OUTPUT_TOKENS["default"])
    return (
        _BASE_MS
        + input_tokens / 1000 * _MS_PER_1K_INPUT_TOKENS
        + output_tokens * _MS_PER_OUTPUT_TOKEN
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _ask(question: str, portfolio, transport: _Recorder):
    return copilot_service.ask(
        question,
        portfolio,
        ANALYSIS_DATE,
        transport=transport,
        owner_name="Benchmark User",
        decisions=[],
        can_run_scenarios=True,
        can_read_reports=True,
    )


def _corpus_run(portfolio, repeat: int) -> dict[str, Any]:
    labels = {case.question: case.expected for case in ALL_CASES}
    local_ms: list[float] = []
    simulated_ms: list[float] = []
    calls_per_request: Counter[int] = Counter()
    schema_calls: Counter[str] = Counter()
    prompt_chars: dict[str, list[int]] = {}
    statuses: Counter[str] = Counter()
    max_tokens_set = 0
    total_calls = 0
    agreement = 0
    for iteration in range(repeat):
        for case in ALL_CASES:
            recorder = _Recorder(labels)
            started = time.perf_counter()
            answer = _ask(case.question, portfolio, recorder)
            elapsed = (time.perf_counter() - started) * 1000
            if iteration == 0:
                calls_per_request[len(recorder.calls)] += 1
                statuses[answer.status] += 1
                primary = (answer.matched_intent or "").split(" + ")[0] or None
                agreement += primary == case.expected or (
                    case.expected is None and answer.status == "clarification"
                )
                for call in recorder.calls:
                    total_calls += 1
                    schema_calls[call.schema] += 1
                    prompt_chars.setdefault(call.schema, []).append(call.prompt_chars)
                    max_tokens_set += call.max_tokens is not None
            local_ms.append(elapsed)
            simulated_ms.append(elapsed + sum(_simulated_ms(call) for call in recorder.calls))

    requests_total = len(ALL_CASES)
    classifier_requests = schema_calls.get("epos_semantic_route", 0)
    return {
        "requests": requests_total,
        "repeat": repeat,
        "model_calls_total": total_calls,
        "model_calls_per_request_mean": round(total_calls / requests_total, 3),
        "calls_per_request_distribution": dict(sorted(calls_per_request.items())),
        "classifier_calls": classifier_requests,
        "classifier_call_rate": round(classifier_requests / requests_total, 3),
        "zero_model_call_rate": round(calls_per_request.get(0, 0) / requests_total, 3),
        "calls_by_schema": dict(sorted(schema_calls.items())),
        "prompt_chars_mean_by_schema": {
            key: round(statistics.mean(values)) for key, values in sorted(prompt_chars.items())
        },
        "prompt_chars_max_by_schema": {
            key: max(values) for key, values in sorted(prompt_chars.items())
        },
        "calls_with_max_tokens": max_tokens_set,
        "status_distribution": dict(sorted(statuses.items())),
        "routing_agreement_with_oracle": round(agreement / requests_total, 3),
        "measured_local_ms": {
            "p50": round(_percentile(local_ms, 0.5), 2),
            "p95": round(_percentile(local_ms, 0.95), 2),
            "mean": round(statistics.mean(local_ms), 2),
        },
        "simulated_end_to_end_ms": {
            "p50": round(_percentile(simulated_ms, 0.5), 1),
            "p95": round(_percentile(simulated_ms, 0.95), 1),
            "mean": round(statistics.mean(simulated_ms), 1),
        },
    }


_FAULT_QUESTIONS = (
    "Which risks have no mitigation owner?",
    "Why is P-007 Amber or Red?",
    "Draft a weekly executive portfolio update.",
)


def _fault_run(portfolio) -> dict[str, dict[str, int]]:
    labels = {case.question: case.expected for case in ALL_CASES}
    results: dict[str, dict[str, int]] = {}
    for fault in (
        None,
        "fabricated_source",
        "malformed",
        "extra_property",
        "false_review",
        "timeout",
        "http_error",
    ):
        outcome: Counter[str] = Counter()
        for question in _FAULT_QUESTIONS:
            answer = _ask(question, portfolio, _Recorder(labels, fault))
            reviewed = "review" if answer.human_review_required else "no-review"
            content = "content" if answer.key_findings else "no-content"
            outcome[f"{answer.status}/{reviewed}/{content}"] += 1
        results[fault or "none"] = dict(sorted(outcome.items()))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="run")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    ai_assistant.get_azure_settings = lambda: AzureOpenAISettings(  # type: ignore[assignment]
        api_key="benchmark-placeholder", endpoint="https://benchmark.invalid/chat"
    )
    portfolio = load_portfolio()
    _ask("Which projects need attention this week?", portfolio, _Recorder({}))  # warm imports

    report = {
        "label": args.label,
        "measurement_note": (
            "measured_local_ms and counts are measured with a fake transport; "
            "simulated_end_to_end_ms adds an assumed model cost model and is not a live measurement"
        ),
        "cost_model": {
            "base_ms": _BASE_MS,
            "ms_per_1k_input_tokens": _MS_PER_1K_INPUT_TOKENS,
            "ms_per_output_token": _MS_PER_OUTPUT_TOKEN,
            "output_tokens": _OUTPUT_TOKENS,
        },
        "corpus": _corpus_run(portfolio, args.repeat),
        "faults": _fault_run(portfolio),
    }
    _OUTPUT_DIR.mkdir(exist_ok=True)
    target = _OUTPUT_DIR / f"ai-benchmark-{args.label}.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWritten to {target.relative_to(target.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
