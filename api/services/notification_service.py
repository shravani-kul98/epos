"""In-app notifications: who should look at what, re-checked against access when read."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Final

from fastapi import HTTPException, status
from sqlmodel import Session, col, desc, select

from api.models import NotificationTable, ProjectMemberTable, ProjectTable, UserTable
from api.schemas import NotificationOut
from api.security.permissions import Permission, has_permission
from api.security.project_scope import has_project_access, project_ids_for

TASK_ASSIGNED: Final[str] = "task_assigned"
TASK_BLOCKED: Final[str] = "task_blocked"
TASK_COMPLETED: Final[str] = "task_completed"
REVIEW_REQUESTED: Final[str] = "review_requested"
REVIEW_ACCEPTED: Final[str] = "review_accepted"
REVIEW_RETURNED: Final[str] = "review_returned"
ACTION_ASSIGNED: Final[str] = "action_assigned"
RISK_ASSIGNED: Final[str] = "risk_assigned"
ISSUE_ASSIGNED: Final[str] = "issue_assigned"
ASSUMPTION_ASSIGNED: Final[str] = "assumption_assigned"
ASSIGNMENT_ACCEPTED: Final[str] = "assignment_accepted"
ASSIGNMENT_DECLINED: Final[str] = "assignment_declined"

_LIST_LIMIT: Final[int] = 100
_TITLE_LENGTH: Final[int] = 200
_DETAIL_LENGTH: Final[int] = 300


def notify(
    session: Session,
    recipients: Iterable[int | None],
    *,
    kind: str,
    title: str,
    detail: str | None = None,
    project_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: UserTable | None = None,
) -> int:
    """Queue one notification per active recipient, never for the person who acted."""
    wanted = {
        user_id
        for user_id in recipients
        if user_id is not None and (actor is None or user_id != actor.id)
    }
    if not wanted:
        return 0
    active = session.exec(
        select(UserTable.id).where(col(UserTable.id).in_(wanted), UserTable.is_active.is_(True))
    ).all()
    for user_id in active:
        session.add(
            NotificationTable(
                user_id=user_id,
                kind=kind,
                title=title[:_TITLE_LENGTH],
                detail=detail[:_DETAIL_LENGTH] if detail else None,
                project_id=project_id,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_name=actor.full_name if actor else None,
            )
        )
    return len(active)


def project_managers(session: Session, project_id: str) -> list[int]:
    """Active members of a project whose role manages its delivery work."""
    members = session.exec(
        select(UserTable)
        .join(ProjectMemberTable, col(ProjectMemberTable.user_id) == col(UserTable.id))
        .where(ProjectMemberTable.project_id == project_id, UserTable.is_active.is_(True))
    ).all()
    return [
        member.id
        for member in members
        if member.id is not None and has_permission(member.role, Permission.WORK_MANAGE)
    ]


def resolve(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
    kinds: Iterable[str],
    user_ids: Iterable[int | None] | None = None,
) -> int:
    """Mark notifications read once the thing they asked for has been handled.

    A review request stops being news when the review is recorded, and an assignment when the
    assignee answers it. The caller commits.
    """
    statement = select(NotificationTable).where(
        NotificationTable.entity_type == entity_type,
        NotificationTable.entity_id == entity_id,
        col(NotificationTable.kind).in_(list(kinds)),
        col(NotificationTable.read_at).is_(None),
    )
    if user_ids is not None:
        wanted = [user_id for user_id in user_ids if user_id is not None]
        if not wanted:
            return 0
        statement = statement.where(col(NotificationTable.user_id).in_(wanted))
    rows = session.exec(statement).all()
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
        session.add(row)
    return len(rows)


def _owned_rows(session: Session, user: UserTable, unread_only: bool) -> list[NotificationTable]:
    statement = select(NotificationTable).where(NotificationTable.user_id == user.id)
    if unread_only:
        statement = statement.where(col(NotificationTable.read_at).is_(None))
    statement = statement.order_by(desc(NotificationTable.created_at), desc(NotificationTable.id))
    rows = session.exec(statement).all()
    # Access is rechecked on every read, so leaving a project hides its notifications.
    projects = {row.project_id for row in rows if row.project_id is not None}
    if not projects:
        return list(rows)
    live = set(
        session.exec(
            select(ProjectTable.project_id).where(
                col(ProjectTable.project_id).in_(projects), ProjectTable.deleted_at.is_(None)
            )
        ).all()
    )
    allowed = project_ids_for(session, user)
    return [
        row
        for row in rows
        if row.project_id is None
        or (row.project_id in live and (allowed is None or row.project_id in allowed))
    ]


def list_for(session: Session, user: UserTable, unread_only: bool = False) -> list[NotificationOut]:
    """The signed-in user's notifications, newest first."""
    return [
        NotificationOut.model_validate(row, from_attributes=True)
        for row in _owned_rows(session, user, unread_only)[:_LIST_LIMIT]
    ]


def unread_count(session: Session, user: UserTable) -> int:
    return len(_owned_rows(session, user, unread_only=True))


def mark_read(session: Session, user: UserTable, notification_id: int) -> NotificationOut:
    row = session.get(NotificationTable, notification_id)
    if (
        row is None
        or row.user_id != user.id
        or (row.project_id is not None and not has_project_access(session, user, row.project_id))
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        session.refresh(row)
    return NotificationOut.model_validate(row, from_attributes=True)


def mark_all_read(session: Session, user: UserTable) -> int:
    rows = _owned_rows(session, user, unread_only=True)
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
        session.add(row)
    session.commit()
    return len(rows)
