"""User registration, sign-in and account administration."""

from __future__ import annotations

import hashlib
import secrets
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Final

from fastapi import HTTPException, status
from sqlmodel import Session, select

from api import settings
from api.models import InvitationTable, UserTable
from api.schemas_auth import InvitationOut, UserOut
from api.security import sessions
from api.security.permissions import DEFAULT_ROLE, Role, permissions_for, role_label
from api.security.tokens import (
    TOKEN_LIFETIME_MINUTES,
    AuthError,
    generate_temporary_password,
    hash_password,
    needs_rehash,
    verify_absent_account,
    verify_password,
)

INVITATION_LIFETIME_DAYS: Final[int] = 7

# Deliberately identical for an unknown email and a wrong password, so the endpoint cannot be used
# to discover which addresses are registered.
_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="That email address and password combination was not recognised.",
    headers={"WWW-Authenticate": "Bearer"},
)

# Says nothing about whether the address is registered.
_REGISTRATION_REFUSED = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="An account could not be created with these details. If you already have one, sign in.",
)


def normalise_email(email: str) -> str:
    """Store and compare email addresses in a single canonical form."""
    return email.strip().lower()


def user_out(user: UserTable) -> UserOut:
    """Present a user, resolving their permissions for the interface to adapt to."""
    return UserOut(
        id=user.id or 0,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        role_label=role_label(user.role),
        job_title=user.job_title,
        is_active=user.is_active,
        permissions=sorted(permission.value for permission in permissions_for(user.role)),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        password_change_required=user.password_change_required,
    )


def find_by_email(session: Session, email: str) -> UserTable | None:
    """Return the user with this email address, if any."""
    statement = select(UserTable).where(UserTable.email == normalise_email(email))
    return session.exec(statement).first()


def ensure_self_registration_allowed(email: str) -> None:
    """Apply the workspace's sign-up policy before any account lookup happens."""
    if not settings.self_registration_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is turned off. Ask a workspace administrator for an account.",
        )
    domains = settings.registration_email_domains()
    domain = normalise_email(email).rpartition("@")[2]
    if domains and domain not in domains:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is limited to approved email domains.",
        )


def register(
    session: Session,
    email: str,
    full_name: str,
    password: str,
    job_title: str | None = None,
    role: Role = DEFAULT_ROLE,
) -> UserTable:
    """Create an account.

    ``role`` is only ever supplied by seeding or by an administrator, never by a request body.
    """
    address = normalise_email(email)
    if find_by_email(session, address) is not None:
        raise _REGISTRATION_REFUSED

    try:
        password_hash = hash_password(password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    user = UserTable(
        email=address,
        full_name=full_name.strip(),
        password_hash=password_hash,
        role=role,
        job_title=job_title,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, email: str, password: str) -> UserTable:
    """Verify credentials and return the user.

    Raises the same error for an unknown address and a wrong password.
    """
    user = find_by_email(session, email)
    if user is None:
        verify_absent_account(password)
        raise _INVALID_CREDENTIALS
    if not verify_password(password, user.password_hash):
        raise _INVALID_CREDENTIALS
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled."
        )

    if needs_rehash(user.password_hash):
        # A legacy password below today's minimum keeps its old hash until it is changed.
        with suppress(AuthError):
            user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def change_password(
    session: Session, user: UserTable, current_password: str, new_password: str
) -> None:
    """Replace a user's password after confirming the current one."""
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Your current password is not correct."
        )
    if verify_password(new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose a password different from your current one.",
        )
    try:
        user.password_hash = hash_password(new_password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    user.updated_at = datetime.now(UTC)
    user.password_change_required = False
    session.add(user)
    sessions.revoke_all(session, user.id or 0)
    session.commit()


def reset_password(session: Session, user: UserTable) -> str:
    """Replace a user's password with a temporary one and return it once.

    The new hash also invalidates every token issued for the old password, and the temporary
    password admits nothing but choosing a new one.
    """
    temporary = generate_temporary_password()
    user.password_hash = hash_password(temporary)
    user.updated_at = datetime.now(UTC)
    user.password_change_required = True
    session.add(user)
    sessions.revoke_all(session, user.id or 0)
    return temporary


def _invitation_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def invitation_status(row: InvitationTable) -> str:
    if row.accepted_at is not None:
        return "Accepted"
    if row.revoked_at is not None:
        return "Revoked"
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    return "Expired" if expires <= datetime.now(UTC) else "Pending"


def invitation_out(row: InvitationTable) -> InvitationOut:
    role = Role(row.role)
    return InvitationOut(
        id=row.id or 0,
        email=row.email,
        role=role,
        role_label=role_label(role),
        created_by=row.created_by,
        created_at=row.created_at,
        expires_at=row.expires_at,
        status=invitation_status(row),  # type: ignore[arg-type]
    )


def create_invitation(
    session: Session, admin: UserTable, email: str, role: Role
) -> tuple[InvitationTable, str]:
    """Issue a one-time code bound to one address. Earlier pending codes for it stop working."""
    address = normalise_email(email)
    if find_by_email(session, address) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That address already has an account."
        )
    now = datetime.now(UTC)
    for pending in session.exec(
        select(InvitationTable).where(InvitationTable.email == address)
    ).all():
        if invitation_status(pending) == "Pending":
            pending.revoked_at = now
            session.add(pending)
    code = secrets.token_urlsafe(24)
    row = InvitationTable(
        code_hash=_invitation_hash(code),
        email=address,
        role=role.value,
        created_by=admin.full_name,
        created_at=now,
        expires_at=now + timedelta(days=INVITATION_LIFETIME_DAYS),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, code


def list_invitations(session: Session) -> list[InvitationOut]:
    rows = session.exec(select(InvitationTable)).all()
    return [invitation_out(row) for row in sorted(rows, key=lambda row: row.id or 0, reverse=True)]


def revoke_invitation(session: Session, invitation_id: int) -> InvitationOut:
    row = session.get(InvitationTable, invitation_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
    if invitation_status(row) == "Pending":
        row.revoked_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        session.refresh(row)
    return invitation_out(row)


def accept_invitation(session: Session, code: str, email: str) -> tuple[InvitationTable, Role]:
    """Validate a code for this address. The caller commits it together with the new account."""
    row = session.exec(
        select(InvitationTable).where(InvitationTable.code_hash == _invitation_hash(code))
    ).first()
    if row is None or invitation_status(row) != "Pending" or row.email != normalise_email(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is not valid for that address. Ask for a new one.",
        )
    row.accepted_at = datetime.now(UTC)
    session.add(row)
    return row, Role(row.role)


def token_lifetime_seconds() -> int:
    """Access-token lifetime, for the client to schedule a re-authentication."""
    return TOKEN_LIFETIME_MINUTES * 60
