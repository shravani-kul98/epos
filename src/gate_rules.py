"""Deterministic project Gate readiness and lifecycle rules."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Final


class GateStatus(StrEnum):
    NOT_STARTED = "Not Started"
    PREPARING = "Preparing"
    READY_FOR_REVIEW = "Ready for Review"
    IN_REVIEW = "In Review"
    PASSED = "Passed"
    PASSED_WITH_CONDITIONS = "Passed with Conditions"
    FAILED = "Failed"
    DEFERRED = "Deferred"
    WITHDRAWN = "Withdrawn"


class GateCriterionStatus(StrEnum):
    NOT_ASSESSED = "Not Assessed"
    MET = "Met"
    NOT_MET = "Not Met"


class GateReviewOutcome(StrEnum):
    APPROVED = "Approved"
    APPROVED_WITH_CONDITIONS = "Approved with Conditions"
    REJECTED = "Rejected"
    DEFERRED = "Deferred"


class GateReadinessState(StrEnum):
    NOT_READY = "Not Ready"
    READY_FOR_REVIEW = "Ready for Review"
    APPROVED = "Approved"
    APPROVED_WITH_CONDITIONS = "Approved with Conditions"


class GateResult(StrEnum):
    PASSED = "Passed"
    PASSED_WITH_CONDITIONS = "Passed with Conditions"
    FAILED = "Failed"
    DEFERRED = "Deferred"


GATE_READINESS_METHODOLOGY_VERSION: Final[str] = "1.0"


class GateRuleError(ValueError):
    """Raised when Gate evidence or a requested lifecycle transition is invalid."""


@dataclass(frozen=True)
class GateCriterionEvidence:
    """The authoritative criterion facts used by the readiness calculation."""

    criterion_id: str
    status: GateCriterionStatus
    is_mandatory: bool
    evidence_required: bool
    evidence_reference: str | None


@dataclass(frozen=True)
class GateReviewEvidence:
    """One immutable human Gate review outcome."""

    review_id: str
    outcome: GateReviewOutcome
    reviewed_at: datetime
    conditions: str | None = None


@dataclass(frozen=True)
class GateReadinessFinding:
    """One readiness conclusion and the records that support it."""

    message: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class GateReadinessAssessment:
    """Deterministic readiness facts for one Gate."""

    state: GateReadinessState
    percentage: int | None
    complete_criterion_ids: tuple[str, ...]
    incomplete_criterion_ids: tuple[str, ...]
    blockers: tuple[GateReadinessFinding, ...]
    warnings: tuple[GateReadinessFinding, ...]
    evidence_references: tuple[str, ...]
    latest_review_id: str | None
    latest_review_outcome: GateReviewOutcome | None
    methodology_version: str = GATE_READINESS_METHODOLOGY_VERSION


_ALLOWED_GATE_TRANSITIONS: Final[dict[GateStatus, frozenset[GateStatus]]] = {
    GateStatus.NOT_STARTED: frozenset({GateStatus.PREPARING, GateStatus.WITHDRAWN}),
    GateStatus.PREPARING: frozenset({GateStatus.READY_FOR_REVIEW, GateStatus.WITHDRAWN}),
    GateStatus.READY_FOR_REVIEW: frozenset(
        {
            GateStatus.IN_REVIEW,
            GateStatus.PREPARING,
            GateStatus.WITHDRAWN,
        }
    ),
    GateStatus.IN_REVIEW: frozenset(
        {
            GateStatus.PASSED,
            GateStatus.PASSED_WITH_CONDITIONS,
            GateStatus.FAILED,
            GateStatus.DEFERRED,
            GateStatus.WITHDRAWN,
        }
    ),
    GateStatus.FAILED: frozenset({GateStatus.PREPARING, GateStatus.WITHDRAWN}),
    GateStatus.DEFERRED: frozenset({GateStatus.PREPARING, GateStatus.WITHDRAWN}),
    GateStatus.PASSED: frozenset(),
    GateStatus.PASSED_WITH_CONDITIONS: frozenset(),
    GateStatus.WITHDRAWN: frozenset(),
}


def ensure_gate_review_is_valid(
    review_id: str, outcome: GateReviewOutcome, conditions: str | None
) -> None:
    """Require conditions exactly when a reviewer grants conditional approval."""
    has_conditions = bool(conditions and conditions.strip())
    if outcome is GateReviewOutcome.APPROVED_WITH_CONDITIONS and not has_conditions:
        raise GateRuleError(f"Gate Review {review_id} requires recorded conditions.")
    if outcome is not GateReviewOutcome.APPROVED_WITH_CONDITIONS and has_conditions:
        raise GateRuleError(
            f"Gate Review {review_id} can record conditions only for conditional approval."
        )


def ensure_gate_criterion_assessment_is_valid(
    criterion_id: str,
    status: GateCriterionStatus,
    evidence_required: bool,
    evidence_reference: str | None,
) -> None:
    """Prevent a criterion from being marked Met without its required evidence."""
    if (
        status is GateCriterionStatus.MET
        and evidence_required
        and not (evidence_reference and evidence_reference.strip())
    ):
        raise GateRuleError(
            f"Gate criterion {criterion_id} requires evidence before it can be Met."
        )


def result_for_gate_status(status: GateStatus) -> GateResult | None:
    """Return the recorded Gate result represented by a terminal review status."""
    try:
        return GateResult(status.value)
    except ValueError:
        return None


def ensure_gate_transition(current: GateStatus, target: GateStatus) -> None:
    """Reject lifecycle jumps outside the controlled Gate workflow."""
    if target not in _ALLOWED_GATE_TRANSITIONS[current]:
        raise GateRuleError(f"Gate cannot transition from {current.value} to {target.value}.")


def ensure_gate_configuration_is_editable(gate_id: str, status: GateStatus) -> None:
    """Freeze Gate configuration once it has been submitted for review."""
    if status not in {GateStatus.NOT_STARTED, GateStatus.PREPARING}:
        raise GateRuleError(
            f"Gate {gate_id} configuration cannot change while status is {status.value}."
        )


def ensure_gate_criterion_can_be_assessed(gate_id: str, status: GateStatus) -> None:
    """Allow criterion assessment only while the Gate is being prepared."""
    if status is not GateStatus.PREPARING:
        raise GateRuleError(
            f"Gate {gate_id} criteria can be assessed only while status is Preparing."
        )


def ensure_gate_review_can_be_submitted(gate_id: str, status: GateStatus) -> None:
    """Allow an immutable human review only during the review state."""
    if status is not GateStatus.IN_REVIEW:
        raise GateRuleError(f"Gate {gate_id} can be reviewed only while status is In Review.")


def ensure_gate_result_is_supported(
    target: GateStatus, assessment: GateReadinessAssessment
) -> None:
    """Prevent a passing Gate result without matching deterministic readiness."""
    expected = {
        GateStatus.PASSED: GateReadinessState.APPROVED,
        GateStatus.PASSED_WITH_CONDITIONS: GateReadinessState.APPROVED_WITH_CONDITIONS,
    }.get(target)
    if expected is not None and assessment.state is not expected:
        source_ids = sorted(
            {
                source_id
                for finding in (*assessment.blockers, *assessment.warnings)
                for source_id in finding.source_ids
            }
        )
        evidence = f" Supporting source records: {', '.join(source_ids)}." if source_ids else ""
        raise GateRuleError(
            f"Gate cannot transition to {target.value} while readiness is "
            f"{assessment.state.value}.{evidence}"
        )
    expected_review = {
        GateStatus.FAILED: GateReviewOutcome.REJECTED,
        GateStatus.DEFERRED: GateReviewOutcome.DEFERRED,
    }.get(target)
    if expected_review is not None and assessment.latest_review_outcome is not expected_review:
        source_id = assessment.latest_review_id or "no Gate Review"
        raise GateRuleError(
            f"Gate cannot transition to {target.value} without a matching human review. "
            f"Supporting source record: {source_id}."
        )


def ensure_gate_is_ready_for_review(assessment: GateReadinessAssessment) -> None:
    """Prevent review from starting while mandatory readiness blockers remain."""
    if assessment.state is GateReadinessState.NOT_READY:
        source_ids = sorted(
            {source_id for finding in assessment.blockers for source_id in finding.source_ids}
        )
        raise GateRuleError(
            "Gate is not ready for review. Supporting source records: " f"{', '.join(source_ids)}."
        )


def assess_gate_readiness(
    gate_id: str,
    criteria: Iterable[GateCriterionEvidence],
    reviews: Iterable[GateReviewEvidence],
) -> GateReadinessAssessment:
    """Calculate Gate readiness from configured criteria and immutable reviews."""
    criterion_list = list(criteria)
    review_list = list(reviews)
    criterion_ids = [criterion.criterion_id for criterion in criterion_list]
    if len(set(criterion_ids)) != len(criterion_ids):
        raise GateRuleError(f"Gate {gate_id} contains duplicate criterion source records.")

    complete: list[str] = []
    incomplete: list[str] = []
    blockers: list[GateReadinessFinding] = []
    warnings: list[GateReadinessFinding] = []
    evidence_references: set[str] = set()

    if not criterion_list:
        blockers.append(
            GateReadinessFinding(
                message="No criteria have been added to this gate yet.", source_ids=(gate_id,)
            )
        )

    for criterion in sorted(criterion_list, key=lambda item: item.criterion_id):
        has_required_evidence = not criterion.evidence_required or bool(
            criterion.evidence_reference and criterion.evidence_reference.strip()
        )
        is_complete = criterion.status is GateCriterionStatus.MET and has_required_evidence
        if is_complete:
            complete.append(criterion.criterion_id)
            if criterion.evidence_reference:
                evidence_references.add(criterion.evidence_reference.strip())
            continue

        incomplete.append(criterion.criterion_id)
        if criterion.status is GateCriterionStatus.MET:
            reason = "is marked Met but required evidence is missing"
        elif criterion.status is GateCriterionStatus.NOT_MET:
            reason = "is Not Met"
        else:
            reason = "has not been assessed"
        finding = GateReadinessFinding(
            message=f"Criterion {criterion.criterion_id} {reason}.",
            source_ids=(criterion.criterion_id,),
        )
        (blockers if criterion.is_mandatory else warnings).append(finding)

    latest_review = max(
        review_list,
        key=lambda review: (review.reviewed_at, review.review_id),
        default=None,
    )
    if latest_review is None:
        warnings.append(
            GateReadinessFinding(
                message="No review decision has been recorded for this gate yet.",
                source_ids=(gate_id,),
            )
        )
    elif latest_review.outcome in {GateReviewOutcome.REJECTED, GateReviewOutcome.DEFERRED}:
        blockers.append(
            GateReadinessFinding(
                message=(f"Latest Gate review outcome is {latest_review.outcome.value}."),
                source_ids=(latest_review.review_id,),
            )
        )
    elif latest_review.outcome is GateReviewOutcome.APPROVED_WITH_CONDITIONS:
        ensure_gate_review_is_valid(
            latest_review.review_id, latest_review.outcome, latest_review.conditions
        )
        warnings.append(
            GateReadinessFinding(
                message=f"Gate approval has conditions: {latest_review.conditions}",
                source_ids=(latest_review.review_id,),
            )
        )

    if blockers:
        state = GateReadinessState.NOT_READY
    elif latest_review is None:
        state = GateReadinessState.READY_FOR_REVIEW
    elif latest_review.outcome is GateReviewOutcome.APPROVED:
        state = GateReadinessState.APPROVED
    else:
        state = GateReadinessState.APPROVED_WITH_CONDITIONS

    percentage = round(len(complete) * 100 / len(criterion_list)) if criterion_list else None
    return GateReadinessAssessment(
        state=state,
        percentage=percentage,
        complete_criterion_ids=tuple(complete),
        incomplete_criterion_ids=tuple(incomplete),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        evidence_references=tuple(sorted(evidence_references)),
        latest_review_id=latest_review.review_id if latest_review else None,
        latest_review_outcome=latest_review.outcome if latest_review else None,
    )


def assess_gate_rows(
    gate: Any, criteria: Iterable[Any], reviews: Iterable[Any]
) -> GateReadinessAssessment:
    """Readiness of one stored Gate from stored criterion and review rows.

    Rows are read by attribute. Only the Gate's own criteria and the reviews of its current review
    cycle count, so a review from an earlier cycle never decides today's readiness.
    """
    return assess_gate_readiness(
        gate.gate_id,
        (
            GateCriterionEvidence(
                criterion_id=row.criterion_id,
                status=GateCriterionStatus(row.status),
                is_mandatory=row.is_mandatory,
                evidence_required=row.evidence_required,
                evidence_reference=row.evidence_reference,
            )
            for row in criteria
            if row.gate_id == gate.gate_id
        ),
        (
            GateReviewEvidence(
                review_id=row.review_id,
                outcome=GateReviewOutcome(row.outcome),
                reviewed_at=row.reviewed_at,
                conditions=row.conditions,
            )
            for row in reviews
            if row.gate_id == gate.gate_id and row.review_cycle == gate.review_cycle
        ),
    )
