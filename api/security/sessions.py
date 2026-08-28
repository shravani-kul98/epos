"""Server-side sessions: every sign-in is a record that can be listed and ended on its own.

A token names its session. Revoking the record ends that browser or client immediately, and a
browser session travels in an HttpOnly cookie so page scripts never hold the credential.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Final

from fastapi import Request, Response
from sqlmodel import Session, col, select

from api import settings
from api.models import UserSessionTable, UserTable
from api.security.tokens import SESSION_MAX_HOURS, TOKEN_LIFETIME_MINUTES, signing_key

SESSION_COOKIE: Final[str] = "epos_session"
SESSION_COOKIE_PATH: Final[str] = "/api"
CSRF_HEADER: Final[str] = "X-CSRF-Token"
# Tells the interface the refusal was a stale CSRF value it can re-read, not a role refusal.
CSRF_RETRY_HEADER: Final[str] = "X-EPOS-CSRF"
# Sent by the web interface to receive its session as a cookie instead of a readable token.
WEB_CLIENT_HEADER: Final[str] = "X-EPOS-Client"
WEB_CLIENT: Final[str] = "web"
SAFE_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD", "OPTIONS"})
_LAST_SEEN_RESOLUTION: Final[timedelta] = timedelta(minutes=5)
_USER_AGENT_LENGTH: Final[int] = 200


def _aware(value: datetime) -> datetime:
    """SQLite returns naive timestamps; every stored time is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def start(session: Session, user: UserTable, request: Request) -> UserSessionTable:
    """Record a new sign-in. The session ends at most SESSION_MAX_HOURS later."""
    now = datetime.now(UTC)
    agent = (request.headers.get("user-agent") or "").strip()[:_USER_AGENT_LENGTH] or None
    record = UserSessionTable(
        id=secrets.token_urlsafe(24),
        user_id=user.id or 0,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=SESSION_MAX_HOURS),
        user_agent=agent,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def active(session: Session, session_id: str | None, user_id: int) -> UserSessionTable | None:
    """The live session record behind a token, or None when it was ended or has expired."""
    if not session_id:
        return None
    record = session.get(UserSessionTable, session_id)
    now = datetime.now(UTC)
    if (
        record is None
        or record.user_id != user_id
        or record.revoked_at is not None
        or _aware(record.expires_at) <= now
    ):
        return None
    if now - _aware(record.last_seen_at) > _LAST_SEEN_RESOLUTION:
        record.last_seen_at = now
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def list_active(session: Session, user_id: int) -> list[UserSessionTable]:
    now = datetime.now(UTC)
    rows = session.exec(
        select(UserSessionTable).where(
            UserSessionTable.user_id == user_id, col(UserSessionTable.revoked_at).is_(None)
        )
    ).all()
    live = [row for row in rows if _aware(row.expires_at) > now]
    return sorted(live, key=lambda row: _aware(row.last_seen_at), reverse=True)


def revoke(session: Session, record: UserSessionTable) -> None:
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        session.add(record)


def revoke_all(session: Session, user_id: int, keep: str | None = None) -> int:
    """End every live session for a user, optionally keeping the one making the request."""
    ended = 0
    for record in list_active(session, user_id):
        if record.id != keep:
            revoke(session, record)
            ended += 1
    return ended


def csrf_token(session_id: str) -> str:
    """A per-session value the interface echoes on writes; a cross-site page cannot read it."""
    digest = hmac.new(
        signing_key().encode(), f"csrf:{session_id}".encode(), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest[:24]).decode()


def csrf_matches(request: Request, session_id: str) -> bool:
    supplied = request.headers.get(CSRF_HEADER, "")
    return bool(supplied) and hmac.compare_digest(supplied, csrf_token(session_id))


def wants_cookie(request: Request) -> bool:
    return request.headers.get(WEB_CLIENT_HEADER, "").lower() == WEB_CLIENT


def set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=TOKEN_LIFETIME_MINUTES * 60,
        httponly=True,
        secure=settings.is_production() or request.url.scheme == "https",
        samesite="lax",
        path=SESSION_COOKIE_PATH,
    )


def clear_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=settings.is_production() or request.url.scheme == "https",
        samesite="lax",
        path=SESSION_COOKIE_PATH,
    )
