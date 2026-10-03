"""Measure how well Ask EPOS routes real user language.

The harness runs the corpus through the router and reports where it lands. It is deliberately
separate from the assertions in ``test_routing_quality.py``: the report is for reading, the test is
for gating. Run it directly to see the full picture:

    python -m tests.eval.harness
"""

from __future__ import annotations

from collections import defaultdict
from typing import NamedTuple

from api.services import copilot_service
from tests.eval.corpus import ALL_CASES, Case


class Result(NamedTuple):
    """One routed question and how it turned out."""

    case: Case
    actual: str | None

    @property
    def correct(self) -> bool:
        return self.actual == self.case.expected

    @property
    def failure_mode(self) -> str | None:
        """Why the case failed, in the terms that matter for this system."""
        if self.correct:
            return None
        if self.case.expected is None:
            return "false_routing"
        if self.actual is None:
            return "unrouted"
        return "wrong_intent"


class Report(NamedTuple):
    total: int
    passed: int
    failed: list[Result]
    by_style: dict[str, tuple[int, int]]
    by_intent: dict[str, tuple[int, int]]
    failure_modes: dict[str, int]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def rate(self, mode: str) -> float:
        return self.failure_modes.get(mode, 0) / self.total if self.total else 0.0


def run(cases: tuple[Case, ...] = ALL_CASES) -> Report:
    """Route every case and tally the outcome."""
    results = [Result(case, copilot_service.route_intent(case.question)[0]) for case in cases]

    by_style: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_intent: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    failure_modes: dict[str, int] = defaultdict(int)

    for result in results:
        style = by_style[result.case.style]
        intent = by_intent[result.case.expected or "out_of_scope"]
        style[1] += 1
        intent[1] += 1
        if result.correct:
            style[0] += 1
            intent[0] += 1
        else:
            failure_modes[result.failure_mode or "unknown"] += 1

    return Report(
        total=len(results),
        passed=sum(1 for result in results if result.correct),
        failed=[result for result in results if not result.correct],
        by_style={key: (value[0], value[1]) for key, value in sorted(by_style.items())},
        by_intent={key: (value[0], value[1]) for key, value in sorted(by_intent.items())},
        failure_modes=dict(failure_modes),
    )


def format_report(report: Report) -> str:
    """Render the report as plain text."""
    lines = [
        "Ask EPOS routing evaluation",
        "=" * 60,
        f"Cases        : {report.total}",
        f"Passed       : {report.passed}",
        f"Pass rate    : {report.pass_rate:.1%}",
        "",
        "Failure modes",
        "-" * 60,
    ]
    for mode in ("wrong_intent", "unrouted", "false_routing"):
        count = report.failure_modes.get(mode, 0)
        lines.append(f"{mode:<16} {count:>4}  {count / report.total:.1%}")

    lines += ["", "By phrasing style", "-" * 60]
    for style, (passed, total) in report.by_style.items():
        lines.append(f"{style:<18} {passed:>3}/{total:<4} {passed / total:.0%}")

    lines += ["", "By expected intent", "-" * 60]
    for intent, (passed, total) in report.by_intent.items():
        lines.append(f"{intent:<38} {passed:>3}/{total:<4} {passed / total:.0%}")

    if report.failed:
        lines += ["", f"Failures ({len(report.failed)})", "-" * 60]
        for result in report.failed:
            lines.append(
                f"[{result.failure_mode}] {result.case.question!r}\n"
                f"    expected {result.case.expected} got {result.actual}"
            )

    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - developer entry point
    print(format_report(run()))
