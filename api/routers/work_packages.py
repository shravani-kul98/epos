"""Governed engineering Work Package records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.crud import (
    apply_update,
    ensure_absent,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import DeliverableTable, WorkPackageTable
from api.schemas import WorkPackageCreate, WorkPackageOut, WorkPackageUpdate
from api.security.dependencies import CurrentUser, WorkManager
from api.security.project_scope import require_project_access, scope_rows
from api.services import activity_service
from api.services.record_references import next_reference

router = APIRouter(prefix="/work-packages", tags=["work packages"])

_LABEL = "Work Package"


def _present(row: WorkPackageTable) -> WorkPackageOut:
    return WorkPackageOut.model_validate(row, from_attributes=True)


@router.get("", response_model=list[WorkPackageOut])
def list_work_packages(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
) -> list[WorkPackageOut]:
    """List live Work Packages visible to the signed-in user."""
    rows = scope_rows(session, actor, list_rows(session, WorkPackageTable, project_id))
    return [_present(row) for row in sorted(rows, key=lambda item: item.work_package_id)]


@router.get("/{work_package_id}", response_model=WorkPackageOut)
def get_work_package(
    work_package_id: str, session: SessionDep, actor: CurrentUser
) -> WorkPackageOut:
    """Return one authorized Work Package."""
    row = get_or_404(session, WorkPackageTable, work_package_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=WorkPackageOut, status_code=status.HTTP_201_CREATED)
def create_work_package(
    payload: WorkPackageCreate, session: SessionDep, actor: WorkManager
) -> WorkPackageOut:
    """Create a Work Package in an authorized project."""
    require_project_access(session, actor, payload.project_id, write=True)
    work_package_id = payload.work_package_id or next_reference(session, payload.project_id, "WP")
    ensure_absent(session, WorkPackageTable, work_package_id, _LABEL)
    row = WorkPackageTable(**{**payload.model_dump(), "work_package_id": work_package_id})
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=row.work_package_id,
        project_id=row.project_id,
        summary=f"Created Work Package {row.work_package_id}: {row.work_package_name}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{work_package_id}", response_model=WorkPackageOut)
def update_work_package(
    work_package_id: str,
    payload: WorkPackageUpdate,
    session: SessionDep,
    actor: WorkManager,
) -> WorkPackageOut:
    """Update Work Package facts using optimistic concurrency."""
    row = get_or_404(session, WorkPackageTable, work_package_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    before = apply_update(row, payload, actor.email)
    after = payload.model_dump(exclude_unset=True)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=row.work_package_id,
        project_id=row.project_id,
        summary=f"Updated Work Package {row.work_package_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{work_package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_package(
    work_package_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: WorkManager,
) -> None:
    """Withdraw an empty Work Package while retaining its audit history."""
    row = get_or_404(session, WorkPackageTable, work_package_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    child_ids = sorted(
        child.deliverable_id
        for child in list_rows(session, DeliverableTable, row.project_id)
        if child.work_package_id == row.work_package_id
    )
    if child_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Work Package {row.work_package_id} cannot be withdrawn while live "
                f"Deliverables remain: {', '.join(child_ids)}."
            ),
        )
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=row.work_package_id,
        project_id=row.project_id,
        summary=f"Deleted Work Package {row.work_package_id}",
        actor=actor,
    )
    session.commit()
