"""Governed project Gates, criteria, immutable reviews, and readiness."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from api.crud import (
    apply_update,
    ensure_absent,
    ensure_referenced_in_project,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
    stamp_update,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import (
    GateCriterionTable,
    GateReviewTable,
    GateTable,
    MilestoneTable,
)
from api.schemas import (
    GateCreate,
    GateCriterionAssessmentRequest,
    GateCriterionCreate,
    GateCriterionOut,
    GateCriterionUpdate,
    GateOut,
    GateReadinessFindingOut,
    GateReadinessOut,
    GateReviewCreate,
    GateReviewOut,
    GateTransitionRequest,
    GateUpdate,
)
from api.security.dependencies import ChangeDecider, CurrentUser, WorkManager, WorkUpdater
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import gate_out
from api.services import activity_service
from api.services.record_references import next_reference
from src.gate_rules import (
    GateCriterionStatus,
    GateReadinessAssessment,
    GateRuleError,
    GateStatus,
    assess_gate_rows,
    ensure_gate_configuration_is_editable,
    ensure_gate_criterion_assessment_is_valid,
    ensure_gate_criterion_can_be_assessed,
    ensure_gate_is_ready_for_review,
    ensure_gate_result_is_supported,
    ensure_gate_review_can_be_submitted,
    ensure_gate_review_is_valid,
    ensure_gate_transition,
)

router = APIRouter(prefix="/gates", tags=["gates"])

_GATE_LABEL = "Gate"
_CRITERION_LABEL = "Gate criterion"
_REVIEW_LABEL = "Gate Review"


def _conflict(exc: GateRuleError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _present_gate(row: GateTable) -> GateOut:
    return gate_out(row)


def _present_criterion(row: GateCriterionTable) -> GateCriterionOut:
    return GateCriterionOut.model_validate(row, from_attributes=True)


def _present_review(row: GateReviewTable) -> GateReviewOut:
    return GateReviewOut.model_validate(row, from_attributes=True)


def _get_gate(session: SessionDep, gate_id: str, actor: CurrentUser) -> GateTable:
    row = get_or_404(session, GateTable, gate_id, _GATE_LABEL)
    require_project_access(session, actor, row.project_id)
    return row


def _ensure_milestone(session: SessionDep, milestone_id: str | None, project_id: str) -> None:
    if milestone_id is not None:
        ensure_referenced_in_project(session, MilestoneTable, milestone_id, project_id, "Milestone")


def _ensure_sequence_is_free(
    session: SessionDep, project_id: str, sequence: int, exclude_gate_id: str | None = None
) -> None:
    """Reject a sequence already held in the project.

    Withdrawn Gates keep their sequence because the database constraint spans them, so a
    soft-deleted Gate is reported as a conflict rather than surfacing as a server error.
    """
    statement = select(GateTable).where(
        GateTable.project_id == project_id, GateTable.sequence == sequence
    )
    for holder in session.exec(statement).all():
        if holder.gate_id == exclude_gate_id:
            continue
        state = "withdrawn " if holder.deleted_at is not None else ""
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Gate sequence {sequence} in project {project_id} is already held by "
                f"{state}Gate {holder.gate_id}."
            ),
        )


def _next_sequence(session: SessionDep, project_id: str) -> int:
    """The sequence after every Gate the project has held, withdrawn ones included."""
    held = session.exec(select(GateTable.sequence).where(GateTable.project_id == project_id)).all()
    return max(held, default=0) + 1


def _criteria(session: SessionDep, gate: GateTable) -> list[GateCriterionTable]:
    return sorted(
        [
            row
            for row in list_rows(session, GateCriterionTable, gate.project_id)
            if row.gate_id == gate.gate_id
        ],
        key=lambda row: row.criterion_id,
    )


def _reviews(session: SessionDep, gate: GateTable) -> list[GateReviewTable]:
    statement = select(GateReviewTable).where(GateReviewTable.gate_id == gate.gate_id)
    return sorted(
        session.exec(statement).all(),
        key=lambda row: (row.reviewed_at, row.review_id),
    )


def _current_reviews(session: SessionDep, gate: GateTable) -> list[GateReviewTable]:
    return [row for row in _reviews(session, gate) if row.review_cycle == gate.review_cycle]


def _assessment(session: SessionDep, gate: GateTable) -> GateReadinessAssessment:
    return assess_gate_rows(gate, _criteria(session, gate), _reviews(session, gate))


def _readiness_out(gate: GateTable, result: GateReadinessAssessment) -> GateReadinessOut:
    return GateReadinessOut(
        gate_id=gate.gate_id,
        project_id=gate.project_id,
        state=result.state,
        percentage=result.percentage,
        complete_criterion_ids=list(result.complete_criterion_ids),
        incomplete_criterion_ids=list(result.incomplete_criterion_ids),
        blockers=[
            GateReadinessFindingOut(message=item.message, source_ids=list(item.source_ids))
            for item in result.blockers
        ],
        warnings=[
            GateReadinessFindingOut(message=item.message, source_ids=list(item.source_ids))
            for item in result.warnings
        ],
        evidence_references=list(result.evidence_references),
        latest_review_id=result.latest_review_id,
        latest_review_outcome=result.latest_review_outcome,
        calculated_at=datetime.now(UTC),
        methodology_version=result.methodology_version,
        applicable_baseline=gate.applicable_baseline,
    )


@router.get("", response_model=list[GateOut])
def list_gates(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
) -> list[GateOut]:
    """List live Gates visible to the signed-in user."""
    rows = scope_rows(session, actor, list_rows(session, GateTable, project_id))
    return [
        _present_gate(row) for row in sorted(rows, key=lambda row: (row.project_id, row.sequence))
    ]


@router.get("/{gate_id}", response_model=GateOut)
def get_gate(gate_id: str, session: SessionDep, actor: CurrentUser) -> GateOut:
    """Return one authorized Gate."""
    return _present_gate(_get_gate(session, gate_id, actor))


@router.post("", response_model=GateOut, status_code=status.HTTP_201_CREATED)
def create_gate(payload: GateCreate, session: SessionDep, actor: WorkManager) -> GateOut:
    """Create an unstarted project Gate without inventing criteria or approval."""
    require_project_access(session, actor, payload.project_id, write=True)
    gate_id = payload.gate_id or next_reference(session, payload.project_id, "G")
    ensure_absent(session, GateTable, gate_id, _GATE_LABEL)
    _ensure_milestone(session, payload.milestone_id, payload.project_id)
    sequence = payload.sequence or _next_sequence(session, payload.project_id)
    _ensure_sequence_is_free(session, payload.project_id, sequence)
    row = GateTable(
        **{**payload.model_dump(), "gate_id": gate_id, "sequence": sequence},
        status=GateStatus.NOT_STARTED.value,
    )
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_GATE_LABEL,
        entity_id=row.gate_id,
        project_id=row.project_id,
        summary=f"Created gate {row.gate_id}: {row.gate_name}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present_gate(row)


@router.patch("/{gate_id}", response_model=GateOut)
def update_gate(
    gate_id: str, payload: GateUpdate, session: SessionDep, actor: WorkManager
) -> GateOut:
    """Update Gate configuration before it enters review."""
    row = _get_gate(session, gate_id, actor)
    require_project_access(session, actor, row.project_id, write=True)
    try:
        ensure_gate_configuration_is_editable(row.gate_id, GateStatus(row.status))
    except GateRuleError as exc:
        raise _conflict(exc) from exc
    if "milestone_id" in payload.model_fields_set:
        _ensure_milestone(session, payload.milestone_id, row.project_id)
    if payload.sequence is not None:
        _ensure_sequence_is_free(
            session, row.project_id, payload.sequence, exclude_gate_id=row.gate_id
        )
    before = apply_update(row, payload, actor.email)
    after = payload.model_dump(exclude_unset=True)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_GATE_LABEL,
        entity_id=row.gate_id,
        project_id=row.project_id,
        summary=f"Updated gate {row.gate_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present_gate(row)


@router.post("/{gate_id}/transition", response_model=GateOut)
def transition_gate(
    gate_id: str,
    payload: GateTransitionRequest,
    session: SessionDep,
    actor: WorkManager,
) -> GateOut:
    """Apply one controlled, versioned Gate lifecycle transition."""
    row = _get_gate(session, gate_id, actor)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, payload.row_version)
    current = GateStatus(row.status)
    try:
        ensure_gate_transition(current, payload.target_status)
        readiness = _assessment(session, row)
        if payload.target_status is GateStatus.READY_FOR_REVIEW:
            ensure_gate_is_ready_for_review(readiness)
        ensure_gate_result_is_supported(payload.target_status, readiness)
    except GateRuleError as exc:
        raise _conflict(exc) from exc

    before = {
        "status": row.status,
        "review_cycle": row.review_cycle,
        "actual_review_date": row.actual_review_date,
    }
    if payload.target_status is GateStatus.PREPARING and current in {
        GateStatus.FAILED,
        GateStatus.DEFERRED,
    }:
        row.review_cycle += 1
        row.actual_review_date = None
    row.status = payload.target_status.value
    if payload.target_status in {
        GateStatus.PASSED,
        GateStatus.PASSED_WITH_CONDITIONS,
        GateStatus.FAILED,
        GateStatus.DEFERRED,
    }:
        latest_review = _current_reviews(session, row)[-1]
        row.actual_review_date = latest_review.reviewed_at.date()
    stamp_update(row, actor.email)
    after = {
        "status": row.status,
        "review_cycle": row.review_cycle,
        "actual_review_date": row.actual_review_date,
    }
    session.add(row)
    activity_service.record(
        session,
        action="transitioned",
        entity_type=_GATE_LABEL,
        entity_id=row.gate_id,
        project_id=row.project_id,
        summary=f"Moved gate {row.gate_id} from {current.value} to {row.status}",
        detail=payload.rationale,
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present_gate(row)


@router.get("/{gate_id}/readiness", response_model=GateReadinessOut)
def get_gate_readiness(gate_id: str, session: SessionDep, actor: CurrentUser) -> GateReadinessOut:
    """Return deterministic Gate readiness with supporting source IDs."""
    gate = _get_gate(session, gate_id, actor)
    return _readiness_out(gate, _assessment(session, gate))


@router.get("/{gate_id}/criteria", response_model=list[GateCriterionOut])
def list_gate_criteria(
    gate_id: str, session: SessionDep, actor: CurrentUser
) -> list[GateCriterionOut]:
    """List configured criteria for one authorized Gate."""
    gate = _get_gate(session, gate_id, actor)
    return [_present_criterion(row) for row in _criteria(session, gate)]


@router.post(
    "/{gate_id}/criteria",
    response_model=GateCriterionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_gate_criterion(
    gate_id: str,
    payload: GateCriterionCreate,
    session: SessionDep,
    actor: WorkManager,
) -> GateCriterionOut:
    """Configure one Gate criterion before review."""
    gate = _get_gate(session, gate_id, actor)
    require_project_access(session, actor, gate.project_id, write=True)
    criterion_id = payload.criterion_id or next_reference(session, gate.project_id, "GC")
    ensure_absent(session, GateCriterionTable, criterion_id, _CRITERION_LABEL)
    try:
        ensure_gate_configuration_is_editable(gate.gate_id, GateStatus(gate.status))
    except GateRuleError as exc:
        raise _conflict(exc) from exc
    row = GateCriterionTable(
        **{**payload.model_dump(), "criterion_id": criterion_id},
        gate_id=gate.gate_id,
        project_id=gate.project_id,
    )
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_CRITERION_LABEL,
        entity_id=row.criterion_id,
        project_id=row.project_id,
        summary=f"Created gate criterion {row.criterion_id} for gate {gate.gate_id}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present_criterion(row)


@router.patch("/{gate_id}/criteria/{criterion_id}", response_model=GateCriterionOut)
def update_gate_criterion(
    gate_id: str,
    criterion_id: str,
    payload: GateCriterionUpdate,
    session: SessionDep,
    actor: WorkManager,
) -> GateCriterionOut:
    """Update criterion configuration before review."""
    gate = _get_gate(session, gate_id, actor)
    require_project_access(session, actor, gate.project_id, write=True)
    row = get_or_404(session, GateCriterionTable, criterion_id, _CRITERION_LABEL)
    if row.gate_id != gate.gate_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Gate criterion not found."
        )
    try:
        ensure_gate_configuration_is_editable(gate.gate_id, GateStatus(gate.status))
        if payload.evidence_required is True and row.status == GateCriterionStatus.MET.value:
            ensure_gate_criterion_assessment_is_valid(
                row.criterion_id,
                GateCriterionStatus.MET,
                True,
                row.evidence_reference,
            )
    except GateRuleError as exc:
        raise _conflict(exc) from exc
    before = apply_update(row, payload, actor.email)
    after = payload.model_dump(exclude_unset=True)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_CRITERION_LABEL,
        entity_id=row.criterion_id,
        project_id=row.project_id,
        summary=f"Updated gate criterion {row.criterion_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present_criterion(row)


@router.post(
    "/{gate_id}/criteria/{criterion_id}/assessment",
    response_model=GateCriterionOut,
)
def assess_gate_criterion(
    gate_id: str,
    criterion_id: str,
    payload: GateCriterionAssessmentRequest,
    session: SessionDep,
    actor: WorkUpdater,
) -> GateCriterionOut:
    """Record a versioned human assessment of one configured criterion."""
    gate = _get_gate(session, gate_id, actor)
    require_project_access(session, actor, gate.project_id, write=True)
    row = get_or_404(session, GateCriterionTable, criterion_id, _CRITERION_LABEL)
    if row.gate_id != gate.gate_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Gate criterion not found."
        )
    ensure_row_version(row, payload.row_version)
    try:
        ensure_gate_criterion_can_be_assessed(gate.gate_id, GateStatus(gate.status))
        ensure_gate_criterion_assessment_is_valid(
            row.criterion_id,
            payload.target_status,
            row.evidence_required,
            payload.evidence_reference,
        )
    except GateRuleError as exc:
        raise _conflict(exc) from exc
    before = {
        "status": row.status,
        "evidence_reference": row.evidence_reference,
        "assessment_rationale": row.assessment_rationale,
        "assessed_by": row.assessed_by,
        "assessed_at": row.assessed_at,
    }
    row.status = payload.target_status.value
    row.evidence_reference = payload.evidence_reference
    row.assessment_rationale = payload.rationale
    row.assessed_by = actor.full_name
    row.assessed_at = datetime.now(UTC)
    stamp_update(row, actor.email)
    after = {field: getattr(row, field) for field in before}
    session.add(row)
    activity_service.record(
        session,
        action="assessed",
        entity_type=_CRITERION_LABEL,
        entity_id=row.criterion_id,
        project_id=row.project_id,
        summary=f"Assessed gate criterion {row.criterion_id} as {row.status}",
        detail=payload.rationale,
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present_criterion(row)


@router.delete("/{gate_id}/criteria/{criterion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gate_criterion(
    gate_id: str,
    criterion_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: WorkManager,
) -> None:
    """Withdraw criterion configuration before review."""
    gate = _get_gate(session, gate_id, actor)
    require_project_access(session, actor, gate.project_id, write=True)
    row = get_or_404(session, GateCriterionTable, criterion_id, _CRITERION_LABEL)
    if row.gate_id != gate.gate_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Gate criterion not found."
        )
    ensure_row_version(row, row_version)
    try:
        ensure_gate_configuration_is_editable(gate.gate_id, GateStatus(gate.status))
    except GateRuleError as exc:
        raise _conflict(exc) from exc
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_CRITERION_LABEL,
        entity_id=row.criterion_id,
        project_id=row.project_id,
        summary=f"Deleted gate criterion {row.criterion_id}",
        actor=actor,
    )
    session.commit()


@router.get("/{gate_id}/reviews", response_model=list[GateReviewOut])
def list_gate_reviews(gate_id: str, session: SessionDep, actor: CurrentUser) -> list[GateReviewOut]:
    """List immutable human reviews for one authorized Gate."""
    gate = _get_gate(session, gate_id, actor)
    return [_present_review(row) for row in _reviews(session, gate)]


@router.post(
    "/{gate_id}/reviews",
    response_model=GateReviewOut,
    status_code=status.HTTP_201_CREATED,
)
def create_gate_review(
    gate_id: str,
    payload: GateReviewCreate,
    session: SessionDep,
    actor: ChangeDecider,
) -> GateReviewOut:
    """Append one immutable human decision for the current Gate review cycle."""
    gate = _get_gate(session, gate_id, actor)
    require_project_access(session, actor, gate.project_id, write=True)
    review_id = payload.review_id or next_reference(session, gate.project_id, "GR")
    ensure_absent(session, GateReviewTable, review_id, _REVIEW_LABEL)
    try:
        ensure_gate_review_can_be_submitted(gate.gate_id, GateStatus(gate.status))
        ensure_gate_review_is_valid(review_id, payload.outcome, payload.conditions)
    except GateRuleError as exc:
        raise _conflict(exc) from exc
    existing = _current_reviews(session, gate)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Gate {gate.gate_id} review cycle {gate.review_cycle} already has immutable "
                f"Gate Review {existing[0].review_id}."
            ),
        )
    row = GateReviewTable(
        **{**payload.model_dump(), "review_id": review_id},
        gate_id=gate.gate_id,
        project_id=gate.project_id,
        reviewer=actor.full_name,
        review_cycle=gate.review_cycle,
        created_by=actor.email,
    )
    session.add(row)
    activity_service.record(
        session,
        action="reviewed",
        entity_type=_REVIEW_LABEL,
        entity_id=row.review_id,
        project_id=row.project_id,
        summary=f"Recorded {row.outcome} for gate {gate.gate_id}",
        detail=row.rationale,
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present_review(row)


@router.delete("/{gate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gate(
    gate_id: str, row_version: RowVersionDep, session: SessionDep, actor: WorkManager
) -> None:
    """Withdraw an unreviewed Gate and its mutable criteria."""
    gate = _get_gate(session, gate_id, actor)
    require_project_access(session, actor, gate.project_id, write=True)
    ensure_row_version(gate, row_version)
    reviews = _reviews(session, gate)
    if reviews:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Gate {gate.gate_id} cannot be deleted because immutable Gate Reviews remain: "
                f"{', '.join(row.review_id for row in reviews)}."
            ),
        )
    try:
        ensure_gate_transition(GateStatus(gate.status), GateStatus.WITHDRAWN)
    except GateRuleError as exc:
        raise _conflict(exc) from exc
    for criterion in _criteria(session, gate):
        soft_delete(criterion, actor.email)
        session.add(criterion)
    soft_delete(gate, actor.email)
    gate.status = GateStatus.WITHDRAWN.value
    session.add(gate)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_GATE_LABEL,
        entity_id=gate.gate_id,
        project_id=gate.project_id,
        summary=f"Deleted gate {gate.gate_id}",
        actor=actor,
    )
    session.commit()
