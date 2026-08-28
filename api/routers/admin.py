"""Administrator-only user and role management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from api import database, settings
from api.dependencies import SessionDep
from api.models import ActionTable, TaskTable, UserTable
from api.schemas_auth import (
    ActiveUpdateRequest,
    DatabaseRevisionOut,
    DatabaseStatusOut,
    InvitationCreate,
    InvitationIssued,
    InvitationOut,
    PasswordResetOut,
    RoleDescriptor,
    RoleUpdateRequest,
    UserOut,
)
from api.security import sessions
from api.security.dependencies import UserAdministrator
from api.security.permissions import ROLE_PERMISSIONS, Permission, Role, has_permission, role_label
from api.services import activity_service, user_service
from src.scoring_rules import is_terminal_schedule_status
from src.workflow_rules import ActionStatus

router = APIRouter(prefix="/admin", tags=["administration"])

_CLOSED_ACTION_STATES = frozenset({ActionStatus.COMPLETE.value, ActionStatus.CANCELLED.value})


def _ensure_no_open_assignments(session: SessionDep, user: UserTable, change: str) -> None:
    """Refuse a change that would leave assigned work with someone who cannot update it."""
    open_task_ids = sorted(
        task.task_id
        for task in session.exec(
            select(TaskTable).where(
                TaskTable.owner_user_id == user.id, TaskTable.deleted_at.is_(None)
            )
        ).all()
        if not is_terminal_schedule_status(task.status)
    )
    open_action_ids = sorted(
        action.action_id
        for action in session.exec(
            select(ActionTable).where(
                ActionTable.owner_user_id == user.id, ActionTable.deleted_at.is_(None)
            )
        ).all()
        if action.status not in _CLOSED_ACTION_STATES
    )
    if open_task_ids or open_action_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Reassign or complete {user.full_name}'s open work before you {change}: "
                f"{', '.join([*open_task_ids, *open_action_ids])}."
            ),
        )


@router.get("/roles", response_model=list[RoleDescriptor])
def list_roles(_: UserAdministrator) -> list[RoleDescriptor]:
    """Every role and the permissions it grants."""
    return [
        RoleDescriptor(
            role=role,
            label=role_label(role),
            permissions=sorted(permission.value for permission in permissions),
        )
        for role, permissions in ROLE_PERMISSIONS.items()
    ]


@router.get("/users", response_model=list[UserOut])
def list_users(session: SessionDep, _: UserAdministrator) -> list[UserOut]:
    """Every account in the workspace."""
    users = session.exec(select(UserTable).order_by(UserTable.email)).all()
    return [user_service.user_out(user) for user in users]


@router.patch("/users/{user_id}/role", response_model=UserOut)
def set_role(
    user_id: int, payload: RoleUpdateRequest, session: SessionDep, admin: UserAdministrator
) -> UserOut:
    """Change a user's role."""
    user = _get_user(session, user_id)
    if user.id == admin.id and payload.role is not Role.ADMINISTRATOR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot remove your own administrator access.",
        )
    if not has_permission(payload.role, Permission.WORK_UPDATE):
        _ensure_no_open_assignments(session, user, f"make them {role_label(payload.role)}")

    previous = user.role
    user.role = payload.role
    session.add(user)
    activity_service.record(
        session,
        action="updated",
        entity_type="User",
        entity_id=user.email,
        summary=f"Changed {user.full_name} from {role_label(previous)} to {role_label(user.role)}",
        actor=admin,
    )
    session.commit()
    session.refresh(user)
    return user_service.user_out(user)


@router.patch("/users/{user_id}/active", response_model=UserOut)
def set_active(
    user_id: int, payload: ActiveUpdateRequest, session: SessionDep, admin: UserAdministrator
) -> UserOut:
    """Enable or disable an account."""
    user = _get_user(session, user_id)
    if user.id == admin.id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot disable your own account.",
        )
    if not payload.is_active:
        _ensure_no_open_assignments(session, user, "disable the account")

    user.is_active = payload.is_active
    session.add(user)
    if not payload.is_active:
        sessions.revoke_all(session, user.id or 0)
    activity_service.record(
        session,
        action="updated",
        entity_type="User",
        entity_id=user.email,
        summary=f"{'Enabled' if payload.is_active else 'Disabled'} the account for {user.full_name}",
        actor=admin,
    )
    session.commit()
    session.refresh(user)
    return user_service.user_out(user)


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
def reset_password(user_id: int, session: SessionDep, admin: UserAdministrator) -> PasswordResetOut:
    """Issue a one-time temporary password and end the user's existing sessions.

    The password is returned once for the administrator to pass on, and is never recorded.
    """
    user = _get_user(session, user_id)
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Change your own password from your account page instead.",
        )
    temporary = user_service.reset_password(session, user)
    activity_service.record(
        session,
        action="updated",
        entity_type="User",
        entity_id=user.email,
        summary=f"Reset the password for {user.full_name}",
        actor=admin,
    )
    session.commit()
    return PasswordResetOut(user_id=user.id or 0, temporary_password=temporary)


@router.post("/users/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_sessions(user_id: int, session: SessionDep, admin: UserAdministrator) -> None:
    """Sign a person out of every browser and client, for example after a lost device."""
    user = _get_user(session, user_id)
    ended = sessions.revoke_all(session, user.id or 0, keep=None)
    activity_service.record(
        session,
        action="updated",
        entity_type="User",
        entity_id=user.email,
        summary=f"Ended {ended} active session{'s' if ended != 1 else ''} for {user.full_name}",
        actor=admin,
    )
    session.commit()


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(session: SessionDep, _: UserAdministrator) -> list[InvitationOut]:
    return user_service.list_invitations(session)


@router.post("/invitations", response_model=InvitationIssued, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate, session: SessionDep, admin: UserAdministrator
) -> InvitationIssued:
    """Invite one address with a chosen role. The code is returned once and never stored."""
    row, code = user_service.create_invitation(session, admin, payload.email, payload.role)
    activity_service.record(
        session,
        action="created",
        entity_type="Invitation",
        entity_id=str(row.id),
        summary=f"Invited {row.email} as {role_label(payload.role)}",
        actor=admin,
    )
    session.commit()
    return InvitationIssued(invitation=user_service.invitation_out(row), code=code)


@router.post("/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def revoke_invitation(
    invitation_id: int, session: SessionDep, admin: UserAdministrator
) -> InvitationOut:
    revoked = user_service.revoke_invitation(session, invitation_id)
    activity_service.record(
        session,
        action="updated",
        entity_type="Invitation",
        entity_id=str(invitation_id),
        summary=f"Withdrew the invitation for {revoked.email}",
        actor=admin,
    )
    session.commit()
    return revoked


def _get_user(session: SessionDep, user_id: int) -> UserTable:
    """Return a user or raise a 404."""
    user = session.get(UserTable, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That user was not found."
        )
    return user


def _database_out(state: database.SchemaStatus) -> DatabaseStatusOut:
    return DatabaseStatusOut(
        dialect=state.dialect,
        current_revision=state.current_revision,
        expected_revision=state.expected_revision,
        is_current=state.is_current,
        can_upgrade=state.can_upgrade,
        automatic_upgrades=settings.schema_auto_upgrade(),
        pending=[
            DatabaseRevisionOut(revision=step.revision, description=step.description)
            for step in state.pending
        ],
        round_trip_ms=state.round_trip_ms,
        database_region=state.database_region,
        application_region=state.application_region,
    )


@router.get("/database", response_model=DatabaseStatusOut)
def database_status(_: UserAdministrator) -> DatabaseStatusOut:
    """The schema revision, pending upgrades and one measured database round trip."""
    return _database_out(database.schema_status(measure=True))


@router.post("/database/upgrade", response_model=DatabaseStatusOut)
def upgrade_database(session: SessionDep, admin: UserAdministrator) -> DatabaseStatusOut:
    """Apply the governed migrations this release needs, so no console access is required."""
    before = database.schema_status()
    if before.current_revision is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This database has not been initialised for EPOS, so it cannot be upgraded here.",
        )
    if not before.can_upgrade:
        return _database_out(database.schema_status(measure=True))
    # End this request's own transaction first: its reads would otherwise block the upgrade.
    session.commit()
    after = database.apply_pending_upgrades()
    activity_service.record(
        session,
        action="updated",
        entity_type="Database",
        entity_id=after.current_revision or "schema",
        project_id=None,
        summary=(
            f"Upgraded the database schema from {before.current_revision} "
            f"to {after.current_revision}"
        ),
        actor=admin,
    )
    session.commit()
    return _database_out(after)
