"""Deterministic lifecycle rules for governed project records."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class WorkflowTransitionError(ValueError):
    """Raised when a governed record is asked to skip its lifecycle."""


class ActionStatus(StrEnum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    COMPLETE = "Complete"
    CANCELLED = "Cancelled"


class DecisionStatus(StrEnum):
    PROPOSED = "Proposed"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    SUPERSEDED = "Superseded"


class IssueStatus(StrEnum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class AssumptionStatus(StrEnum):
    PROPOSED = "Proposed"
    VALIDATED = "Validated"
    INVALIDATED = "Invalidated"
    RETIRED = "Retired"


_ISSUE_TRANSITIONS: Final[dict[IssueStatus, frozenset[IssueStatus]]] = {
    IssueStatus.OPEN: frozenset({IssueStatus.IN_PROGRESS, IssueStatus.RESOLVED}),
    IssueStatus.IN_PROGRESS: frozenset({IssueStatus.OPEN, IssueStatus.RESOLVED}),
    IssueStatus.RESOLVED: frozenset({IssueStatus.IN_PROGRESS, IssueStatus.CLOSED}),
    IssueStatus.CLOSED: frozenset({IssueStatus.OPEN}),
}

_ACTION_TRANSITIONS: Final[dict[ActionStatus, frozenset[ActionStatus]]] = {
    ActionStatus.OPEN: frozenset(
        {ActionStatus.IN_PROGRESS, ActionStatus.BLOCKED, ActionStatus.CANCELLED}
    ),
    ActionStatus.IN_PROGRESS: frozenset(
        {
            ActionStatus.OPEN,
            ActionStatus.BLOCKED,
            ActionStatus.COMPLETE,
            ActionStatus.CANCELLED,
        }
    ),
    ActionStatus.BLOCKED: frozenset({ActionStatus.IN_PROGRESS, ActionStatus.CANCELLED}),
    ActionStatus.COMPLETE: frozenset({ActionStatus.IN_PROGRESS}),
    ActionStatus.CANCELLED: frozenset(),
}

_DECISION_TRANSITIONS: Final[dict[DecisionStatus, frozenset[DecisionStatus]]] = {
    DecisionStatus.PROPOSED: frozenset({DecisionStatus.APPROVED, DecisionStatus.REJECTED}),
    DecisionStatus.APPROVED: frozenset({DecisionStatus.SUPERSEDED}),
    DecisionStatus.REJECTED: frozenset(),
    DecisionStatus.SUPERSEDED: frozenset(),
}

_ASSUMPTION_TRANSITIONS: Final[dict[AssumptionStatus, frozenset[AssumptionStatus]]] = {
    AssumptionStatus.PROPOSED: frozenset(
        {AssumptionStatus.VALIDATED, AssumptionStatus.INVALIDATED}
    ),
    AssumptionStatus.VALIDATED: frozenset({AssumptionStatus.INVALIDATED, AssumptionStatus.RETIRED}),
    AssumptionStatus.INVALIDATED: frozenset({AssumptionStatus.PROPOSED, AssumptionStatus.RETIRED}),
    AssumptionStatus.RETIRED: frozenset(),
}


def ensure_issue_transition(current: IssueStatus, target: IssueStatus) -> None:
    """Reject an issue transition not permitted by the lifecycle."""
    _ensure_transition("Issue", current, target, _ISSUE_TRANSITIONS)


def ensure_action_transition(current: ActionStatus, target: ActionStatus) -> None:
    """Reject an action transition not permitted by the lifecycle."""
    _ensure_transition("Action", current, target, _ACTION_TRANSITIONS)


def ensure_decision_transition(current: DecisionStatus, target: DecisionStatus) -> None:
    """Reject an outcome that rewrites or skips a decision state."""
    _ensure_transition("Decision", current, target, _DECISION_TRANSITIONS)


def ensure_assumption_transition(current: AssumptionStatus, target: AssumptionStatus) -> None:
    """Reject an assumption transition not permitted by the lifecycle."""
    _ensure_transition("Assumption", current, target, _ASSUMPTION_TRANSITIONS)


# The shortest reasoning accepted for a recorded approval, rejection or supersession.
MIN_DECISION_RATIONALE_LENGTH: Final[int] = 10

CHANGE_REQUEST_DECIDED_STATUSES: Final[frozenset[str]] = frozenset({"Approved", "Rejected"})

# Risk statuses that end active management and therefore need recorded reasoning.
RISK_STATUSES_REQUIRING_RATIONALE: Final[frozenset[str]] = frozenset({"Closed", "Accepted"})
RISK_CLOSED: Final[str] = "Closed"
# A risk is closed only once nothing is left to mitigate.
MITIGATION_STATUSES_ALLOWING_CLOSURE: Final[frozenset[str]] = frozenset(
    {"Complete", "Not Required"}
)

# Assumption fields that carry the statement a validation outcome was recorded against.
_ASSUMPTION_STATEMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {"assumption_text", "impact_if_false"}
)


def is_change_request_decided(status: str | None) -> bool:
    """True once a change request carries a recorded approval or rejection."""
    decided = {value.lower() for value in CHANGE_REQUEST_DECIDED_STATUSES}
    return (status or "").strip().lower() in decided


def ensure_change_request_undecided(change_request_id: str, status: str) -> None:
    """Reject a second decision, or an edit, once an outcome has been recorded."""
    if is_change_request_decided(status):
        raise WorkflowTransitionError(
            f"Change request {change_request_id} already has a recorded decision ({status}); "
            "raise a new change request instead."
        )


def ensure_decision_is_editable(decision_id: str, status: DecisionStatus) -> None:
    """Freeze a decision's content once an outcome has been recorded against it."""
    if status is not DecisionStatus.PROPOSED:
        raise WorkflowTransitionError(
            f"Decision {decision_id} is {status.value}; its content is frozen. "
            "Record a new decision and supersede this one instead."
        )


def ensure_assumption_is_editable(
    assumption_id: str, status: AssumptionStatus, changed_fields: set[str]
) -> None:
    """Keep a validation outcome attached to the statement it was recorded against."""
    if status is AssumptionStatus.RETIRED:
        raise WorkflowTransitionError(f"Assumption {assumption_id} is Retired and cannot change.")
    if status is not AssumptionStatus.PROPOSED and changed_fields & _ASSUMPTION_STATEMENT_FIELDS:
        raise WorkflowTransitionError(
            f"Assumption {assumption_id} is {status.value}; return it to Proposed before "
            "changing its statement."
        )


def _ensure_transition(
    label: str,
    current: StrEnum,
    target: StrEnum,
    transitions: dict[StrEnum, frozenset[StrEnum]],
) -> None:
    if target not in transitions[current]:
        raise WorkflowTransitionError(
            f"{label} cannot move from {current.value} to {target.value}."
        )
