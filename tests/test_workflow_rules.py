"""Deterministic governance workflow contracts."""

from __future__ import annotations

import pytest

from src.workflow_rules import (
    ActionStatus,
    AssumptionStatus,
    DecisionStatus,
    IssueStatus,
    WorkflowTransitionError,
    ensure_action_transition,
    ensure_assumption_transition,
    ensure_decision_transition,
    ensure_issue_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ActionStatus.OPEN, ActionStatus.IN_PROGRESS),
        (ActionStatus.IN_PROGRESS, ActionStatus.BLOCKED),
        (ActionStatus.BLOCKED, ActionStatus.IN_PROGRESS),
        (ActionStatus.IN_PROGRESS, ActionStatus.COMPLETE),
        (ActionStatus.COMPLETE, ActionStatus.IN_PROGRESS),
    ],
)
def test_action_lifecycle_allows_owned_progression(
    current: ActionStatus, target: ActionStatus
) -> None:
    ensure_action_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ActionStatus.OPEN, ActionStatus.COMPLETE),
        (ActionStatus.BLOCKED, ActionStatus.COMPLETE),
        (ActionStatus.CANCELLED, ActionStatus.OPEN),
    ],
)
def test_action_lifecycle_rejects_skipped_or_terminal_transitions(
    current: ActionStatus, target: ActionStatus
) -> None:
    with pytest.raises(WorkflowTransitionError):
        ensure_action_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DecisionStatus.PROPOSED, DecisionStatus.APPROVED),
        (DecisionStatus.PROPOSED, DecisionStatus.REJECTED),
        (DecisionStatus.APPROVED, DecisionStatus.SUPERSEDED),
    ],
)
def test_decision_lifecycle_allows_reviewed_outcomes(
    current: DecisionStatus, target: DecisionStatus
) -> None:
    ensure_decision_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DecisionStatus.PROPOSED, DecisionStatus.SUPERSEDED),
        (DecisionStatus.REJECTED, DecisionStatus.APPROVED),
        (DecisionStatus.SUPERSEDED, DecisionStatus.APPROVED),
    ],
)
def test_decision_lifecycle_rejects_rewrites_and_skips(
    current: DecisionStatus, target: DecisionStatus
) -> None:
    with pytest.raises(WorkflowTransitionError):
        ensure_decision_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IssueStatus.OPEN, IssueStatus.IN_PROGRESS),
        (IssueStatus.OPEN, IssueStatus.RESOLVED),
        (IssueStatus.RESOLVED, IssueStatus.CLOSED),
        (IssueStatus.CLOSED, IssueStatus.OPEN),
    ],
)
def test_issue_lifecycle_allows_governed_progression(
    current: IssueStatus, target: IssueStatus
) -> None:
    ensure_issue_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IssueStatus.OPEN, IssueStatus.CLOSED),
        (IssueStatus.IN_PROGRESS, IssueStatus.CLOSED),
        (IssueStatus.CLOSED, IssueStatus.RESOLVED),
    ],
)
def test_issue_lifecycle_rejects_skipped_transitions(
    current: IssueStatus, target: IssueStatus
) -> None:
    with pytest.raises(WorkflowTransitionError):
        ensure_issue_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (AssumptionStatus.PROPOSED, AssumptionStatus.VALIDATED),
        (AssumptionStatus.PROPOSED, AssumptionStatus.INVALIDATED),
        (AssumptionStatus.VALIDATED, AssumptionStatus.RETIRED),
        (AssumptionStatus.INVALIDATED, AssumptionStatus.PROPOSED),
    ],
)
def test_assumption_lifecycle_allows_reviewed_outcomes(
    current: AssumptionStatus, target: AssumptionStatus
) -> None:
    ensure_assumption_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (AssumptionStatus.PROPOSED, AssumptionStatus.RETIRED),
        (AssumptionStatus.RETIRED, AssumptionStatus.PROPOSED),
        (AssumptionStatus.RETIRED, AssumptionStatus.VALIDATED),
    ],
)
def test_assumption_lifecycle_rejects_skipped_or_terminal_transitions(
    current: AssumptionStatus, target: AssumptionStatus
) -> None:
    with pytest.raises(WorkflowTransitionError):
        ensure_assumption_transition(current, target)
