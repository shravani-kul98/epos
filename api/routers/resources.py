"""Weekly allocation records behind the team-capacity factor."""

from __future__ import annotations

from fastapi import APIRouter, status

from api.crud import (
    apply_update,
    ensure_absent,
    ensure_row_version,
    get_or_404,
    soft_delete,
    stamp_create,
    to_entity,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import ResourceTable
from api.schemas import ResourceCreate, ResourceOut, ResourceUpdate
from api.security.dependencies import WorkManager
from api.security.project_scope import require_project_access
from api.serializers import resource_out
from api.services import activity_service
from api.services.record_references import next_reference
from src.schemas import Resource

router = APIRouter(prefix="/resources", tags=["resources"])

_LABEL = "Resource allocation"


def _present(row: ResourceTable) -> ResourceOut:
    return resource_out(to_entity(row, Resource), row.row_version)


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(
    payload: ResourceCreate, session: SessionDep, actor: WorkManager
) -> ResourceOut:
    """Record one person's allocated and available hours for a week."""
    require_project_access(session, actor, payload.project_id, write=True)
    resource_id = payload.resource_id or next_reference(session, payload.project_id, "RES")
    ensure_absent(session, ResourceTable, resource_id, _LABEL)
    row = ResourceTable(**{**payload.model_dump(), "resource_id": resource_id})
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=resource_id,
        project_id=payload.project_id,
        summary=(
            f"Recorded {payload.allocated_hours} of {payload.capacity_hours} hours for "
            f"{payload.resource_name}, week of {payload.week_start_date.isoformat()}"
        ),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{resource_id}", response_model=ResourceOut)
def update_resource(
    resource_id: str, payload: ResourceUpdate, session: SessionDep, actor: WorkManager
) -> ResourceOut:
    """Correct an allocation. The previous values stay in the audit trail."""
    row = get_or_404(session, ResourceTable, resource_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    before = apply_update(row, payload, actor.email)
    after = payload.model_dump(exclude_unset=True)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=resource_id,
        project_id=row.project_id,
        summary=f"Updated the allocation for {row.resource_name}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    resource_id: str, row_version: RowVersionDep, session: SessionDep, actor: WorkManager
) -> None:
    """Withdraw an allocation. The record is retained for audit."""
    row = get_or_404(session, ResourceTable, resource_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=resource_id,
        project_id=row.project_id,
        summary=f"Withdrew the allocation for {row.resource_name}",
        actor=actor,
    )
    session.commit()
