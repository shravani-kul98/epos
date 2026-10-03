"""Unit checks for the shared rules behind the governance and security hardening."""

from __future__ import annotations

import pytest

from api.security.rate_limit import SlidingWindowLimit
from api.services.copilot_answers import my_tasks
from src import config
from src import scoring_rules as sr
from src.ai_assistant import unsupported_identifier_warnings
from src.data_loader import PortfolioData
from src.health_engine import calculate_project_health
from src.schemas import CopilotResponse
from src.workflow_rules import (
    AssumptionStatus,
    DecisionStatus,
    WorkflowTransitionError,
    ensure_assumption_is_editable,
    ensure_change_request_undecided,
    ensure_decision_is_editable,
    is_change_request_decided,
)
from tests.conftest import AS_OF, TEST_PROJECT_ID


# ------------------------------------------------------------------ risk status
@pytest.mark.parametrize(
    ("status", "active"),
    [
        ("Open", True),
        ("Mitigating", True),
        ("in mitigation", True),
        ("Closed", False),
        (" accepted ", False),
        ("Watching", True),
        (None, True),
    ],
)
def test_only_closed_or_accepted_risks_stop_counting(status: str | None, active: bool) -> None:
    assert sr.is_active_risk_status(status) is active


def test_a_risk_with_an_unrecognised_status_still_carries_exposure(
    make_project, make_risk, make_portfolio, as_of_date
) -> None:
    risk = make_risk(probability=5, impact=5, mitigation_owner=None, status="Watching")
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], risks=[risk]), as_of_date
    )

    assert result.factor_scores["risk_exposure"] < 100.0


# ------------------------------------------------------------------ workflow rules
@pytest.mark.parametrize(("status", "decided"), [("Approved", True), ("rejected", True)])
def test_a_decided_change_is_final(status: str, decided: bool) -> None:
    assert is_change_request_decided(status) is decided
    with pytest.raises(WorkflowTransitionError):
        ensure_change_request_undecided("CR-1", status)


@pytest.mark.parametrize("status", ["Proposed", "Raised", "Open", None])
def test_an_undecided_change_can_still_be_decided(status: str | None) -> None:
    assert is_change_request_decided(status) is False
    if status is not None:
        ensure_change_request_undecided("CR-1", status)


@pytest.mark.parametrize("status", [s for s in DecisionStatus if s is not DecisionStatus.PROPOSED])
def test_only_a_proposed_decision_is_editable(status: DecisionStatus) -> None:
    ensure_decision_is_editable("DEC-1", DecisionStatus.PROPOSED)
    with pytest.raises(WorkflowTransitionError):
        ensure_decision_is_editable("DEC-1", status)


def test_an_assessed_assumption_keeps_its_statement() -> None:
    ensure_assumption_is_editable("A-1", AssumptionStatus.PROPOSED, {"assumption_text"})
    ensure_assumption_is_editable("A-1", AssumptionStatus.VALIDATED, {"owner", "row_version"})
    for status in (AssumptionStatus.VALIDATED, AssumptionStatus.INVALIDATED):
        with pytest.raises(WorkflowTransitionError):
            ensure_assumption_is_editable("A-1", status, {"impact_if_false"})
    with pytest.raises(WorkflowTransitionError):
        ensure_assumption_is_editable("A-1", AssumptionStatus.RETIRED, {"owner"})


# ------------------------------------------------------------------ request limits
def test_a_sliding_window_forgets_events_once_they_age_out() -> None:
    now = [0.0]
    limit = SlidingWindowLimit(2, 10.0, clock=lambda: now[0])

    limit.record("key")
    assert limit.retry_after("key") is None
    limit.record("key")
    assert limit.retry_after("key") == 11
    assert limit.retry_after("other") is None

    now[0] = 10.0
    assert limit.retry_after("key") is None


def test_a_reset_clears_a_key() -> None:
    limit = SlidingWindowLimit(1, 60.0)
    limit.record("key")
    assert limit.retry_after("key") is not None

    limit.reset("key")

    assert limit.retry_after("key") is None


# ------------------------------------------------------------------ grounding
def _reply(finding: str) -> CopilotResponse:
    return CopilotResponse(
        executive_summary="Summary.",
        key_findings=[finding],
        recommended_actions=[],
        source_ids=[],
        human_review_required=True,
        disclaimer=config.AI_DISCLAIMER,
    )


def test_an_invented_generated_reference_is_rejected() -> None:
    evidence = '{"record_id": "T-P-002-001"}'

    assert (
        unsupported_identifier_warnings(_reply("T-P-002-001 is late."), evidence, "evidence") == []
    )
    warnings = unsupported_identifier_warnings(_reply("T-P-002-999 is late."), evidence, "evidence")
    assert warnings and "T-P-002-999" in warnings[0]


# ------------------------------------------------------------------ personal work
def test_assigned_work_is_matched_by_account_before_name(make_task) -> None:
    portfolio = PortfolioData(
        tasks=[
            make_task(task_id="T-1", owner="Former Name", owner_user_id=7),
            make_task(task_id="T-2", owner="Pat Owner", owner_user_id=8),
            make_task(task_id="T-3", owner="Pat Owner", owner_user_id=None),
        ]
    )

    answer = my_tasks(portfolio, "Pat Owner", AS_OF, owner_user_id=7)

    assert sorted(answer.source_ids) == ["T-1", "T-3"]
