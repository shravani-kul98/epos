"""Governed engineering Deliverable records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.crud import (
    apply_update,
    ensure_absent,
    ensure_referenced_in_project,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import DeliverableTable, TaskTable, WorkPackageTable
from api.schemas import DeliverableCreate, DeliverableOut, DeliverableUpdate
from api.security.dependencies import CurrentUser, WorkManager
from api.security.project_scope import require_project_access, scope_rows
from api.services import activity_service
from api.services.record_references import next_reference

router = APIRouter(prefix="/deliverables", tags=["deliverables"])

_LABEL = "Deliverable"


def _present(row: DeliverableTable) -> DeliverableOut:
    return DeliverableOut.model_validate(row, from_attributes=True)


def _ensure_work_package(session: SessionDep, work_package_id: str | None, project_id: str) -> None:
    if work_package_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A Deliverable must belong to a Work Package.",
        )
    ensure_referenced_in_project(
        session, WorkPackageTable, work_package_id, project_id, "Work Package"
    )


@router.get("", response_model=list[DeliverableOut])
def list_deliverables(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
) -> list[DeliverableOut]:
    """List live Deliverables visible to the signed-in user."""
    rows = scope_rows(session, actor, list_rows(session, DeliverableTable, project_id))
    return [_present(row) for row in sorted(rows, key=lambda item: item.deliverable_id)]


@router.get("/{deliverable_id}", response_model=DeliverableOut)
def get_deliverable(deliverable_id: str, session: SessionDep, actor: CurrentUser) -> DeliverableOut:
    """Return one authorized Deliverable."""
    row = get_or_404(session, DeliverableTable, deliverable_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=DeliverableOut, status_code=status.HTTP_201_CREATED)
def create_deliverable(
    payload: DeliverableCreate, session: SessionDep, actor: WorkManager
) -> DeliverableOut:
    """Create a Deliverable beneath a Work Package in the same project."""
    require_project_access(session, actor, payload.project_id, write=True)
    deliverable_id = payload.deliverable_id or next_reference(session, payload.project_id, "DL")
    ensure_absent(session, DeliverableTable, deliverable_id, _LABEL)
    _ensure_work_package(session, payload.work_package_id, payload.project_id)
    row = DeliverableTable(**{**payload.model_dump(), "deliverable_id": deliverable_id})
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=row.deliverable_id,
        project_id=row.project_id,
        summary=f"Created Deliverable {row.deliverable_id}: {row.deliverable_name}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{deliverable_id}", response_model=DeliverableOut)
def update_deliverable(
    deliverable_id: str,
    payload: DeliverableUpdate,
    session: SessionDep,
    actor: WorkManager,
) -> DeliverableOut:
    """Update Deliverable facts using optimistic concurrency."""
    row = get_or_404(session, DeliverableTable, deliverable_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    if "work_package_id" in payload.model_fields_set:
        _ensure_work_package(session, payload.work_package_id, row.project_id)
    before = apply_update(row, payload, actor.email)
    after = payload.model_dump(exclude_unset=True)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=row.deliverable_id,
        project_id=row.project_id,
        summary=f"Updated Deliverable {row.deliverable_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{deliverable_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deliverable(
    deliverable_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: WorkManager,
) -> None:
    """Withdraw an empty Deliverable while retaining its audit history."""
    row = get_or_404(session, DeliverableTable, deliverable_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    child_ids = sorted(
        child.task_id
        for child in list_rows(session, TaskTable, row.project_id)
        if child.deliverable_id == row.deliverable_id
    )
    if child_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Deliverable {row.deliverable_id} cannot be withdrawn while live Tasks "
                f"remain: {', '.join(child_ids)}."
            ),
        )
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=row.deliverable_id,
        project_id=row.project_id,
        summary=f"Deleted Deliverable {row.deliverable_id}",
        actor=actor,
    )
    session.commit()
