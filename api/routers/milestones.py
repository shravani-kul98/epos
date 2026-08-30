"""Milestone records."""

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
    to_entity,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import (
    DecisionTable,
    DependencyTable,
    GateTable,
    MilestoneTable,
    TaskTable,
    TraceLinkTable,
)
from api.schemas import MilestoneCreate, MilestoneOut, MilestoneUpdate
from api.security.dependencies import CurrentUser, WorkManager
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import milestone_out
from api.services import activity_service
from api.services.record_references import next_reference
from src.schemas import DeliveryMilestone

router = APIRouter(prefix="/milestones", tags=["milestones"])

_LABEL = "Milestone"


def _present(row: MilestoneTable) -> MilestoneOut:
    return milestone_out(to_entity(row, DeliveryMilestone), row.row_version)


@router.get("", response_model=list[MilestoneOut])
def list_milestones(
    session: SessionDep, actor: CurrentUser, project_id: str | None = Query(default=None)
) -> list[MilestoneOut]:
    """List milestones, optionally filtered to one project."""
    rows = list_rows(session, MilestoneTable, project_id)
    rows = scope_rows(session, actor, rows)
    return [_present(row) for row in sorted(rows, key=lambda m: m.milestone_id)]


@router.get("/{milestone_id}", response_model=MilestoneOut)
def get_milestone(milestone_id: str, session: SessionDep, actor: CurrentUser) -> MilestoneOut:
    """Return one milestone."""
    row = get_or_404(session, MilestoneTable, milestone_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=MilestoneOut, status_code=status.HTTP_201_CREATED)
def create_milestone(
    payload: MilestoneCreate, session: SessionDep, actor: WorkManager
) -> MilestoneOut:
    """Create a milestone."""
    require_project_access(session, actor, payload.project_id, write=True)
    milestone_id = payload.milestone_id or next_reference(session, payload.project_id, "M")
    ensure_absent(session, MilestoneTable, milestone_id, _LABEL)
    row = MilestoneTable(**{**payload.model_dump(), "milestone_id": milestone_id})
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=milestone_id,
        project_id=payload.project_id,
        summary=f"Created milestone {payload.milestone_name}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{milestone_id}", response_model=MilestoneOut)
def update_milestone(
    milestone_id: str, payload: MilestoneUpdate, session: SessionDep, actor: WorkManager
) -> MilestoneOut:
    """Update the supplied fields of a milestone."""
    row = get_or_404(session, MilestoneTable, milestone_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    before = apply_update(row, payload, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=milestone_id,
        project_id=row.project_id,
        summary=f"Updated milestone {row.milestone_name}",
        detail=activity_service.describe_changes(before, payload.model_dump(exclude_unset=True)),
        changes=activity_service.field_changes(before, payload.model_dump(exclude_unset=True)),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(
    milestone_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: WorkManager,
) -> None:
    """Withdraw a milestone. The record is retained for audit."""
    row = get_or_404(session, MilestoneTable, milestone_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    reference_ids = {
        gate.gate_id
        for gate in list_rows(session, GateTable, row.project_id)
        if gate.milestone_id == row.milestone_id
    }
    reference_ids.update(
        task.task_id
        for task in list_rows(session, TaskTable, row.project_id)
        if task.milestone_id == row.milestone_id
    )
    reference_ids.update(
        dependency.dependency_id
        for dependency in list_rows(session, DependencyTable, row.project_id)
        if (
            dependency.predecessor_type == "Milestone"
            and dependency.predecessor_id == row.milestone_id
        )
        or (
            dependency.successor_type == "Milestone" and dependency.successor_id == row.milestone_id
        )
    )
    reference_ids.update(
        link.trace_link_id
        for link in list_rows(session, TraceLinkTable, row.project_id)
        if (link.source_type == "Milestone" and link.source_id == row.milestone_id)
        or (link.target_type == "Milestone" and link.target_id == row.milestone_id)
    )
    reference_ids.update(
        decision.decision_id
        for decision in list_rows(session, DecisionTable, row.project_id)
        if decision.related_milestone_id == row.milestone_id
    )
    if reference_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Milestone {row.milestone_id} cannot be withdrawn while live references "
                f"remain: {', '.join(sorted(reference_ids))}."
            ),
        )
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=milestone_id,
        project_id=row.project_id,
        summary=f"Deleted milestone {row.milestone_name}",
        actor=actor,
    )
    session.commit()
