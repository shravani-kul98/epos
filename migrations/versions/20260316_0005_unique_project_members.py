"""Require one membership assignment per project and user.

Revision ID: 20260316_0005
Revises: 20260316_0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0005"
down_revision = "20260316_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Reject ambiguous legacy data, then enforce assignment uniqueness."""
    duplicate = op.get_bind().execute(sa.text("""
            SELECT project_id, user_id
            FROM project_members
            GROUP BY project_id, user_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """)).first()
    if duplicate is not None:
        raise RuntimeError("Duplicate project memberships must be reviewed before migration.")

    with op.batch_alter_table("project_members") as batch_op:
        batch_op.create_unique_constraint(
            "uq_project_members_project_user", ["project_id", "user_id"]
        )


def downgrade() -> None:
    """Prevent weakening a security-critical assignment invariant."""
    raise RuntimeError("Project membership uniqueness cannot be removed safely.")
