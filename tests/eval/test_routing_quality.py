"""Routing quality gates.

The evaluation corpus is large and deliberately messy. These tests turn it into a gate so a change
to the matcher cannot quietly make Ask EPOS worse at understanding real questions. The thresholds
are floors, not targets: they exist to catch regression, and the report in ``harness`` is what to
read when one of them trips.
"""

from __future__ import annotations

import pytest

from tests.eval.corpus import ALL_CASES, Case
from tests.eval.harness import format_report, run


@pytest.fixture(scope="module")
def report():
    return run()


class TestOverall:
    def test_the_corpus_is_large_enough_to_mean_something(self) -> None:
        assert len(ALL_CASES) >= 200

    def test_almost_every_question_reaches_the_right_intent(self, report) -> None:
        assert report.pass_rate >= 0.97, format_report(report)

    def test_no_in_scope_question_is_left_unrouted(self, report) -> None:
        assert report.rate("unrouted") <= 0.01, format_report(report)

    def test_nothing_out_of_scope_is_answered_confidently(self, report) -> None:
        """A wrong answer to an unrelated question is worse than no answer at all."""
        assert report.rate("false_routing") == 0.0, format_report(report)


class TestByStyle:
    @pytest.mark.parametrize(
        "style",
        [
            "direct",
            "conversational",
            "executive",
            "engineering",
            "casual",
            "vague",
            "typos",
            "synonyms",
            "adversarial",
            "fragment",
        ],
    )
    def test_every_way_of_asking_works(self, report, style: str) -> None:
        passed, total = report.by_style[style]

        assert passed / total >= 0.9, f"{style}: {passed}/{total}\n{format_report(report)}"

    def test_out_of_domain_questions_are_always_declined(self, report) -> None:
        passed, total = report.by_style["out_of_domain"]

        assert passed == total, format_report(report)

    def test_instruction_injection_is_always_declined(self, report) -> None:
        passed, total = report.by_style["prompt_injection"]

        assert passed == total, format_report(report)


class TestByIntent:
    def test_no_intent_is_left_behind(self, report) -> None:
        """An intent that only works for one phrasing is a trap for the next user."""
        weak = {
            intent: f"{passed}/{total}"
            for intent, (passed, total) in report.by_intent.items()
            if passed / total < 0.8
        }

        assert weak == {}, format_report(report)

    def test_every_supported_intent_is_covered_by_the_corpus(self) -> None:
        covered = {case.expected for case in ALL_CASES if case.expected}
        from api.services.intent_matcher import _PAIRS

        assert set(_PAIRS.values()) - covered == set()

    def test_each_intent_has_several_phrasings_tested(self) -> None:
        counts: dict[str, int] = {}
        for case in ALL_CASES:
            if case.expected:
                counts[case.expected] = counts.get(case.expected, 0) + 1

        thin = {intent: count for intent, count in counts.items() if count < 3}
        assert thin == {}, f"too few phrasings tested for: {thin}"


class TestCorpusHygiene:
    def test_no_question_appears_twice(self) -> None:
        seen: dict[str, Case] = {}
        duplicates = []
        for case in ALL_CASES:
            key = case.question.lower()
            if key in seen and seen[key].expected != case.expected:
                duplicates.append(case.question)
            seen[key] = case
        assert duplicates == []

    def test_every_case_declares_a_style(self) -> None:
        assert all(case.style for case in ALL_CASES)
