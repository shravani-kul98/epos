"""Require a password change after an administrator reset.

Revision ID: 20260925_0017
Revises: 20260924_0016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260925_0017"
down_revision = "20260924_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add one defaulted flag; every existing account keeps its current password."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "password_change_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("password_change_required")
