"""Audit trail of writes performed through the API."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.dependencies import SessionDep
from api.schemas import ActivityEventOut
from api.security.dependencies import CurrentUser
from api.security.permissions import Permission, has_permission
from api.security.project_scope import project_ids_for, require_project_access
from api.services import activity_service

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=list[ActivityEventOut])
def list_activity(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[ActivityEventOut]:
    """Return recent activity, newest first."""
    if project_id is not None:
        require_project_access(session, actor, project_id)
    return activity_service.list_events(
        session,
        project_id=project_id,
        limit=limit,
        project_ids=project_ids_for(session, actor),
        include_workspace_events=has_permission(actor.role, Permission.USER_MANAGE),
    )
