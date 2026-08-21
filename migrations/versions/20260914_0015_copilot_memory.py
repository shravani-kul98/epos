"""Persist complete copilot answers and validated conversation selectors."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260914_0015"
down_revision = "20260316_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve legacy messages while adding structured answer snapshots."""
    with op.batch_alter_table("conversation_messages") as batch:
        batch.add_column(sa.Column("answer_json", sa.String(), nullable=True))
        batch.add_column(sa.Column("context_json", sa.String(), nullable=True))


def downgrade() -> None:
    """Refuse to discard saved conversation context."""
    raise RuntimeError("Restore from a reviewed backup instead of discarding conversation history.")
