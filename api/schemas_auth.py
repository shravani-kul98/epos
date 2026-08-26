"""Authentication and user-management request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import EmailStr, Field, field_validator, model_validator

from api.schemas import ApiModel
from api.security.permissions import Role
from api.security.tokens import MIN_PASSWORD_LENGTH, password_policy_problem


def _acceptable_password(value: str) -> str:
    problem = password_policy_problem(value)
    if problem is not None:
        raise ValueError(problem)
    return value


class RegisterRequest(ApiModel):
    """Registration. The role is never accepted from the client; an invitation carries it."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    job_title: str | None = Field(default=None, max_length=120)
    invitation_code: str | None = Field(default=None, min_length=16, max_length=128)

    @field_validator("password")
    @classmethod
    def _reject_trivial_password(cls, value: str) -> str:
        """Refuse passwords with no variety, which pass a length check but protect nothing."""
        return _acceptable_password(value)


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(ApiModel):
    """A user as shown in the product. Never carries the password hash."""

    id: int
    email: str
    full_name: str
    role: Role
    role_label: str
    job_title: str | None
    is_active: bool
    permissions: list[str]
    created_at: datetime
    last_login_at: datetime | None
    password_change_required: bool = False


class TokenResponse(ApiModel):
    """A signed-in session. Web clients receive it as an HttpOnly cookie, so no token here."""

    access_token: str | None
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserOut
    csrf_token: str | None = None


class SessionState(ApiModel):
    """What the interface needs after a reload: when to renew, and the value writes must echo."""

    csrf_token: str
    expires_at: datetime
    session_expires_at: datetime


class SessionOut(ApiModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    current: bool


class InvitationCreate(ApiModel):
    email: EmailStr
    role: Role


class InvitationOut(ApiModel):
    id: int
    email: str
    role: Role
    role_label: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    status: Literal["Pending", "Accepted", "Revoked", "Expired"]


class InvitationIssued(ApiModel):
    """A new invitation. The code is shown once and only its hash is stored."""

    invitation: InvitationOut
    code: str


class RoleUpdateRequest(ApiModel):
    """Administrator-only role change."""

    role: Role


class ActiveUpdateRequest(ApiModel):
    """Administrator-only enable or disable."""

    is_active: bool


class ProjectMemberCreate(ApiModel):
    """Assign an active workspace account to a project."""

    user_email: EmailStr | None = None
    user_id: int | None = Field(default=None, gt=0, strict=True)
    project_role: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def select_one_account(self) -> Self:
        """Require one unambiguous account selector."""
        if (self.user_email is None) == (self.user_id is None):
            raise ValueError("Select an account by user ID or email, not both.")
        return self


class ProjectUserOption(ApiModel):
    """Minimal account details for an authorized project-member picker."""

    user_id: int
    email: str
    full_name: str
    workspace_role: Role
    role_label: str


class ProjectOptions(ApiModel):
    domains: list[str]
    managers: list[ProjectUserOption]


class ProjectMemberUpdate(ApiModel):
    """Change the descriptive role attached to a project assignment."""

    project_role: str = Field(min_length=1, max_length=100)


class ProjectMemberOut(ApiModel):
    """One governed project assignment."""

    user_id: int
    email: str
    full_name: str
    workspace_role: Role
    project_role: str
    is_active: bool
    created_at: datetime


class PasswordChangeRequest(ApiModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _reject_trivial_password(cls, value: str) -> str:
        return _acceptable_password(value)


class PasswordResetOut(ApiModel):
    """A one-time temporary password issued by an administrator. Shown once, never stored."""

    user_id: int
    temporary_password: str


class RoleDescriptor(ApiModel):
    """A role and what it permits, for the administration screen."""

    role: Role
    label: str
    permissions: list[str]


class DatabaseRevisionOut(ApiModel):
    """One governed schema migration."""

    revision: str
    description: str


class DatabaseStatusOut(ApiModel):
    """Where the database stands against this release. Never carries a host or credential."""

    dialect: str
    current_revision: str | None
    expected_revision: str | None
    is_current: bool
    can_upgrade: bool
    automatic_upgrades: bool
    pending: list[DatabaseRevisionOut]
    round_trip_ms: float | None = None
    database_region: str | None = None
    application_region: str | None = None
