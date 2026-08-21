"""Add optimistic-concurrency versions to mutable business records.

Revision ID: 20260316_0003
Revises: 20260316_0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0003"
down_revision = "20260316_0002"
branch_labels = None
depends_on = None

_VERSIONED_TABLES = (
    "projects",
    "milestones",
    "tasks",
    "risks",
    "dependencies",
    "actions",
    "resources",
    "requirements",
    "test_cases",
    "trace_links",
    "change_requests",
    "decisions",
    "meeting_notes",
)


def upgrade() -> None:
    """Backfill every existing record at version one."""
    for table_name in _VERSIONED_TABLES:
        op.add_column(
            table_name,
            sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )


def downgrade() -> None:
    """Prevent removal of concurrency evidence from governed records."""
    raise RuntimeError("Row-version evidence cannot be removed destructively.")
