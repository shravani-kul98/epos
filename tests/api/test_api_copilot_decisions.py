"""Ask EPOS reading the decision log.

Decisions are not engine input, so they reach the router separately. These tests cover the
routing and the record-based answers; nothing here contacts a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from api.services import copilot_answers as answers
from api.services import copilot_service
from src.ui_formatting import ANALYSIS_DATE


@dataclass
class _Decision:
    """The subset of a decision row the answers actually read."""

    decision_id: str
    project_id: str
    title: str
    category: str
    owner: str
    status: str
    decision_date: date
    rationale: str | None = None
    related_change_request_id: str | None = None
    related_milestone_id: str | None = None


@pytest.fixture
def decisions() -> list[_Decision]:
    return [
        _Decision(
            "DEC-100",
            "P-002",
            "Move the pilot to Q4",
            "Schedule",
            "Alex Morgan",
            "Proposed",
            date(2026, 8, 12),
        ),
        _Decision(
            "DEC-101",
            "P-007",
            "Adopt the revised attribute mapping",
            "Scope",
            "Priya Nair",
            "Approved",
            date(2026, 8, 5),
            rationale="Required for regulatory compliance.",
            related_change_request_id="CR-042",
        ),
        _Decision(
            "DEC-102",
            "P-002",
            "Second-source the cell supplier",
            "Supply",
            "Alex Morgan",
            "Proposed",
            date(2026, 8, 20),
        ),
    ]


class TestRouting:
    @pytest.mark.parametrize(
        "question",
        [
            "which decisions need approval?",
            "what decisions are waiting?",
            "show me the decision log",
            "which decisions are pending?",
        ],
    )
    def test_decision_questions_reach_the_decision_log(self, question: str) -> None:
        intent, _ = copilot_service.route_intent(question)
        assert intent in {answers.PENDING_DECISIONS, answers.PROJECT_DECISIONS}

    def test_a_change_request_question_still_reaches_change_control(self) -> None:
        """The decision log and change control must not be confused for each other."""
        intent, _ = copilot_service.route_intent("what needs a decision?")
        assert intent == answers.PENDING_CHANGE_DECISIONS


class TestPendingDecisions:
    def test_only_undecided_entries_are_reported(self, csv_portfolio, decisions) -> None:
        answer = copilot_service.ask(
            "which decisions need approval?", csv_portfolio, ANALYSIS_DATE, decisions=decisions
        )
        assert answer.status == "ok"
        assert set(answer.source_ids) == {"DEC-100", "DEC-102"}

    def test_an_approved_decision_is_never_reported_as_waiting(
        self, csv_portfolio, decisions
    ) -> None:
        answer = copilot_service.ask(
            "which decisions need approval?", csv_portfolio, ANALYSIS_DATE, decisions=decisions
        )
        assert "DEC-101" not in answer.source_ids

    def test_an_empty_log_says_so_without_inventing_anything(self, csv_portfolio) -> None:
        answer = copilot_service.ask(
            "which decisions need approval?", csv_portfolio, ANALYSIS_DATE, decisions=[]
        )
        assert answer.source_ids == []
        assert answer.key_findings == []

    def test_a_lookup_needs_no_human_review(self, csv_portfolio, decisions) -> None:
        answer = copilot_service.ask(
            "which decisions are pending?", csv_portfolio, ANALYSIS_DATE, decisions=decisions
        )
        assert answer.human_review_required is False


class TestProjectDecisions:
    def test_decisions_are_scoped_to_the_named_project(self, csv_portfolio, decisions) -> None:
        answer = answers.project_decisions(decisions, "P-002")
        assert set(answer.source_ids) == {"DEC-100", "DEC-102"}

    def test_recorded_reasoning_is_carried_into_the_answer(self, decisions) -> None:
        answer = answers.project_decisions(decisions, "P-007")
        assert "regulatory compliance" in " ".join(answer.key_findings).lower()

    def test_a_project_with_no_decisions_is_reported_honestly(self, decisions) -> None:
        answer = answers.project_decisions(decisions, "P-019")
        assert answer.source_ids == []
        assert "P-019" in answer.executive_summary


class TestEvidence:
    def test_every_cited_decision_appears_as_evidence(self, csv_portfolio, decisions) -> None:
        answer = copilot_service.ask(
            "which decisions need approval?", csv_portfolio, ANALYSIS_DATE, decisions=decisions
        )
        cited = set(answer.source_ids)
        evidenced = {record.record_id for record in answer.evidence}
        assert cited == evidenced

    def test_evidence_records_read_as_decisions(self, csv_portfolio, decisions) -> None:
        answer = copilot_service.ask(
            "which decisions need approval?", csv_portfolio, ANALYSIS_DATE, decisions=decisions
        )
        assert {record.record_type for record in answer.evidence} == {"decision"}

    def test_a_linked_change_request_is_carried_as_evidence(self, decisions) -> None:
        answer = answers.project_decisions(decisions, "P-007")
        record = next(r for r in answer.evidence if r.record_id == "DEC-101")
        assert record.fields["change_request"] == "CR-042"
