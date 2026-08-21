"""Baseline the existing EPOS schema.

Revision ID: 20260316_0001
Revises: None
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "20260316_0001"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_TABLES = {
    "actions",
    "activity_events",
    "change_requests",
    "conversation_messages",
    "conversations",
    "decisions",
    "dependencies",
    "meeting_notes",
    "milestones",
    "project_members",
    "projects",
    "requirements",
    "resources",
    "risks",
    "saved_scenarios",
    "saved_views",
    "tasks",
    "test_cases",
    "trace_links",
    "users",
}


def upgrade() -> None:
    """Validate a complete pre-Alembic schema before the frozen baseline runs.

    Empty databases continue to the next revision, which owns the explicit baseline DDL.
    Existing databases are adopted only when every baseline table is present.
    """
    connection = op.get_bind()
    existing_tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
    if existing_tables:
        missing_tables = BASELINE_TABLES - existing_tables
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise RuntimeError(
                f"Cannot adopt a partial pre-Alembic schema; missing tables: {missing}"
            )


def downgrade() -> None:
    """Keep the adopted baseline intact; destructive schema resets are not supported."""
    raise RuntimeError("The EPOS baseline migration cannot be downgraded destructively.")
