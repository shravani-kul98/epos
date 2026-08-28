"""Separation of duties for governed outcomes."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import SQLModel

from api.models import UserTable
from api.security.permissions import Role


def ensure_independent_decider(row: SQLModel, actor: UserTable, record: str) -> None:
    """Refuse an outcome recorded by the person who raised the record.

    Administrators keep a break-glass exception; the audit trail names whoever used it.
    """
    if actor.role is Role.ADMINISTRATOR:
        return
    raised_by = getattr(row, "created_by", None)
    if raised_by and raised_by == actor.email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You raised this {record}, so another person with decision rights must "
                "record its outcome."
            ),
        )
