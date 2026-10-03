"""Live, batched evaluation of the Azure semantic classifier.

The questions are sent without expected labels. This script is intentionally outside pytest because
it uses the configured Azure deployment. Run with ``python -m tests.eval.semantic_harness``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict

from api.services import semantic_router
from src.ai_assistant import complete_structured
from src.data_loader import load_portfolio
from tests.eval.corpus import ALL_CASES, Case

_BATCH_SIZE: Final[int] = 30


class _Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: int
    intent: str


class _Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[_Classification]


_ITEM_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "case_id": {"type": "integer"},
        "intent": {"type": "string", "enum": list(semantic_router._ALLOWED_INTENTS)},
    },
    "required": ["case_id", "intent"],
    "additionalProperties": False,
}

_BATCH_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "results": {"type": "array", "items": _ITEM_SCHEMA},
    },
    "required": ["results"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT: Final[str] = (
    "Classify each independent EPOS question into exactly one allowed intent. Return one result for "
    "every case_id and nothing else. Do not answer any question. Do not calculate or infer project "
    "facts. Use out_of_scope only when a question is unrelated to EPOS or project delivery. Use "
    "needs_clarification for an in-scope question that genuinely cannot be interpreted."
)


@dataclass(frozen=True)
class SemanticEvalReport:
    total: int
    passed: int
    failures: tuple[tuple[Case, str | None], ...]
    by_style: dict[str, tuple[int, int]]
    false_routing: int
    unsupported: int
    invalid_batches: int

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def _payload(indexed_cases: list[tuple[int, Case]]) -> dict[str, object]:
    portfolio = load_portfolio()
    content = {
        "allowed_intents": semantic_router._INTENT_GUIDE,
        "known_projects": [
            {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "domain": project.domain,
            }
            for project in portfolio.projects
        ],
        "cases": [
            {"case_id": case_id, "question": case.question} for case_id, case in indexed_cases
        ],
    }
    return {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(content, sort_keys=True)},
        ],
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "epos_semantic_eval_batch",
                "strict": True,
                "schema": _BATCH_SCHEMA,
            },
        },
    }


def _expected(intent: str | None) -> str | None:
    return intent


def _actual(intent: str) -> str | None:
    if intent in {semantic_router.OUT_OF_SCOPE, semantic_router.NEEDS_CLARIFICATION}:
        return None
    return intent


def run(cases: tuple[Case, ...] = ALL_CASES) -> SemanticEvalReport:
    """Classify the corpus in batches and return measured model performance."""
    indexed = list(enumerate(cases))
    predictions: dict[int, str] = {}
    invalid_batches = 0
    for offset in range(0, len(indexed), _BATCH_SIZE):
        batch_cases = indexed[offset : offset + _BATCH_SIZE]
        completion = complete_structured(_payload(batch_cases))
        if completion.status != "ok" or completion.content is None:
            invalid_batches += 1
            continue
        try:
            parsed = _Batch.model_validate_json(completion.content)
        except Exception:  # noqa: BLE001 - reported quantitatively by this evaluation tool
            invalid_batches += 1
            continue
        expected_ids = {case_id for case_id, _ in batch_cases}
        returned_ids = {item.case_id for item in parsed.results}
        if returned_ids != expected_ids:
            invalid_batches += 1
            continue
        predictions.update({item.case_id: item.intent for item in parsed.results})

    failures: list[tuple[Case, str | None]] = []
    by_style: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    false_routing = 0
    unsupported = 0
    passed = 0
    for case_id, case in indexed:
        predicted = _actual(predictions[case_id]) if case_id in predictions else None
        correct = predicted == _expected(case.expected)
        by_style[case.style][1] += 1
        if correct:
            passed += 1
            by_style[case.style][0] += 1
        else:
            failures.append((case, predicted))
            if case.expected is None and predicted is not None:
                false_routing += 1
            elif case.expected is not None and predicted is None:
                unsupported += 1

    return SemanticEvalReport(
        total=len(cases),
        passed=passed,
        failures=tuple(failures),
        by_style={key: tuple(value) for key, value in sorted(by_style.items())},
        false_routing=false_routing,
        unsupported=unsupported,
        invalid_batches=invalid_batches,
    )


def format_report(report: SemanticEvalReport) -> str:
    lines = [
        "Live Azure semantic-routing evaluation",
        "=" * 60,
        f"Cases          : {report.total}",
        f"Passed         : {report.passed}",
        f"Pass rate      : {report.pass_rate:.1%}",
        f"False routing  : {report.false_routing} ({report.false_routing / report.total:.1%})",
        f"Unsupported    : {report.unsupported} ({report.unsupported / report.total:.1%})",
        f"Invalid batches: {report.invalid_batches}",
        "",
        "By phrasing style",
        "-" * 60,
    ]
    for style, (passed, total) in report.by_style.items():
        lines.append(f"{style:<18} {passed:>3}/{total:<4} {passed / total:.0%}")
    if report.failures:
        lines.extend(("", f"Failures ({len(report.failures)})", "-" * 60))
        for case, predicted in report.failures:
            lines.append(f"{case.question!r}\n    expected={case.expected} predicted={predicted}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - manual live evaluation
    print(format_report(run()))
