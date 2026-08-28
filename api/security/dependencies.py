"""Request-time authentication and permission checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from api.database import get_session
from api.models import UserTable
from api.security import sessions
from api.security.permissions import Permission, has_permission
from api.security.rate_limit import enforce, limits_for
from api.security.tokens import AuthError, decode_access_token, token_matches_password

# auto_error is disabled so a missing header produces our own 401 with a usable message.
_bearer = HTTPBearer(auto_error=False, description="Bearer access token")
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
_cookie = APIKeyCookie(
    name=sessions.SESSION_COOKIE, auto_error=False, description="Browser session cookie"
)
CookieCredentials = Annotated[str | None, Depends(_cookie)]

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sign in to continue.",
    headers={"WWW-Authenticate": "Bearer"},
)

# What a temporary password admits: reading the account and session, and replacing the password.
_PASSWORD_CHANGE_PATHS = frozenset(
    {"/auth/me", "/auth/session", "/auth/refresh", "/auth/logout", "/auth/change-password"}
)
PASSWORD_CHANGE_HEADER = "X-EPOS-Password"


def _password_change_allows(request: Request) -> bool:
    # The matched route template rather than the raw URL, so a crafted path cannot widen this.
    template = getattr(request.scope.get("route"), "path", "")
    return any(template.endswith(allowed) for allowed in _PASSWORD_CHANGE_PATHS)


def get_current_user(
    request: Request,
    credentials: BearerCredentials,
    cookie: CookieCredentials,
    session: Annotated[Session, Depends(get_session)],
) -> UserTable:
    """Resolve the signed-in user, or reject the request.

    The role is read from the stored record rather than the token, so changing or disabling an
    account takes effect immediately instead of at token expiry. A token must name a live session
    issued for the account's current password, so ending a session or changing the password
    stops it at once. A browser session sent as a cookie must also echo its CSRF token on writes.
    """
    bearer = credentials.credentials if credentials and credentials.credentials else None
    token = bearer or cookie
    if not token:
        raise _UNAUTHENTICATED

    try:
        claims = decode_access_token(token)
    except AuthError as exc:
        raise _UNAUTHENTICATED from exc

    user = session.get(UserTable, claims.user_id)
    if user is None or not token_matches_password(claims, user.password_hash):
        raise _UNAUTHENTICATED
    record = sessions.active(session, claims.session_record_id, user.id or 0)
    if record is None:
        raise _UNAUTHENTICATED
    if (
        bearer is None
        and request.method not in sessions.SAFE_METHODS
        and not sessions.csrf_matches(request, record.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This request could not be verified. Refresh the page and try again.",
            headers={sessions.CSRF_RETRY_HEADER: "refresh"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled."
        )
    if user.password_change_required and not _password_change_allows(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Choose a new password to replace your temporary one before continuing.",
            headers={PASSWORD_CHANGE_HEADER: "change-required"},
        )
    request.state.session_record = record
    request.state.token_claims = claims
    return user


CurrentUser = Annotated[UserTable, Depends(get_current_user)]


def require(permission: Permission) -> Callable[[UserTable], UserTable]:
    """Build a dependency that admits only users holding ``permission``."""

    def dependency(user: CurrentUser) -> UserTable:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role does not allow this action.",
            )
        return user

    return dependency


# One alias per guarded capability, so route signatures read as the permission they need.
PortfolioReader = Annotated[UserTable, Depends(require(Permission.PORTFOLIO_READ))]
ProjectCreator = Annotated[UserTable, Depends(require(Permission.PROJECT_CREATE))]
ProjectEditor = Annotated[UserTable, Depends(require(Permission.PROJECT_UPDATE))]
ProjectRemover = Annotated[UserTable, Depends(require(Permission.PROJECT_DELETE))]
ProjectMemberManager = Annotated[UserTable, Depends(require(Permission.PROJECT_MEMBERS_MANAGE))]
WorkUpdater = Annotated[UserTable, Depends(require(Permission.WORK_UPDATE))]
WorkManager = Annotated[UserTable, Depends(require(Permission.WORK_MANAGE))]
ActionManager = Annotated[UserTable, Depends(require(Permission.ACTION_MANAGE))]
RiskManager = Annotated[UserTable, Depends(require(Permission.RISK_MANAGE))]
IssueManager = Annotated[UserTable, Depends(require(Permission.ISSUE_MANAGE))]
AssumptionManager = Annotated[UserTable, Depends(require(Permission.ASSUMPTION_MANAGE))]
RequirementManager = Annotated[UserTable, Depends(require(Permission.REQUIREMENT_MANAGE))]
ChangeAuthor = Annotated[UserTable, Depends(require(Permission.CHANGE_CREATE))]
ChangeDecider = Annotated[UserTable, Depends(require(Permission.CHANGE_DECIDE))]
ScenarioRunner = Annotated[UserTable, Depends(require(Permission.SCENARIO_RUN))]
ReportReader = Annotated[UserTable, Depends(require(Permission.REPORT_READ))]
CopilotUser = Annotated[UserTable, Depends(require(Permission.COPILOT_ASK))]
UserAdministrator = Annotated[UserTable, Depends(require(Permission.USER_MANAGE))]


def enforce_assistant_quota(
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Bound how often one account can send work to the language model."""
    limits = limits_for(request)
    if limits.enabled:
        enforce(
            limits.assistant_user,
            [f"user:{user.id}"],
            "You have asked a lot of questions in a short time. Wait a few minutes and try again.",
            record=True,
            session=session,
        )


AssistantQuota = Depends(enforce_assistant_quota)
