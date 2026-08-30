"""Decision records: what was decided, why, and what it affects.

Authorisation reuses the change-control permissions rather than introducing new ones. Proposing a
decision carries the same authority as raising a change request; recording an outcome carries the
same authority as deciding one. That keeps the whole security model reviewable in one place.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api import clock
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
    ChangeRequestTable,
    DecisionTable,
    MilestoneTable,
    RequirementTable,
    RiskTable,
)
from api.schemas import (
    DecisionCreate,
    DecisionOut,
    DecisionOutcomeRequest,
    DecisionStatus,
    DecisionUpdate,
)
from api.security.dependencies import ChangeAuthor, ChangeDecider, CurrentUser
from api.security.project_scope import require_project_access, scope_rows
from api.security.separation import ensure_independent_decider
from api.services import activity_service
from api.services.record_references import next_reference
from src.workflow_rules import (
    WorkflowTransitionError,
    ensure_decision_is_editable,
    ensure_decision_transition,
)

router = APIRouter(prefix="/decisions", tags=["decisions"])

_LABEL = "Decision"

_RELATED_REFERENCES = (
    ("related_milestone_id", MilestoneTable, "Milestone"),
    ("related_risk_id", RiskTable, "Risk"),
    ("related_change_request_id", ChangeRequestTable, "Change request"),
    ("related_requirement_id", RequirementTable, "Requirement"),
)


def _present(row: DecisionTable) -> DecisionOut:
    return DecisionOut.model_validate(row, from_attributes=True)


def _ensure_related_records(
    session: SessionDep,
    project_id: str,
    payload: DecisionCreate | DecisionUpdate,
) -> None:
    for field_name, table, label in _RELATED_REFERENCES:
        record_id = getattr(payload, field_name)
        if record_id is not None:
            ensure_referenced_in_project(session, table, record_id, project_id, label)


@router.get("", response_model=list[DecisionOut])
def list_decisions(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
    decision_status: str | None = Query(default=None, alias="status"),
) -> list[DecisionOut]:
    """Every decision the caller can see, optionally narrowed by project or status."""
    rows = list_rows(session, DecisionTable, project_id)
    rows = scope_rows(session, actor, rows)
    if decision_status:
        wanted = decision_status.strip().lower()
        rows = [row for row in rows if row.status.lower() == wanted]
    rows.sort(key=lambda row: (row.decision_date, row.decision_id), reverse=True)
    return [_present(row) for row in rows]


@router.get("/{decision_id}", response_model=DecisionOut)
def read_decision(decision_id: str, session: SessionDep, actor: CurrentUser) -> DecisionOut:
    row = get_or_404(session, DecisionTable, decision_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
def create_decision(
    payload: DecisionCreate, session: SessionDep, actor: ChangeAuthor
) -> DecisionOut:
    """Record a proposed decision. It carries no outcome until one is decided."""
    require_project_access(session, actor, payload.project_id, write=True)
    decision_id = payload.decision_id or next_reference(session, payload.project_id, "DEC")
    ensure_absent(session, DecisionTable, decision_id, _LABEL)
    _ensure_related_records(session, payload.project_id, payload)

    row = DecisionTable(
        **{**payload.model_dump(), "decision_id": decision_id},
        status=DecisionStatus.PROPOSED.value,
    )
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="proposed",
        entity_type="Decision",
        entity_id=decision_id,
        project_id=payload.project_id,
        summary=f"Proposed decision {decision_id}: {payload.title}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{decision_id}", response_model=DecisionOut)
def update_decision(
    decision_id: str, payload: DecisionUpdate, session: SessionDep, actor: ChangeAuthor
) -> DecisionOut:
    """Amend a proposed decision. The outcome is set only through the outcome endpoint."""
    row = get_or_404(session, DecisionTable, decision_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    try:
        ensure_decision_is_editable(decision_id, DecisionStatus(row.status))
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _ensure_related_records(session, row.project_id, payload)
    before = apply_update(row, payload, actor.email)
    after = payload.model_dump(exclude_unset=True)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type="Decision",
        entity_id=decision_id,
        project_id=row.project_id,
        summary=f"Updated decision {decision_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.post("/{decision_id}/outcome", response_model=DecisionOut)
def record_outcome(
    decision_id: str,
    payload: DecisionOutcomeRequest,
    session: SessionDep,
    actor: ChangeDecider,
) -> DecisionOut:
    """Approve, reject or supersede a decision, always with a recorded rationale."""
    row = get_or_404(session, DecisionTable, decision_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, payload.row_version)
    ensure_independent_decider(row, actor, "decision")
    current = DecisionStatus(row.status)
    target = DecisionStatus(payload.outcome.value)
    try:
        ensure_decision_transition(current, target)
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    before = {
        "status": row.status,
        "approver": row.approver,
        "approval_date": row.approval_date,
        "rationale": row.rationale,
    }

    row.status = payload.outcome.value
    row.approver = actor.full_name
    row.approval_date = clock.utc_today()
    # The proposal's reasoning, if any, stays in full in this event's recorded changes.
    row.rationale = payload.rationale
    stamp_update(row, actor.email)
    session.add(row)

    activity_service.record(
        session,
        action=payload.outcome.value.lower(),
        entity_type="Decision",
        entity_id=decision_id,
        project_id=row.project_id,
        summary=f"{payload.outcome.value} decision {decision_id}: {row.title}",
        detail=payload.rationale,
        changes=activity_service.field_changes(
            before,
            {
                "status": row.status,
                "approver": row.approver,
                "approval_date": row.approval_date,
                "rationale": row.rationale,
            },
        ),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_decision(
    decision_id: str, row_version: RowVersionDep, session: SessionDep, actor: ChangeDecider
) -> None:
    """Withdraw a decision. Soft deleted, so the record survives for audit."""
    row = get_or_404(session, DecisionTable, decision_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="withdrew",
        entity_type="Decision",
        entity_id=decision_id,
        project_id=row.project_id,
        summary=f"Withdrew decision {decision_id}",
        actor=actor,
    )
    session.commit()
