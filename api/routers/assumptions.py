"""Governed register of project assumptions and their validation outcomes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from api.crud import (
    apply_update,
    ensure_absent,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
    stamp_update,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import AssumptionTable
from api.schemas import (
    AssumptionCreate,
    AssumptionOut,
    AssumptionTransitionRequest,
    AssumptionUpdate,
)
from api.security.dependencies import AssumptionManager, CurrentUser
from api.security.project_scope import require_project_access, scope_rows
from api.services import activity_service, notification_service, record_owners
from api.services.record_references import next_reference
from src.workflow_rules import (
    AssumptionStatus,
    WorkflowTransitionError,
    ensure_assumption_is_editable,
    ensure_assumption_transition,
)

router = APIRouter(prefix="/assumptions", tags=["assumptions"])

_LABEL = "Assumption"


def _present(row: AssumptionTable) -> AssumptionOut:
    return AssumptionOut.model_validate(row, from_attributes=True)


def _notify_owner(
    session: SessionDep, row: AssumptionTable, previous_owner_id: int | None, actor: CurrentUser
) -> None:
    due = f" Validate by {row.validation_due_date:%d %b %Y}." if row.validation_due_date else ""
    record_owners.notify_new_owner(
        session,
        owner_id=row.owner_user_id,
        previous_owner_id=previous_owner_id,
        kind=notification_service.ASSUMPTION_ASSIGNED,
        title=f"You own assumption {row.assumption_id}",
        detail=f"{row.assumption_text}{due}",
        project_id=row.project_id,
        entity_type=_LABEL,
        entity_id=row.assumption_id,
        actor=actor,
    )


@router.get("", response_model=list[AssumptionOut])
def list_assumptions(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
    assumption_status: Annotated[AssumptionStatus | None, Query(alias="status")] = None,
) -> list[AssumptionOut]:
    """List visible assumptions, optionally narrowed by project or lifecycle state."""
    rows = scope_rows(session, actor, list_rows(session, AssumptionTable, project_id))
    if assumption_status is not None:
        rows = [row for row in rows if row.status == assumption_status.value]
    rows.sort(key=lambda row: row.assumption_id)
    return [_present(row) for row in rows]


@router.get("/{assumption_id}", response_model=AssumptionOut)
def get_assumption(assumption_id: str, session: SessionDep, actor: CurrentUser) -> AssumptionOut:
    """Return one assumption within the caller's current project scope."""
    row = get_or_404(session, AssumptionTable, assumption_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=AssumptionOut, status_code=status.HTTP_201_CREATED)
def create_assumption(
    payload: AssumptionCreate,
    session: SessionDep,
    actor: AssumptionManager,
) -> AssumptionOut:
    """Record an assumption in the Proposed state."""
    require_project_access(session, actor, payload.project_id, write=True)
    assumption_id = payload.assumption_id or next_reference(session, payload.project_id, "ASM")
    ensure_absent(session, AssumptionTable, assumption_id, _LABEL)
    row = AssumptionTable(
        **{**payload.model_dump(exclude={"owner_user_id"}), "assumption_id": assumption_id},
        status=AssumptionStatus.PROPOSED.value,
    )
    record_owners.apply_owner_link(
        session,
        row,
        payload.project_id,
        id_field="owner_user_id",
        name_field="owner",
        user_id=payload.owner_user_id,
        id_supplied=payload.owner_user_id is not None,
        name_supplied=False,
    )
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="proposed",
        entity_type=_LABEL,
        entity_id=row.assumption_id,
        project_id=row.project_id,
        summary=f"Proposed assumption {row.assumption_id}",
        actor=actor,
    )
    _notify_owner(session, row, None, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{assumption_id}", response_model=AssumptionOut)
def update_assumption(
    assumption_id: str,
    payload: AssumptionUpdate,
    session: SessionDep,
    actor: AssumptionManager,
) -> AssumptionOut:
    """Update assumption facts without bypassing validation."""
    row = get_or_404(session, AssumptionTable, assumption_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    try:
        ensure_assumption_is_editable(
            assumption_id, AssumptionStatus(row.status), payload.model_fields_set
        )
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    previous_owner_id = row.owner_user_id
    before = apply_update(row, payload, actor.email, exclude=frozenset({"owner_user_id"}))
    before.update(
        record_owners.apply_owner_link(
            session,
            row,
            row.project_id,
            id_field="owner_user_id",
            name_field="owner",
            user_id=payload.owner_user_id,
            id_supplied="owner_user_id" in payload.model_fields_set,
            name_supplied="owner" in payload.model_fields_set,
        )
    )
    after = {field: getattr(row, field) for field in before}
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=assumption_id,
        project_id=row.project_id,
        summary=f"Updated assumption {assumption_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    _notify_owner(session, row, previous_owner_id, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


@router.post("/{assumption_id}/transition", response_model=AssumptionOut)
def transition_assumption(
    assumption_id: str,
    payload: AssumptionTransitionRequest,
    session: SessionDep,
    actor: AssumptionManager,
) -> AssumptionOut:
    """Record a validated assumption transition and its supporting evidence."""
    row = get_or_404(session, AssumptionTable, assumption_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, payload.row_version)
    current = AssumptionStatus(row.status)
    try:
        ensure_assumption_transition(current, payload.target_status)
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    before = {
        "status": row.status,
        "validation_evidence": row.validation_evidence,
        "validated_by": row.validated_by,
        "validated_at": row.validated_at,
    }
    row.status = payload.target_status.value
    if payload.target_status in {
        AssumptionStatus.VALIDATED,
        AssumptionStatus.INVALIDATED,
    }:
        row.validation_evidence = payload.evidence
        row.validated_by = actor.full_name
        row.validated_at = datetime.now(UTC)
    elif payload.target_status is AssumptionStatus.PROPOSED:
        row.validation_evidence = None
        row.validated_by = None
        row.validated_at = None
    stamp_update(row, actor.email)
    after = {
        "status": row.status,
        "validation_evidence": row.validation_evidence,
        "validated_by": row.validated_by,
        "validated_at": row.validated_at,
    }
    session.add(row)
    activity_service.record(
        session,
        action="transitioned",
        entity_type=_LABEL,
        entity_id=assumption_id,
        project_id=row.project_id,
        summary=(f"Moved assumption {assumption_id} from {current.value} to {row.status}"),
        detail=payload.evidence,
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{assumption_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assumption(
    assumption_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: AssumptionManager,
) -> None:
    """Withdraw an assumption while retaining its audit history."""
    row = get_or_404(session, AssumptionTable, assumption_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="withdrew",
        entity_type=_LABEL,
        entity_id=assumption_id,
        project_id=row.project_id,
        summary=f"Withdrew assumption {assumption_id}",
        actor=actor,
    )
    session.commit()
