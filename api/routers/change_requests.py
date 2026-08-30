"""Change request records and their deterministic impact analysis."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.crud import (
    apply_update,
    ensure_absent,
    ensure_not_referenced_by_decisions,
    ensure_referenced_in_project,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
    stamp_update,
    to_entity,
)
from api.dependencies import AsOfDateDep, PortfolioDep, RowVersionDep, SessionDep
from api.models import ChangeRequestTable, RequirementTable
from api.schemas import (
    ChangeDecisionRequest,
    ChangeImpactOut,
    ChangeRequestCreate,
    ChangeRequestOut,
    ChangeRequestUpdate,
)
from api.security.dependencies import ChangeAuthor, ChangeDecider, CurrentUser
from api.security.project_scope import require_project_access, scope_rows
from api.security.separation import ensure_independent_decider
from api.serializers import change_request_out
from api.services import activity_service, analytics_service
from api.services.record_references import next_reference
from src.schemas import ChangeRequest
from src.validators import DataValidationError
from src.workflow_rules import WorkflowTransitionError, ensure_change_request_undecided

router = APIRouter(prefix="/change-requests", tags=["change requests"])

_LABEL = "Change request"


def _present(row: ChangeRequestTable) -> ChangeRequestOut:
    return change_request_out(to_entity(row, ChangeRequest), row.row_version)


@router.get("", response_model=list[ChangeRequestOut])
def list_change_requests(
    session: SessionDep, actor: CurrentUser, project_id: str | None = Query(default=None)
) -> list[ChangeRequestOut]:
    """List change requests, optionally filtered to one project."""
    rows = list_rows(session, ChangeRequestTable, project_id)
    rows = scope_rows(session, actor, rows)
    return [_present(row) for row in sorted(rows, key=lambda c: c.change_request_id)]


@router.get("/{change_request_id}", response_model=ChangeRequestOut)
def get_change_request(
    change_request_id: str, session: SessionDep, actor: CurrentUser
) -> ChangeRequestOut:
    """Return one change request."""
    row = get_or_404(session, ChangeRequestTable, change_request_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.get("/{change_request_id}/impact", response_model=ChangeImpactOut)
def get_change_impact(
    change_request_id: str, portfolio: PortfolioDep, as_of_date: AsOfDateDep, _: CurrentUser
) -> ChangeImpactOut:
    """Return the estimated downstream effect of a change request."""
    try:
        return analytics_service.change_impact(change_request_id, portfolio, as_of_date)
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{_LABEL} {change_request_id} could not be analysed: {exc}",
        ) from exc


@router.post("", response_model=ChangeRequestOut, status_code=status.HTTP_201_CREATED)
def create_change_request(
    payload: ChangeRequestCreate, session: SessionDep, actor: ChangeAuthor
) -> ChangeRequestOut:
    """Raise a change request against an existing requirement."""
    require_project_access(session, actor, payload.project_id, write=True)
    change_request_id = payload.change_request_id or next_reference(
        session, payload.project_id, "CR"
    )
    ensure_absent(session, ChangeRequestTable, change_request_id, _LABEL)
    ensure_referenced_in_project(
        session,
        RequirementTable,
        payload.requirement_id,
        payload.project_id,
        "Requirement",
    )
    values = {**payload.model_dump(), "change_request_id": change_request_id}
    row = ChangeRequestTable(**values, requested_by=actor.full_name)
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type="ChangeRequest",
        entity_id=change_request_id,
        project_id=payload.project_id,
        summary=(f"Raised change request {change_request_id} " f"against {payload.requirement_id}"),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.post("/{change_request_id}/decision", response_model=ChangeRequestOut)
def decide_change_request(
    change_request_id: str,
    payload: ChangeDecisionRequest,
    session: SessionDep,
    actor: ChangeDecider,
) -> ChangeRequestOut:
    """Approve or reject a change request.

    Kept separate from the general update route so that deciding a change needs its own
    permission and always leaves a recorded rationale.
    """
    row = get_or_404(session, ChangeRequestTable, change_request_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, payload.row_version)
    ensure_independent_decider(row, actor, "change request")
    try:
        ensure_change_request_undecided(change_request_id, row.status)
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    before = {"status": row.status}
    row.status = payload.decision.value
    stamp_update(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action=payload.decision.value.lower(),
        entity_type="ChangeRequest",
        entity_id=change_request_id,
        project_id=row.project_id,
        summary=f"{payload.decision.value} change request {change_request_id}",
        detail=payload.rationale,
        changes=activity_service.field_changes(before, {"status": row.status}),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{change_request_id}", response_model=ChangeRequestOut)
def update_change_request(
    change_request_id: str,
    payload: ChangeRequestUpdate,
    session: SessionDep,
    actor: ChangeAuthor,
) -> ChangeRequestOut:
    """Update the supplied fields of a change request that is still awaiting its decision."""
    row = get_or_404(session, ChangeRequestTable, change_request_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    try:
        ensure_change_request_undecided(change_request_id, row.status)
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    before = apply_update(row, payload, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type="ChangeRequest",
        entity_id=change_request_id,
        project_id=row.project_id,
        summary=f"Updated change request {change_request_id}",
        detail=activity_service.describe_changes(before, payload.model_dump(exclude_unset=True)),
        changes=activity_service.field_changes(before, payload.model_dump(exclude_unset=True)),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{change_request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_change_request(
    change_request_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: ChangeDecider,
) -> None:
    """Withdraw a change request. The record is retained for audit."""
    row = get_or_404(session, ChangeRequestTable, change_request_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    ensure_not_referenced_by_decisions(
        session, row.project_id, "related_change_request_id", change_request_id, _LABEL
    )
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type="ChangeRequest",
        entity_id=change_request_id,
        project_id=row.project_id,
        summary=f"Deleted change request {change_request_id}",
        actor=actor,
    )
    session.commit()
