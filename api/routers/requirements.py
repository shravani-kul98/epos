"""Requirement records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api import clock
from api.crud import (
    apply_update,
    ensure_absent,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
    to_entity,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import ChangeRequestTable, DecisionTable, RequirementTable, TraceLinkTable
from api.schemas import RequirementCreate, RequirementOut, RequirementUpdate
from api.security.dependencies import CurrentUser, RequirementManager
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import requirement_out
from api.services import activity_service
from api.services.record_references import next_reference
from src.schemas import Requirement

router = APIRouter(prefix="/requirements", tags=["requirements"])

_LABEL = "Requirement"


def _present(row: RequirementTable) -> RequirementOut:
    return requirement_out(to_entity(row, Requirement), row.row_version)


@router.get("", response_model=list[RequirementOut])
def list_requirements(
    session: SessionDep, actor: CurrentUser, project_id: str | None = Query(default=None)
) -> list[RequirementOut]:
    """List requirements, optionally filtered to one project."""
    rows = list_rows(session, RequirementTable, project_id)
    rows = scope_rows(session, actor, rows)
    return [_present(row) for row in sorted(rows, key=lambda r: r.requirement_id)]


@router.get("/{requirement_id}", response_model=RequirementOut)
def get_requirement(requirement_id: str, session: SessionDep, actor: CurrentUser) -> RequirementOut:
    """Return one requirement."""
    row = get_or_404(session, RequirementTable, requirement_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=RequirementOut, status_code=status.HTTP_201_CREATED)
def create_requirement(
    payload: RequirementCreate, session: SessionDep, actor: RequirementManager
) -> RequirementOut:
    """Create a requirement. Omit ``requirement_id`` to receive the next project reference."""
    require_project_access(session, actor, payload.project_id, write=True)
    requirement_id = payload.requirement_id or next_reference(session, payload.project_id, "REQ")
    ensure_absent(session, RequirementTable, requirement_id, _LABEL)
    row = RequirementTable(
        **payload.model_dump(exclude={"requirement_id"}),
        requirement_id=requirement_id,
        last_updated_date=clock.utc_today(),
    )
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=requirement_id,
        project_id=payload.project_id,
        summary=f"Created requirement {requirement_id}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{requirement_id}", response_model=RequirementOut)
def update_requirement(
    requirement_id: str,
    payload: RequirementUpdate,
    session: SessionDep,
    actor: RequirementManager,
) -> RequirementOut:
    """Update the supplied fields of a requirement."""
    row = get_or_404(session, RequirementTable, requirement_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    before = apply_update(row, payload, actor.email)
    row.last_updated_date = clock.utc_today()
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=requirement_id,
        project_id=row.project_id,
        summary=f"Updated requirement {requirement_id}",
        detail=activity_service.describe_changes(before, payload.model_dump(exclude_unset=True)),
        changes=activity_service.field_changes(before, payload.model_dump(exclude_unset=True)),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requirement(
    requirement_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: RequirementManager,
) -> None:
    """Withdraw a requirement. The record is retained for audit."""
    row = get_or_404(session, RequirementTable, requirement_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    reference_ids = {
        change.change_request_id
        for change in list_rows(session, ChangeRequestTable, row.project_id)
        if change.requirement_id == row.requirement_id
    }
    reference_ids.update(
        link.trace_link_id
        for link in list_rows(session, TraceLinkTable, row.project_id)
        if (link.source_type == "Requirement" and link.source_id == row.requirement_id)
        or (link.target_type == "Requirement" and link.target_id == row.requirement_id)
    )
    reference_ids.update(
        decision.decision_id
        for decision in list_rows(session, DecisionTable, row.project_id)
        if decision.related_requirement_id == row.requirement_id
    )
    if reference_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Requirement {row.requirement_id} cannot be withdrawn while live references "
                f"remain: {', '.join(sorted(reference_ids))}."
            ),
        )
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=requirement_id,
        project_id=row.project_id,
        summary=f"Deleted requirement {requirement_id}",
        actor=actor,
    )
    session.commit()
