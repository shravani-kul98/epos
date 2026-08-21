"""Link risk, issue and assumption owners to accounts, and record assignment responses.

Revision ID: 20260925_0018
Revises: 20260925_0017
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260925_0018"
down_revision = "20260925_0017"
branch_labels = None
depends_on = None

_OWNER_LINKS = (
    ("risks", "mitigation_owner_user_id", "fk_risks_mitigation_owner_user"),
    ("issues", "owner_user_id", "fk_issues_owner_user"),
    ("assumptions", "owner_user_id", "fk_assumptions_owner_user"),
)


def upgrade() -> None:
    """Additive only: nullable columns, so every existing record keeps its recorded owner name."""
    for table, column, constraint in _OWNER_LINKS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column(column, sa.Integer(), nullable=True))
            batch_op.create_index(f"ix_{table}_{column}", [column], unique=False)
            batch_op.create_foreign_key(constraint, "users", [column], ["id"])
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("assignment_status", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("assignment_responded_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("assignment_note", sa.String(), nullable=True))
        batch_op.create_index("ix_tasks_assignment_status", ["assignment_status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_tasks_assignment_status")
        batch_op.drop_column("assignment_note")
        batch_op.drop_column("assignment_responded_at")
        batch_op.drop_column("assignment_status")
    for table, column, constraint in reversed(_OWNER_LINKS):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(constraint, type_="foreignkey")
            batch_op.drop_index(f"ix_{table}_{column}")
            batch_op.drop_column(column)
