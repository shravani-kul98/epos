"""Deterministic project Gate readiness and lifecycle contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.gate_rules import (
    GateCriterionEvidence,
    GateCriterionStatus,
    GateReadinessState,
    GateReviewEvidence,
    GateReviewOutcome,
    GateRuleError,
    GateStatus,
    assess_gate_readiness,
    ensure_gate_configuration_is_editable,
    ensure_gate_criterion_assessment_is_valid,
    ensure_gate_criterion_can_be_assessed,
    ensure_gate_is_ready_for_review,
    ensure_gate_result_is_supported,
    ensure_gate_review_can_be_submitted,
    ensure_gate_review_is_valid,
    ensure_gate_transition,
    result_for_gate_status,
)

REVIEWED_AT = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)


def _criterion(
    criterion_id: str,
    status: GateCriterionStatus = GateCriterionStatus.MET,
    *,
    mandatory: bool = True,
    evidence_required: bool = False,
    evidence_reference: str | None = None,
) -> GateCriterionEvidence:
    return GateCriterionEvidence(
        criterion_id=criterion_id,
        status=status,
        is_mandatory=mandatory,
        evidence_required=evidence_required,
        evidence_reference=evidence_reference,
    )


def _review(
    outcome: GateReviewOutcome = GateReviewOutcome.APPROVED,
    conditions: str | None = None,
) -> GateReviewEvidence:
    return GateReviewEvidence(
        review_id="GR-1",
        outcome=outcome,
        reviewed_at=REVIEWED_AT,
        conditions=conditions,
    )


def test_gate_without_criteria_is_not_ready_and_has_no_percentage() -> None:
    result = assess_gate_readiness("G-1", [], [])
    assert result.state is GateReadinessState.NOT_READY
    assert result.percentage is None
    assert result.blockers[0].source_ids == ("G-1",)


def test_mandatory_blocker_overrides_a_nonzero_percentage_and_approval() -> None:
    result = assess_gate_readiness(
        "G-1",
        [
            _criterion("GC-1"),
            _criterion("GC-2", GateCriterionStatus.NOT_MET),
        ],
        [_review()],
    )
    assert result.percentage == 50
    assert result.state is GateReadinessState.NOT_READY
    assert result.blockers[0].source_ids == ("GC-2",)


def test_required_evidence_controls_criterion_completion() -> None:
    result = assess_gate_readiness(
        "G-1",
        [_criterion("GC-1", evidence_required=True)],
        [],
    )
    assert result.complete_criterion_ids == ()
    assert result.incomplete_criterion_ids == ("GC-1",)
    assert result.blockers[0].source_ids == ("GC-1",)
    with pytest.raises(GateRuleError, match="GC-1"):
        ensure_gate_criterion_assessment_is_valid("GC-1", GateCriterionStatus.MET, True, None)


def test_complete_mandatory_criteria_are_ready_for_human_review() -> None:
    result = assess_gate_readiness(
        "G-1",
        [_criterion("GC-1", evidence_required=True, evidence_reference="EV-1")],
        [],
    )
    assert result.state is GateReadinessState.READY_FOR_REVIEW
    assert result.percentage == 100
    assert result.evidence_references == ("EV-1",)


def test_human_approval_is_required_for_approved_readiness() -> None:
    result = assess_gate_readiness("G-1", [_criterion("GC-1")], [_review()])
    assert result.state is GateReadinessState.APPROVED
    assert result.latest_review_id == "GR-1"


def test_conditional_approval_requires_and_reports_conditions() -> None:
    with pytest.raises(GateRuleError, match="GR-1"):
        ensure_gate_review_is_valid("GR-1", GateReviewOutcome.APPROVED_WITH_CONDITIONS, None)

    result = assess_gate_readiness(
        "G-1",
        [_criterion("GC-1")],
        [_review(GateReviewOutcome.APPROVED_WITH_CONDITIONS, "Close GC-9 by Friday.")],
    )
    assert result.state is GateReadinessState.APPROVED_WITH_CONDITIONS
    assert result.warnings[-1].source_ids == ("GR-1",)


def test_gate_pass_transition_requires_matching_readiness_and_valid_lifecycle() -> None:
    ready = assess_gate_readiness("G-1", [_criterion("GC-1")], [])
    ensure_gate_is_ready_for_review(ready)
    with pytest.raises(GateRuleError, match="readiness is Ready for Review"):
        ensure_gate_result_is_supported(GateStatus.PASSED, ready)

    approved = assess_gate_readiness("G-1", [_criterion("GC-1")], [_review()])
    ensure_gate_result_is_supported(GateStatus.PASSED, approved)
    ensure_gate_transition(GateStatus.IN_REVIEW, GateStatus.PASSED)
    with pytest.raises(GateRuleError, match="Not Started.*Passed"):
        ensure_gate_transition(GateStatus.NOT_STARTED, GateStatus.PASSED)
    assert result_for_gate_status(GateStatus.PASSED).value == "Passed"
    assert result_for_gate_status(GateStatus.IN_REVIEW) is None


def test_mandatory_blockers_prevent_ready_for_review() -> None:
    blocked = assess_gate_readiness(
        "G-1", [_criterion("GC-1", GateCriterionStatus.NOT_ASSESSED)], []
    )
    with pytest.raises(GateRuleError, match="GC-1"):
        ensure_gate_is_ready_for_review(blocked)


def test_gate_configuration_assessment_and_review_have_distinct_phases() -> None:
    ensure_gate_configuration_is_editable("G-1", GateStatus.PREPARING)
    ensure_gate_criterion_can_be_assessed("G-1", GateStatus.PREPARING)
    ensure_gate_review_can_be_submitted("G-1", GateStatus.IN_REVIEW)
    with pytest.raises(GateRuleError, match="configuration"):
        ensure_gate_configuration_is_editable("G-1", GateStatus.IN_REVIEW)
    with pytest.raises(GateRuleError, match="only while status is Preparing"):
        ensure_gate_criterion_can_be_assessed("G-1", GateStatus.READY_FOR_REVIEW)
    with pytest.raises(GateRuleError, match="only while status is In Review"):
        ensure_gate_review_can_be_submitted("G-1", GateStatus.PREPARING)


def test_failed_and_deferred_results_require_matching_human_reviews() -> None:
    rejected = assess_gate_readiness(
        "G-1", [_criterion("GC-1")], [_review(GateReviewOutcome.REJECTED)]
    )
    ensure_gate_result_is_supported(GateStatus.FAILED, rejected)
    with pytest.raises(GateRuleError, match="matching human review"):
        ensure_gate_result_is_supported(GateStatus.DEFERRED, rejected)
    with pytest.raises(GateRuleError, match="Preparing.*Deferred"):
        ensure_gate_transition(GateStatus.PREPARING, GateStatus.DEFERRED)
