"""Password hashing and JWT issuing.

Secrets are read from the environment only. Nothing in this module logs or returns a password, a
hash or the signing key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from api import settings
from api.security.permissions import Role

SECRET_KEY_ENV_VAR: Final[str] = "EPOS_SECRET_KEY"
# Deployment platforms commonly use this name for the signing secret.
JWT_SECRET_ENV_VAR: Final[str] = "JWT_SECRET"
TOKEN_ALGORITHM: Final[str] = "HS256"
TOKEN_LIFETIME_MINUTES: Final[int] = 60
# A refreshed session still ends this long after the password was last entered.
SESSION_MAX_HOURS: Final[int] = 12
MIN_PASSWORD_LENGTH: Final[int] = 12
MIN_PASSWORD_VARIETY: Final[int] = 5
MIN_PRODUCTION_SECRET_LENGTH: Final[int] = 32

_hasher = PasswordHasher()

# Generated once per process when no key is configured, so local development works without setup
# while every restart invalidates old tokens. Never used to protect anything shared.
_ephemeral_key: str | None = None
# Verified against when an email is unknown, so both failure paths cost the same.
_absent_account_hash: str | None = None


class AuthError(Exception):
    """Raised when a credential or token cannot be accepted."""


def signing_key() -> str:
    """Return the JWT signing key.

    Production must supply one: a generated key would differ between serverless instances and
    silently invalidate sessions, so its absence fails closed instead. Local development still
    falls back to a random per-process key, which keeps setup free of a predictable default.
    """
    configured = os.getenv(SECRET_KEY_ENV_VAR) or os.getenv(JWT_SECRET_ENV_VAR)
    if configured:
        if settings.is_production() and len(configured) < MIN_PRODUCTION_SECRET_LENGTH:
            raise RuntimeError(
                f"{JWT_SECRET_ENV_VAR} must be at least "
                f"{MIN_PRODUCTION_SECRET_LENGTH} characters in production."
            )
        return configured

    if settings.is_production():
        raise RuntimeError(
            f"{JWT_SECRET_ENV_VAR} must be configured when "
            f"{settings.ENVIRONMENT_ENV_VAR} is production; no signing key is generated."
        )

    global _ephemeral_key
    if _ephemeral_key is None:
        _ephemeral_key = secrets.token_urlsafe(48)
    return _ephemeral_key


def password_policy_problem(password: str) -> str | None:
    """Explain why a new password is unacceptable, or return ``None`` when it is acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(set(password)) < MIN_PASSWORD_VARIETY:
        return "Choose a password with more variety of characters."
    return None


def generate_temporary_password() -> str:
    """A random password that satisfies the policy, for an administrator-initiated reset."""
    while True:
        candidate = secrets.token_urlsafe(18)
        if password_policy_problem(candidate) is None:
            return candidate


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against its stored hash, without revealing why it failed."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_absent_account(password: str) -> None:
    """Spend the same Argon2 work as a real check when the account does not exist."""
    global _absent_account_hash
    if _absent_account_hash is None:
        _absent_account_hash = _hasher.hash(secrets.token_urlsafe(32))
    verify_password(password, _absent_account_hash)


def session_fingerprint(password_hash: str) -> str:
    """Bind a token to the password it was issued for, so a password change revokes it.

    Keyed with the signing secret, so the value in a readable token reveals nothing about the hash.
    """
    digest = hmac.new(signing_key().encode(), password_hash.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode()


def needs_rehash(password_hash: str) -> bool:
    """True when a stored hash uses outdated Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@dataclass(frozen=True)
class TokenClaims:
    """The verified contents of an access token."""

    user_id: int
    email: str
    role: Role
    expires_at: datetime
    session_id: str | None = None
    authenticated_at: datetime | None = None
    session_record_id: str | None = None


def create_access_token(
    user_id: int,
    email: str,
    role: Role,
    *,
    password_hash: str | None = None,
    authenticated_at: datetime | None = None,
    session_record_id: str | None = None,
) -> str:
    """Issue a signed, expiring access token.

    The role is carried for convenience only. Permissions are always resolved server-side from the
    stored user record, so a role change takes effect immediately. ``authenticated_at`` is when the
    password was last entered; it survives refreshes so a session cannot be extended forever.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=TOKEN_LIFETIME_MINUTES)).timestamp()),
        "auth_time": int((authenticated_at or now).timestamp()),
    }
    if password_hash is not None:
        payload["sid"] = session_fingerprint(password_hash)
    if session_record_id is not None:
        payload["ses"] = session_record_id
    return jwt.encode(payload, signing_key(), algorithm=TOKEN_ALGORITHM)


def decode_access_token(token: str) -> TokenClaims:
    """Verify a token's signature and expiry, returning its claims.

    Raises:
        AuthError: The token is malformed, expired, or signed with the wrong key.
    """
    try:
        payload = jwt.decode(
            token,
            signing_key(),
            algorithms=[TOKEN_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("The session token is not valid.") from exc

    try:
        auth_time = payload.get("auth_time")
        session_id = payload.get("sid")
        record_id = payload.get("ses")
        return TokenClaims(
            user_id=int(payload["sub"]),
            email=str(payload.get("email", "")),
            role=Role(payload["role"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
            session_id=session_id if isinstance(session_id, str) else None,
            authenticated_at=(
                datetime.fromtimestamp(auth_time, UTC) if isinstance(auth_time, int) else None
            ),
            session_record_id=record_id if isinstance(record_id, str) else None,
        )
    except (KeyError, ValueError, OverflowError, OSError) as exc:
        raise AuthError("The session token is not valid.") from exc


def token_matches_password(claims: TokenClaims, password_hash: str) -> bool:
    """True when the token was issued for the account's current password."""
    return claims.session_id is not None and hmac.compare_digest(
        claims.session_id, session_fingerprint(password_hash)
    )


def session_can_be_refreshed(claims: TokenClaims) -> bool:
    """True while the original sign-in is recent enough to extend without a password."""
    if claims.authenticated_at is None:
        return False
    return datetime.now(UTC) - claims.authenticated_at < timedelta(hours=SESSION_MAX_HOURS)
