"""Registration, sign-in and the current user's own account."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status

from api import settings
from api.dependencies import SessionDep
from api.models import UserSessionTable, UserTable
from api.schemas_auth import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    SessionOut,
    SessionState,
    TokenResponse,
    UserOut,
)
from api.security import sessions
from api.security.dependencies import CurrentUser
from api.security.permissions import DEFAULT_ROLE
from api.security.rate_limit import client_key, enforce, limits_for, too_many_requests
from api.security.tokens import (
    TokenClaims,
    create_access_token,
    session_can_be_refreshed,
)
from api.services import user_service

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)

_SIGN_IN_LIMITED = "Too many sign-in attempts. Wait a few minutes before trying again."
_REGISTRATION_LIMITED = "Too many accounts were requested from this network. Try again later."


def _account_reference(email: str) -> str:
    """A stable pseudonym for an address, so logs can correlate attempts without storing it."""
    return hashlib.sha256(user_service.normalise_email(email).encode()).hexdigest()[:12]


def _issue(
    request: Request,
    response: Response,
    user: UserTable,
    record: UserSessionTable,
    authenticated_at: datetime | None = None,
) -> TokenResponse:
    """Issue a token for an authenticated session; the web client receives it as a cookie."""
    token = create_access_token(
        user.id or 0,
        user.email,
        user.role,
        password_hash=user.password_hash,
        authenticated_at=authenticated_at,
        session_record_id=record.id,
    )
    web = sessions.wants_cookie(request)
    if web:
        sessions.set_cookie(response, request, token)
    return TokenResponse(
        access_token=None if web else token,
        expires_in_seconds=user_service.token_lifetime_seconds(),
        user=user_service.user_out(user),
        csrf_token=sessions.csrf_token(record.id),
    )


def _current_record(request: Request) -> UserSessionTable:
    return request.state.session_record


def _current_claims(request: Request) -> TokenClaims:
    return request.state.token_claims


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, request: Request, response: Response, session: SessionDep
) -> TokenResponse:
    """Create an account and sign in.

    Self-registered accounts always receive the lowest-privilege role. An administrator's
    invitation, bound to one address, carries the role the administrator chose.
    """
    if payload.invitation_code is None:
        if settings.registration_requires_invitation():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sign-up needs an invitation. Ask a workspace administrator for one.",
            )
        user_service.ensure_self_registration_allowed(payload.email)
    limits = limits_for(request)
    if limits.enabled:
        try:
            enforce(
                limits.registration_client,
                [client_key(request)],
                _REGISTRATION_LIMITED,
                record=True,
                session=session,
            )
        except HTTPException:
            logger.warning(
                "Registration paused for %s after repeated requests", client_key(request)
            )
            raise
    role = DEFAULT_ROLE
    if payload.invitation_code is not None:
        _, role = user_service.accept_invitation(session, payload.invitation_code, payload.email)
    user = user_service.register(
        session,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        job_title=payload.job_title,
        role=role,
    )
    return _issue(request, response, user, sessions.start(session, user, request))


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, session: SessionDep
) -> TokenResponse:
    """Exchange credentials for a session.

    Repeated failures for one account or from one network are refused before the password is
    checked, so guessing cannot continue at full speed.
    """
    limits = limits_for(request)
    account = f"account:{user_service.normalise_email(payload.email)}"
    client = client_key(request)
    if limits.enabled:
        waits = [
            wait
            for wait in (
                limits.sign_in_account.retry_after(account, session),
                limits.sign_in_client.retry_after(client, session),
            )
            if wait is not None
        ]
        if waits:
            logger.warning(
                "Sign-in paused after repeated failures: account %s, %s",
                _account_reference(payload.email),
                client,
            )
            raise too_many_requests(max(waits), _SIGN_IN_LIMITED)
    try:
        user = user_service.authenticate(session, payload.email, payload.password)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            logger.warning(
                "Sign-in refused: account %s, %s", _account_reference(payload.email), client
            )
            if limits.enabled:
                limits.sign_in_account.record(account, session)
                limits.sign_in_client.record(client, session)
        raise
    if limits.enabled:
        limits.sign_in_account.reset(account, session)
    return _issue(request, response, user, sessions.start(session, user, request))


@router.post("/refresh", response_model=TokenResponse)
def refresh(user: CurrentUser, request: Request, response: Response) -> TokenResponse:
    """Extend an active session without asking for the password again.

    The original sign-in time is carried forward, so a session still ends a fixed time after the
    password was last entered.
    """
    claims = _current_claims(request)
    if not session_can_be_refreshed(claims):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has reached its maximum length. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue(
        request, response, user, _current_record(request), authenticated_at=claims.authenticated_at
    )


@router.get("/session", response_model=SessionState)
def read_session(user: CurrentUser, request: Request) -> SessionState:
    """When the current token expires and the value writes must echo, for a reloaded page."""
    record = _current_record(request)
    return SessionState(
        csrf_token=sessions.csrf_token(record.id),
        expires_at=_current_claims(request).expires_at,
        session_expires_at=record.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser, request: Request, response: Response, session: SessionDep) -> None:
    """End this session everywhere it is used, and clear the browser cookie."""
    sessions.revoke(session, _current_record(request))
    session.commit()
    sessions.clear_cookie(response, request)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user: CurrentUser, request: Request, session: SessionDep) -> list[SessionOut]:
    """The signed-in account's live sessions, most recently used first."""
    current = _current_record(request).id
    return [
        SessionOut(
            id=record.id,
            created_at=record.created_at,
            last_seen_at=record.last_seen_at,
            expires_at=record.expires_at,
            user_agent=record.user_agent,
            current=record.id == current,
        )
        for record in sessions.list_active(session, user.id or 0)
    ]


@router.post("/sessions/{session_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: str, user: CurrentUser, request: Request, response: Response, session: SessionDep
) -> None:
    """End one of the account's own sessions."""
    record = session.get(UserSessionTable, session_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    sessions.revoke(session, record)
    session.commit()
    if record.id == _current_record(request).id:
        sessions.clear_cookie(response, request)


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(user: CurrentUser, request: Request, session: SessionDep) -> None:
    """Sign out every other browser and client, keeping this one."""
    sessions.revoke_all(session, user.id or 0, keep=_current_record(request).id)
    session.commit()


@router.get("/me", response_model=UserOut)
def read_current_user(user: CurrentUser) -> UserOut:
    """Return the signed-in user and the permissions their role grants."""
    return user_service.user_out(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: PasswordChangeRequest, user: CurrentUser, session: SessionDep) -> None:
    """Change the signed-in user's own password.

    Every token issued for the previous password stops working, including the one used here.
    """
    user_service.change_password(session, user, payload.current_password, payload.new_password)
