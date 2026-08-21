"""Add structured field changes to append-only activity events.

Revision ID: 20260316_0004
Revises: 20260316_0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0004"
down_revision = "20260316_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable JSON text so existing free-text events remain valid."""
    op.add_column("activity_events", sa.Column("changes_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """Prevent removal of structured audit evidence."""
    raise RuntimeError("Structured activity evidence cannot be removed destructively.")
