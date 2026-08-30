"""Governed engineering dependency records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ValidationError
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
    to_entity,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import DependencyTable, MilestoneTable, TaskTable
from api.schemas import DependencyCreate, DependencyOut, DependencyUpdate
from api.security.dependencies import CurrentUser, WorkManager
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import dependency_out
from api.services import activity_service
from api.services.record_references import next_reference
from src.delivery_rules import (
    SCHEDULABLE_ENDPOINT_TYPES,
    DeliveryNetworkError,
    DependencyEndpointType,
    ensure_acyclic_dependency_network,
    ensure_dependency_metadata,
    ensure_unique_dependency_edges,
)
from src.schemas import GovernedDependency

router = APIRouter(prefix="/dependencies", tags=["dependencies"])

_LABEL = "Dependency"
_ENDPOINT_TABLES = {
    DependencyEndpointType.TASK: (TaskTable, "Task"),
    DependencyEndpointType.MILESTONE: (MilestoneTable, "Milestone"),
}
_TOPOLOGY_FIELDS = {
    "predecessor_type",
    "predecessor_id",
    "successor_type",
    "successor_id",
    "relationship_type",
    "lag_days",
}


def _present(row: DependencyTable) -> DependencyOut:
    return dependency_out(to_entity(row, GovernedDependency), row.row_version)


def _validate(values: dict[str, object], *, require_complete: bool) -> GovernedDependency:
    try:
        dependency = GovernedDependency.model_validate(values)
        ensure_dependency_metadata(
            dependency.edge,
            dependency.relationship_type,
            dependency.lag_days,
            require_complete=require_complete,
        )
    except ValidationError as exc:
        detail = "; ".join(error["msg"] for error in exc.errors())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
        ) from exc
    except DeliveryNetworkError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return dependency


def _ensure_endpoints(session: SessionDep, dependency: GovernedDependency) -> None:
    for endpoint_type, endpoint_id in (
        (dependency.predecessor_type, dependency.predecessor_id),
        (dependency.successor_type, dependency.successor_id),
    ):
        if endpoint_type not in SCHEDULABLE_ENDPOINT_TYPES:
            continue
        table, label = _ENDPOINT_TABLES[endpoint_type]
        ensure_referenced_in_project(session, table, endpoint_id, dependency.project_id, label)


def _ensure_network(
    session: SessionDep,
    dependency: GovernedDependency,
    *,
    replacing_id: str | None = None,
) -> None:
    all_rows = session.exec(
        select(DependencyTable).where(DependencyTable.project_id == dependency.project_id)
    ).all()
    historical_edges = [
        to_entity(row, GovernedDependency).edge
        for row in all_rows
        if row.dependency_id != replacing_id
    ]
    live_edges = [
        to_entity(row, GovernedDependency).edge
        for row in all_rows
        if row.dependency_id != replacing_id and row.deleted_at is None
    ]
    try:
        ensure_unique_dependency_edges([*historical_edges, dependency.edge])
        ensure_acyclic_dependency_network([*live_edges, dependency.edge])
    except DeliveryNetworkError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("", response_model=list[DependencyOut])
def list_dependencies(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
) -> list[DependencyOut]:
    """List dependency edges visible to the signed-in user."""
    rows = scope_rows(session, actor, list_rows(session, DependencyTable, project_id))
    return [_present(row) for row in sorted(rows, key=lambda item: item.dependency_id)]


@router.get("/{dependency_id}", response_model=DependencyOut)
def get_dependency(dependency_id: str, session: SessionDep, actor: CurrentUser) -> DependencyOut:
    """Return one authorized dependency edge."""
    row = get_or_404(session, DependencyTable, dependency_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=DependencyOut, status_code=status.HTTP_201_CREATED)
def create_dependency(
    payload: DependencyCreate, session: SessionDep, actor: WorkManager
) -> DependencyOut:
    """Create a validated, acyclic dependency edge."""
    require_project_access(session, actor, payload.project_id, write=True)
    dependency_id = payload.dependency_id or next_reference(session, payload.project_id, "DEP")
    ensure_absent(session, DependencyTable, dependency_id, _LABEL)
    dependency = _validate(
        {**payload.model_dump(), "dependency_id": dependency_id}, require_complete=True
    )
    _ensure_endpoints(session, dependency)
    _ensure_network(session, dependency)

    row = DependencyTable(**dependency.model_dump())
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=row.dependency_id,
        project_id=row.project_id,
        summary=f"Created dependency {row.dependency_id}: {row.dependency_name}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{dependency_id}", response_model=DependencyOut)
def update_dependency(
    dependency_id: str,
    payload: DependencyUpdate,
    session: SessionDep,
    actor: WorkManager,
) -> DependencyOut:
    """Update an edge only when its resulting network remains valid."""
    row = get_or_404(session, DependencyTable, dependency_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    changes = payload.model_dump(exclude_unset=True, exclude={"row_version"})
    candidate = to_entity(row, GovernedDependency).model_dump()
    candidate.update(changes)
    dependency = _validate(candidate, require_complete=bool(_TOPOLOGY_FIELDS.intersection(changes)))
    _ensure_endpoints(session, dependency)
    _ensure_network(session, dependency, replacing_id=dependency_id)

    before = apply_update(row, payload, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=dependency_id,
        project_id=row.project_id,
        summary=f"Updated dependency {dependency_id}",
        detail=activity_service.describe_changes(before, changes),
        changes=activity_service.field_changes(before, changes),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dependency(
    dependency_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: WorkManager,
) -> None:
    """Withdraw an edge while retaining its audit history."""
    row = get_or_404(session, DependencyTable, dependency_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=dependency_id,
        project_id=row.project_id,
        summary=f"Deleted dependency {dependency_id}",
        actor=actor,
    )
    session.commit()
