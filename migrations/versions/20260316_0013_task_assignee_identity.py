"""Add stable user identity for task assignees.

Revision ID: 20260316_0013
Revises: 20260316_0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0013"
down_revision = "20260316_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a nullable, indexed user reference without guessing legacy assignments."""
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_tasks_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_tasks_owner_user",
            "users",
            ["owner_user_id"],
            ["id"],
        )


def downgrade() -> None:
    """Refuse destructive rollback of governed assignment history."""
    raise RuntimeError("Downgrade is not supported; restore from a reviewed backup instead.")
