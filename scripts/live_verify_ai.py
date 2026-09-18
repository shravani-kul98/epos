"""Manual live verification of the Ask EPOS AI layer against the real Azure OpenAI endpoint.

This script is deliberately kept OUT of ``tests/`` so that ``pytest`` never collects it. The
automated suite always uses mocked transports and never touches the network; this script is the
one place that makes real calls, and it must be run manually by someone holding their own
credentials.

Usage:
    python scripts/live_verify_ai.py

It reads ``API_KEY`` and ``ENDPOINT`` through the existing ``src.config`` mechanism. It never
prints, logs or writes those values in any form: only a boolean "configured" state is reported.
All output goes to stdout; nothing is written to disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import ai_assistant as ai  # noqa: E402
from src import ui_formatting as ui  # noqa: E402
from src.config import AI_DISCLAIMER, get_azure_settings  # noqa: E402
from src.data_loader import load_portfolio  # noqa: E402

AS_OF = ui.ANALYSIS_DATE
SEPARATOR = "-" * 78

# Each supported question, with the context it needs.
QUESTIONS: list[tuple[str, dict[str, str]]] = [
    (ai.QUESTION_PROJECTS_NEEDING_ATTENTION, {}),
    (ai.QUESTION_WHY_PROJECT_BAND, {"project_id": "P-007"}),
    (ai.QUESTION_RISKS_WITHOUT_OWNER, {}),
    (ai.QUESTION_MILESTONES_AT_RISK, {}),
    (ai.QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION, {}),
    (ai.QUESTION_CHANGE_REQUEST_IMPACT, {"change_request_id": "CR-042"}),
    (ai.QUESTION_WEEKLY_EXECUTIVE_UPDATE, {}),
]


def _evaluate(response, evidence) -> tuple[bool, list[str]]:
    """Apply the pass criteria and return the verdict plus any reasons for failure."""
    reasons: list[str] = []
    if response.status != "ok":
        reasons.append(f"status is {response.status}")
    if response.disclaimer != AI_DISCLAIMER:
        reasons.append("disclaimer text does not match exactly")
    if not response.source_ids:
        reasons.append("no source_ids returned")
    if not response.human_review_required:
        reasons.append("human_review_required is not true")
    unknown = [sid for sid in response.source_ids if sid not in set(evidence.source_ids)]
    if unknown:
        reasons.append(f"source_ids outside the evidence survived filtering: {unknown}")
    return (not reasons), reasons


def _run_one(question_type: str, context: dict[str, str], portfolio) -> dict[str, object]:
    """Make one real call and report everything about it."""
    print(SEPARATOR)
    print(f"QUESTION TYPE : {question_type}")
    print(f"QUESTION      : {ai.QUESTION_TYPES[question_type]}")
    if context:
        print(f"CONTEXT       : {context}")

    try:
        evidence = ai.build_evidence_package(question_type, portfolio, AS_OF, context)
    except Exception as exc:  # noqa: BLE001 - report and continue with the next question
        print(f"EVIDENCE ERROR: {type(exc).__name__}: {exc}")
        return {"question_type": question_type, "status": "evidence_error", "passed": False}

    print(
        f"EVIDENCE      : {len(evidence.records)} record(s), ids: "
        f"{ui.format_source_ids(evidence.source_ids)}"
    )

    try:
        # Real call: no transport is injected, so the default requests transport is used.
        response = ai.ask_epos(question_type, portfolio, AS_OF, context)
    except Exception as exc:  # noqa: BLE001 - ask_epos should not raise, but never crash here
        print(
            f"UNEXPECTED EXCEPTION: {type(exc).__name__} (message withheld to avoid leaking data)"
        )
        return {"question_type": question_type, "status": "exception", "passed": False}

    passed, reasons = _evaluate(response, evidence)

    print(f"STATUS        : {response.status}")
    print(f"SUMMARY       : {response.executive_summary}")
    print(f"KEY FINDINGS  : {len(response.key_findings)}")
    for finding in response.key_findings:
        print(f"                - {finding}")
    print(f"ACTIONS       : {len(response.recommended_actions)}")
    for action in response.recommended_actions:
        print(f"                - {action}")
    print(f"SOURCE IDS    : {ui.format_source_ids(response.source_ids)}")
    print(f"ALL GROUNDED  : {set(response.source_ids) <= set(evidence.source_ids)}")
    print(f"DISCLAIMER OK : {response.disclaimer == AI_DISCLAIMER}")
    print(f"DISCLAIMER    : {response.disclaimer}")
    print(f"HUMAN REVIEW  : {response.human_review_required}")
    if response.warnings:
        print("WARNINGS      :")
        for warning in response.warnings:
            print(f"                - {warning}")
    else:
        print("WARNINGS      : none")
    print(f"RESULT        : {'PASS' if passed else 'FAIL'}")
    if reasons:
        for reason in reasons:
            print(f"                ! {reason}")

    return {
        "question_type": question_type,
        "status": response.status,
        "passed": passed,
        "source_id_count": len(response.source_ids),
        "warnings": len(response.warnings),
    }


def _minimal_evidence_observation(portfolio) -> None:
    """Re-run the sparsest question and comment on grounding with minimal evidence."""
    print(SEPARATOR)
    print("MINIMAL-EVIDENCE OBSERVATION")
    question_type = ai.QUESTION_RISKS_WITHOUT_OWNER
    evidence = ai.build_evidence_package(question_type, portfolio, AS_OF, {})
    print(
        f"Evidence supplied: {len(evidence.records)} record(s) -> "
        f"{ui.format_source_ids(evidence.source_ids)}"
    )

    response = ai.ask_epos(question_type, portfolio, AS_OF, {})
    valid = set(evidence.source_ids)
    unsupported = [sid for sid in response.source_ids if sid not in valid]

    print(f"Status              : {response.status}")
    print(f"Findings returned   : {len(response.key_findings)}")
    print(f"Source ids returned : {ui.format_source_ids(response.source_ids)}")
    print(f"Unsupported ids     : {unsupported if unsupported else 'none'}")
    print(f"Filtering warnings  : {response.warnings if response.warnings else 'none'}")
    print(
        "Interpretation      : grounded correctly"
        if not unsupported and not response.warnings
        else "Interpretation      : review the warnings above; the model referenced "
        "something outside the evidence and it was filtered"
    )


def main() -> int:
    settings = get_azure_settings()
    print(SEPARATOR)
    print("EPOS Lite - live Azure OpenAI verification")
    print(f"Analysis reference date : {ui.format_date(AS_OF)}")
    # Only the boolean state is ever reported; values are never printed.
    print(f"Azure configuration     : {'present' if settings.is_configured else 'missing'}")

    if not settings.is_configured:
        print("\nAI configuration is missing. No call was attempted.")
        print("Set API_KEY and ENDPOINT in a local .env before running this script.")
        return 1

    portfolio = load_portfolio()
    print(
        f"Portfolio loaded        : {len(portfolio.project_ids)} project(s) "
        f"({', '.join(sorted(portfolio.project_ids))})"
    )
    print(f"Live calls to be made   : {len(QUESTIONS)} plus 1 minimal-evidence observation")

    results = [_run_one(question_type, context, portfolio) for question_type, context in QUESTIONS]
    _minimal_evidence_observation(portfolio)

    print(SEPARATOR)
    print("SUMMARY")
    print(f"{'question type':<42}{'status':<18}{'result':<8}")
    for result in results:
        print(
            f"{result['question_type']:<42}{str(result['status']):<18}"
            f"{'PASS' if result['passed'] else 'FAIL':<8}"
        )
    passed = sum(1 for result in results if result["passed"])
    print(f"\n{passed} of {len(results)} question types passed all criteria.")
    print("Criteria: response validated as CopilotResponse, disclaimer exact, at least one")
    print("valid source id, human_review_required true, no fabricated ids surviving.")
    print(SEPARATOR)
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
