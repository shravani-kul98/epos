"""The signed-in user's notification inbox."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.dependencies import SessionDep
from api.schemas import NotificationOut, NotificationSummary
from api.security.dependencies import CurrentUser
from api.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    session: SessionDep, actor: CurrentUser, unread_only: bool = Query(default=False)
) -> list[NotificationOut]:
    """Newest first; items from projects the reader can no longer access are hidden."""
    return notification_service.list_for(session, actor, unread_only)


@router.get("/summary", response_model=NotificationSummary)
def notification_summary(session: SessionDep, actor: CurrentUser) -> NotificationSummary:
    return NotificationSummary(unread=notification_service.unread_count(session, actor))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def read_notification(
    notification_id: int, session: SessionDep, actor: CurrentUser
) -> NotificationOut:
    return notification_service.mark_read(session, actor, notification_id)


@router.post("/read-all", response_model=NotificationSummary)
def read_all_notifications(session: SessionDep, actor: CurrentUser) -> NotificationSummary:
    notification_service.mark_all_read(session, actor)
    return NotificationSummary(unread=0)
