"""Owner accounts for risks, issues and assumptions.

The recorded owner name always follows the linked account, so the register and the owner's own
work list can never disagree about who is responsible.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session, SQLModel

from api.models import UserTable
from api.security.project_scope import has_project_access
from api.services import notification_service


def linked_owner(session: Session, project_id: str, user_id: int) -> UserTable:
    """Return an active account that can see the project, or refuse the choice."""
    user = session.get(UserTable, user_id)
    if user is None or not user.is_active or not has_project_access(session, user, project_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Select an active person who can access this project.",
        )
    return user


def apply_owner_link(
    session: Session,
    row: SQLModel,
    project_id: str,
    *,
    id_field: str,
    name_field: str,
    user_id: int | None,
    id_supplied: bool,
    name_supplied: bool,
) -> dict[str, object]:
    """Set or clear the owner account on ``row``. Returns the values before the change.

    A retyped name that no longer matches the linked account drops the link rather than leaving
    the record credited to someone else.
    """
    before: dict[str, object] = {}
    if id_supplied:
        before[id_field] = getattr(row, id_field)
        if user_id is None:
            setattr(row, id_field, None)
        else:
            owner = linked_owner(session, project_id, user_id)
            before.setdefault(name_field, getattr(row, name_field))
            setattr(row, id_field, owner.id)
            setattr(row, name_field, owner.full_name)
    elif name_supplied and getattr(row, id_field) is not None:
        account = session.get(UserTable, getattr(row, id_field))
        if account is None or account.full_name != getattr(row, name_field):
            before[id_field] = getattr(row, id_field)
            setattr(row, id_field, None)
    return before


def notify_new_owner(
    session: Session,
    *,
    owner_id: int | None,
    previous_owner_id: int | None,
    kind: str,
    title: str,
    detail: str | None,
    project_id: str,
    entity_type: str,
    entity_id: str,
    actor: UserTable,
) -> None:
    """Tell a newly linked owner, never the person who made the change."""
    if owner_id is None or owner_id == previous_owner_id:
        return
    notification_service.notify(
        session,
        [owner_id],
        kind=kind,
        title=title,
        detail=detail,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
    )
