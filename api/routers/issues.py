"""Governed register of present project issues."""

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
from api.models import IssueTable
from api.schemas import IssueCreate, IssueOut, IssueTransitionRequest, IssueUpdate
from api.security.dependencies import CurrentUser, IssueManager
from api.security.project_scope import require_project_access, scope_rows
from api.services import activity_service, notification_service, record_owners
from api.services.record_references import next_reference
from src.workflow_rules import IssueStatus, WorkflowTransitionError, ensure_issue_transition

router = APIRouter(prefix="/issues", tags=["issues"])

_LABEL = "Issue"


def _present(row: IssueTable) -> IssueOut:
    return IssueOut.model_validate(row, from_attributes=True)


def _notify_owner(
    session: SessionDep, row: IssueTable, previous_owner_id: int | None, actor: CurrentUser
) -> None:
    record_owners.notify_new_owner(
        session,
        owner_id=row.owner_user_id,
        previous_owner_id=previous_owner_id,
        kind=notification_service.ISSUE_ASSIGNED,
        title=f"You own issue {row.issue_id}: {row.title}",
        detail=row.description,
        project_id=row.project_id,
        entity_type=_LABEL,
        entity_id=row.issue_id,
        actor=actor,
    )


@router.get("", response_model=list[IssueOut])
def list_issues(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
    issue_status: Annotated[IssueStatus | None, Query(alias="status")] = None,
) -> list[IssueOut]:
    """List visible issues, optionally narrowed by project or lifecycle state."""
    rows = scope_rows(session, actor, list_rows(session, IssueTable, project_id))
    if issue_status is not None:
        rows = [row for row in rows if row.status == issue_status.value]
    rows.sort(key=lambda row: (row.raised_date, row.issue_id), reverse=True)
    return [_present(row) for row in rows]


@router.get("/{issue_id}", response_model=IssueOut)
def get_issue(issue_id: str, session: SessionDep, actor: CurrentUser) -> IssueOut:
    """Return one issue within the caller's current project scope."""
    row = get_or_404(session, IssueTable, issue_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
def create_issue(payload: IssueCreate, session: SessionDep, actor: IssueManager) -> IssueOut:
    """Raise an issue in the Open state."""
    require_project_access(session, actor, payload.project_id, write=True)
    issue_id = payload.issue_id or next_reference(session, payload.project_id, "ISS")
    ensure_absent(session, IssueTable, issue_id, _LABEL)
    row = IssueTable(
        **{**payload.model_dump(exclude={"owner_user_id"}), "issue_id": issue_id},
        status=IssueStatus.OPEN.value,
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
        action="raised",
        entity_type=_LABEL,
        entity_id=row.issue_id,
        project_id=row.project_id,
        summary=f"Raised issue {row.issue_id}: {row.title}",
        actor=actor,
    )
    _notify_owner(session, row, None, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{issue_id}", response_model=IssueOut)
def update_issue(
    issue_id: str,
    payload: IssueUpdate,
    session: SessionDep,
    actor: IssueManager,
) -> IssueOut:
    """Update issue facts without bypassing its lifecycle."""
    row = get_or_404(session, IssueTable, issue_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
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
        entity_id=issue_id,
        project_id=row.project_id,
        summary=f"Updated issue {issue_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    _notify_owner(session, row, previous_owner_id, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


@router.post("/{issue_id}/transition", response_model=IssueOut)
def transition_issue(
    issue_id: str,
    payload: IssueTransitionRequest,
    session: SessionDep,
    actor: IssueManager,
) -> IssueOut:
    """Move an issue through its explicit lifecycle with recorded reasoning."""
    row = get_or_404(session, IssueTable, issue_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, payload.row_version)
    current = IssueStatus(row.status)
    try:
        ensure_issue_transition(current, payload.target_status)
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    starting = current is IssueStatus.OPEN and payload.target_status is IssueStatus.IN_PROGRESS
    if not starting and not (payload.rationale and payload.rationale.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Record the reason for this change.",
        )

    before = {
        "status": row.status,
        "resolution_summary": row.resolution_summary,
        "resolved_by": row.resolved_by,
        "resolved_at": row.resolved_at,
    }
    row.status = payload.target_status.value
    if payload.target_status is IssueStatus.RESOLVED:
        row.resolution_summary = payload.rationale
        row.resolved_by = actor.full_name
        row.resolved_at = datetime.now(UTC)
    elif payload.target_status in {IssueStatus.OPEN, IssueStatus.IN_PROGRESS}:
        row.resolution_summary = None
        row.resolved_by = None
        row.resolved_at = None
    stamp_update(row, actor.email)
    after = {
        "status": row.status,
        "resolution_summary": row.resolution_summary,
        "resolved_by": row.resolved_by,
        "resolved_at": row.resolved_at,
    }
    session.add(row)
    activity_service.record(
        session,
        action="transitioned",
        entity_type=_LABEL,
        entity_id=issue_id,
        project_id=row.project_id,
        summary=f"Moved issue {issue_id} from {current.value} to {row.status}",
        detail=payload.rationale,
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(
    issue_id: str, row_version: RowVersionDep, session: SessionDep, actor: IssueManager
) -> None:
    """Withdraw an issue while retaining its audit history."""
    row = get_or_404(session, IssueTable, issue_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="withdrew",
        entity_type=_LABEL,
        entity_id=issue_id,
        project_id=row.project_id,
        summary=f"Withdrew issue {issue_id}",
        actor=actor,
    )
    session.commit()
