"""Constrain Action and Decision lifecycle states.

Revision ID: 20260316_0007
Revises: 20260316_0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0007"
down_revision = "20260316_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Reject unknown legacy states before installing lifecycle constraints."""
    connection = op.get_bind()
    invalid_action = connection.execute(sa.text("""
            SELECT action_id FROM actions
            WHERE status NOT IN ('Open', 'In Progress', 'Blocked', 'Complete', 'Cancelled')
            LIMIT 1
            """)).first()
    invalid_decision = connection.execute(sa.text("""
            SELECT decision_id FROM decisions
            WHERE status NOT IN ('Proposed', 'Approved', 'Rejected', 'Superseded')
            LIMIT 1
            """)).first()
    if invalid_action is not None or invalid_decision is not None:
        raise RuntimeError("Unknown Action or Decision states must be reviewed before migration.")

    with op.batch_alter_table("actions") as batch_op:
        batch_op.create_check_constraint(
            "ck_actions_status",
            "status IN ('Open', 'In Progress', 'Blocked', 'Complete', 'Cancelled')",
        )
    with op.batch_alter_table("decisions") as batch_op:
        batch_op.create_check_constraint(
            "ck_decisions_status",
            "status IN ('Proposed', 'Approved', 'Rejected', 'Superseded')",
        )


def downgrade() -> None:
    """Prevent weakening governed lifecycle constraints."""
    raise RuntimeError("Action and Decision state constraints cannot be removed safely.")
