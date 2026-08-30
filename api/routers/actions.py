"""Action records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

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
from api.models import ActionTable, ProjectMemberTable, UserTable
from api.schemas import ActionCreate, ActionOut, ActionTransitionRequest, ActionUpdate
from api.security.dependencies import ActionManager, CurrentUser, WorkUpdater
from api.security.permissions import Permission, has_permission
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import action_row_out
from api.services import activity_service, notification_service
from api.services.record_references import next_reference
from src.workflow_rules import ActionStatus, WorkflowTransitionError, ensure_action_transition

router = APIRouter(prefix="/actions", tags=["actions"])

_LABEL = "Action"


def _present(row: ActionTable) -> ActionOut:
    return action_row_out(row)


def _assignment_values(
    session: SessionDep, project_id: str, payload: ActionCreate | ActionUpdate
) -> dict[str, object]:
    """Resolve an assignee account; the stored owner name always follows the account."""
    if "owner_user_id" not in payload.model_fields_set:
        return {}
    if payload.owner_user_id is None:
        return {"owner_user_id": None}
    user = session.get(UserTable, payload.owner_user_id)
    membership = session.exec(
        select(ProjectMemberTable).where(
            ProjectMemberTable.project_id == project_id,
            ProjectMemberTable.user_id == payload.owner_user_id,
        )
    ).first()
    if (
        user is None
        or not user.is_active
        or membership is None
        or not has_permission(user.role, Permission.WORK_UPDATE)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Select an active project member whose role can update assigned work.",
        )
    return {"owner_user_id": user.id, "owner": user.full_name}


def _notify_assignee(
    session: SessionDep, row: ActionTable, previous_owner_id: int | None, actor: CurrentUser
) -> None:
    if row.owner_user_id is not None and row.owner_user_id != previous_owner_id:
        notification_service.notify(
            session,
            [row.owner_user_id],
            kind=notification_service.ACTION_ASSIGNED,
            title=f"You were assigned an action: {row.action_description}",
            detail=f"{row.action_id}" + (f", due {row.due_date:%d %b %Y}" if row.due_date else ""),
            project_id=row.project_id,
            entity_type=_LABEL,
            entity_id=row.action_id,
            actor=actor,
        )


@router.get("", response_model=list[ActionOut])
def list_actions(
    session: SessionDep, actor: CurrentUser, project_id: str | None = Query(default=None)
) -> list[ActionOut]:
    """List actions, optionally filtered to one project."""
    rows = list_rows(session, ActionTable, project_id)
    rows = scope_rows(session, actor, rows)
    return [_present(row) for row in sorted(rows, key=lambda a: a.action_id)]


@router.get("/{action_id}", response_model=ActionOut)
def get_action(action_id: str, session: SessionDep, actor: CurrentUser) -> ActionOut:
    """Return one action."""
    row = get_or_404(session, ActionTable, action_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
def create_action(payload: ActionCreate, session: SessionDep, actor: ActionManager) -> ActionOut:
    """Create an action, allocating the next project reference when none is supplied."""
    require_project_access(session, actor, payload.project_id, write=True)
    action_id = payload.action_id or next_reference(session, payload.project_id, "A")
    ensure_absent(session, ActionTable, action_id, _LABEL)
    values = payload.model_dump(exclude={"status", "owner_user_id"})
    values["action_id"] = action_id
    values.update(_assignment_values(session, payload.project_id, payload))
    row = ActionTable(**values, status=ActionStatus.OPEN.value)
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=action_id,
        project_id=payload.project_id,
        summary=f"Created action {action_id}",
        actor=actor,
    )
    _notify_assignee(session, row, None, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{action_id}", response_model=ActionOut)
def update_action(
    action_id: str, payload: ActionUpdate, session: SessionDep, actor: ActionManager
) -> ActionOut:
    """Update the supplied fields of an action."""
    row = get_or_404(session, ActionTable, action_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    previous_owner_id = row.owner_user_id
    assignment = _assignment_values(session, row.project_id, payload)
    if not assignment and "owner" in payload.model_fields_set and row.owner_user_id is not None:
        # A retyped owner name no longer describes the linked account, so the link is dropped.
        account = session.get(UserTable, row.owner_user_id)
        if account is None or account.full_name != payload.owner:
            assignment = {"owner_user_id": None}
    before = apply_update(row, payload, actor.email, exclude=frozenset({"owner_user_id"}))
    after = payload.model_dump(exclude_unset=True, exclude={"owner_user_id"})
    for field_name, value in assignment.items():
        before.setdefault(field_name, getattr(row, field_name))
        setattr(row, field_name, value)
        after[field_name] = value
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=action_id,
        project_id=row.project_id,
        summary=f"Updated action {action_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    _notify_assignee(session, row, previous_owner_id, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


@router.post("/{action_id}/transition", response_model=ActionOut)
def transition_action(
    action_id: str,
    payload: ActionTransitionRequest,
    session: SessionDep,
    actor: WorkUpdater,
) -> ActionOut:
    """Move an action through its controlled lifecycle with recorded reasoning.

    Action managers may move any action; an assignee may move only an action assigned to them.
    """
    row = get_or_404(session, ActionTable, action_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    if not has_permission(actor.role, Permission.ACTION_MANAGE) and (
        actor.id is None or row.owner_user_id != actor.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may update only actions assigned to your account.",
        )
    ensure_row_version(row, payload.row_version)
    current = ActionStatus(row.status)
    try:
        ensure_action_transition(current, payload.target_status)
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    before = {"status": row.status}
    row.status = payload.target_status.value
    stamp_update(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="transitioned",
        entity_type=_LABEL,
        entity_id=action_id,
        project_id=row.project_id,
        summary=f"Moved action {action_id} from {current.value} to {row.status}",
        detail=payload.rationale,
        changes=activity_service.field_changes(before, {"status": row.status}),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_action(
    action_id: str, row_version: RowVersionDep, session: SessionDep, actor: ActionManager
) -> None:
    """Withdraw an action. The record is retained for audit."""
    row = get_or_404(session, ActionTable, action_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=action_id,
        project_id=row.project_id,
        summary=f"Deleted action {action_id}",
        actor=actor,
    )
    session.commit()
