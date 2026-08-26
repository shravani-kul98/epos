"""Shared persistence helpers for the CRUD routers.

Every read here excludes soft-deleted rows, so a withdrawn record disappears from the product and
from the analysis while remaining in the database for audit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import literal_column, union_all
from sqlmodel import Session, SQLModel, select

from api.models import SOURCE_RECORD_TABLES, AuditMixin, DecisionTable

TableT = TypeVar("TableT", bound=SQLModel)
EntityT = TypeVar("EntityT", bound=BaseModel)


def _is_deleted(row: SQLModel) -> bool:
    """True when a row has been soft-deleted."""
    return getattr(row, "deleted_at", None) is not None


def to_entity(row: SQLModel, model: type[EntityT]) -> EntityT:
    """Convert a table row into an engine entity model.

    Audit columns are dropped because the engine contract forbids unexpected fields.
    """
    data = row.model_dump()
    return model.model_validate({k: v for k, v in data.items() if k in model.model_fields})


def get_or_404(session: Session, table: type[TableT], record_id: str, label: str) -> TableT:
    """Return a live row by primary key or raise a 404 naming the record."""
    row = session.get(table, record_id)
    if row is None or _is_deleted(row):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} {record_id} was not found."
        )
    return row


def ensure_absent(session: Session, table: type[SQLModel], record_id: str, label: str) -> None:
    """Reject a create that would collide with an existing identifier.

    A soft-deleted record still owns its identifier, so reusing it is refused rather than silently
    resurrecting old data under a new meaning. Identifiers are also unique across record types,
    because evidence cites them without saying which table they came from. Every table is checked
    in one statement, since each round trip to a hosted database is expensive.
    """
    lookups = [
        select(literal_column(str(position)).label("owner"))
        .select_from(other)
        .where(getattr(other, id_field) == record_id)
        for position, (other, id_field) in enumerate(SOURCE_RECORD_TABLES)
    ]
    owners_by_position = [other for other, _ in SOURCE_RECORD_TABLES]
    if table not in owners_by_position:
        primary_key = next(iter(table.__table__.primary_key.columns))  # type: ignore[attr-defined]
        lookups.append(
            select(literal_column(str(len(owners_by_position))).label("owner"))
            .select_from(table)
            .where(primary_key == record_id)
        )
        owners_by_position.append(table)
    found = session.exec(union_all(*lookups)).scalars().all()  # type: ignore[call-overload]
    owners = {owners_by_position[int(position)] for position in found}
    if table in owners:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"{label} {record_id} already exists."
        )
    if owners:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The identifier {record_id} is already used by another record.",
        )


def ensure_referenced(session: Session, table: type[SQLModel], record_id: str, label: str) -> None:
    """Reject a write whose foreign reference does not exist."""
    row = session.get(table, record_id)
    if row is None or _is_deleted(row):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} {record_id} was not found.",
        )


def ensure_referenced_in_project(
    session: Session,
    table: type[SQLModel],
    record_id: str,
    project_id: str,
    label: str,
) -> None:
    """Reject a reference that is missing, withdrawn, or belongs to another project."""
    row = session.get(table, record_id)
    if row is None or _is_deleted(row) or getattr(row, "project_id", None) != project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} {record_id} was not found in project {project_id}.",
        )


def ensure_not_referenced_by_decisions(
    session: Session, project_id: str, field: str, record_id: str, label: str
) -> None:
    """Refuse to withdraw a record that a live decision still cites."""
    decision_ids = sorted(
        row.decision_id
        for row in list_rows(session, DecisionTable, project_id)
        if getattr(row, field) == record_id
    )
    if decision_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{label} {record_id} cannot be withdrawn while live references remain: "
                f"{', '.join(decision_ids)}."
            ),
        )


def list_rows(
    session: Session,
    table: type[TableT],
    project_id: str | None,
    project_column: str = "project_id",
    project_ids: set[str] | None = None,
) -> list[TableT]:
    """Return every live row, optionally filtered to one project or an authorised set."""
    statement = select(table)
    if project_id is not None:
        statement = statement.where(getattr(table, project_column) == project_id)
    if project_ids is not None:
        statement = statement.where(getattr(table, project_column).in_(sorted(project_ids)))
    if issubclass(table, AuditMixin):
        statement = statement.where(table.deleted_at.is_(None))  # type: ignore[attr-defined]
    return list(session.exec(statement).all())


def apply_update(
    row: SQLModel,
    payload: BaseModel,
    actor_email: str | None = None,
    exclude: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Apply only the fields the client actually sent. Returns the values before the change.

    ``exclude`` names request fields that are not columns, such as a reason for a change.
    """
    changes = payload.model_dump(exclude_unset=True, exclude=set(exclude))
    expected_version = changes.pop("row_version", None)
    if "row_version" in type(payload).model_fields:
        ensure_row_version(row, expected_version)
    before = {field: getattr(row, field) for field in changes}
    for field, value in changes.items():
        setattr(row, field, value)
    stamp_update(row, actor_email)
    return before


def ensure_row_version(row: SQLModel, expected_version: object) -> None:
    """Reject a write based on a stale representation of a governed record."""
    if not isinstance(row, AuditMixin) or expected_version != row.row_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This record changed after it was loaded. Refresh it and try again.",
        )


def stamp_create(row: SQLModel, actor_email: str | None) -> None:
    """Record who created a row."""
    if isinstance(row, AuditMixin):
        row.created_by = actor_email
        row.updated_by = actor_email


def stamp_update(row: SQLModel, actor_email: str | None) -> None:
    """Record who last changed a row and when."""
    if isinstance(row, AuditMixin):
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_email
        row.row_version += 1


def soft_delete(row: SQLModel, actor_email: str | None) -> None:
    """Withdraw a record without destroying it."""
    if isinstance(row, AuditMixin):
        row.deleted_at = datetime.now(UTC)
        stamp_update(row, actor_email)
