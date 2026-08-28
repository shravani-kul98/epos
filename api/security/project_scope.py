"""Project-level authorization over persisted membership assignments."""

from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException, status
from sqlmodel import Session, SQLModel, select

from api.models import SOURCE_RECORD_TABLES, ProjectMemberTable, ProjectTable, UserTable
from api.security.permissions import Role

RowT = TypeVar("RowT", bound=SQLModel)

_GLOBAL_READ_ROLES = frozenset({Role.EXECUTIVE, Role.PMO_ANALYST, Role.ADMINISTRATOR})
_GLOBAL_WRITE_ROLES = frozenset({Role.PMO_ANALYST, Role.ADMINISTRATOR})


def project_ids_for(session: Session, user: UserTable, *, write: bool = False) -> set[str] | None:
    """Return authorized project IDs, or ``None`` when the user has global scope."""
    global_roles = _GLOBAL_WRITE_ROLES if write else _GLOBAL_READ_ROLES
    if user.role in global_roles:
        return None
    if user.id is None:
        return set()
    statement = (
        select(ProjectMemberTable.project_id)
        .join(ProjectTable, ProjectTable.project_id == ProjectMemberTable.project_id)
        .where(
            ProjectMemberTable.user_id == user.id,
            ProjectTable.deleted_at.is_(None),
        )
    )
    return set(session.exec(statement).all())


def has_project_access(
    session: Session, user: UserTable, project_id: str, *, write: bool = False
) -> bool:
    """Return whether the user may read or write one project."""
    project = session.get(ProjectTable, project_id)
    if project is None or project.deleted_at is not None:
        return False
    allowed = project_ids_for(session, user, write=write)
    return allowed is None or project_id in allowed


def require_project_access(
    session: Session, user: UserTable, project_id: str, *, write: bool = False
) -> None:
    """Fail closed without revealing whether an inaccessible project exists."""
    if not has_project_access(session, user, project_id, write=write):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} was not found.",
        )


def scope_rows(
    session: Session, user: UserTable, rows: list[RowT], *, write: bool = False
) -> list[RowT]:
    """Remove rows outside the user's authorized project set."""
    allowed = project_ids_for(session, user, write=write)
    if allowed is None:
        return rows
    return [row for row in rows if getattr(row, "project_id", None) in allowed]


def add_membership(
    session: Session, user: UserTable, project_id: str, project_role: str = "Contributor"
) -> ProjectMemberTable:
    """Assign a user to a project unless that assignment already exists."""
    if user.id is None:
        raise ValueError("A persisted user is required for project membership.")
    statement = select(ProjectMemberTable).where(
        ProjectMemberTable.project_id == project_id,
        ProjectMemberTable.user_id == user.id,
    )
    existing = session.exec(statement).first()
    if existing is not None:
        return existing
    membership = ProjectMemberTable(
        project_id=project_id,
        user_id=user.id,
        project_role=project_role,
    )
    session.add(membership)
    return membership


def source_ids_are_authorized(
    session: Session,
    user: UserTable,
    source_ids: set[str],
    generated_source_ids: set[str] | None = None,
) -> bool:
    """Recheck persisted evidence IDs against the user's current project scope."""
    allowed = project_ids_for(session, user)
    if not source_ids:
        return True
    generated_source_ids = generated_source_ids or set()
    live_project_ids = set(
        session.exec(select(ProjectTable.project_id).where(ProjectTable.deleted_at.is_(None))).all()
    )

    wanted = sorted(source_ids)
    source_projects: dict[str, set[str]] = {}
    for table, id_field in SOURCE_RECORD_TABLES:
        column = getattr(table, id_field)
        for row in session.exec(select(table).where(column.in_(wanted))).all():
            source_id = str(getattr(row, id_field))
            project_id = str(row.project_id)
            source_projects.setdefault(source_id, set()).add(project_id)

    for source_id in source_ids:
        projects = source_projects.get(source_id)
        if projects is None:
            if source_id in generated_source_ids:
                continue
            return False
        if not projects.issubset(live_project_ids):
            return False
        if allowed is not None and not projects.issubset(allowed):
            return False
    return True
