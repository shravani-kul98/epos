"""Require Change Request requirements to belong to the same project.

Revision ID: 20260316_0014
Revises: 20260316_0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0014"
down_revision = "20260316_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Refuse invalid legacy references before adding the composite foreign key."""
    invalid_change_request = op.get_bind().execute(sa.text("""
            SELECT change_requests.change_request_id,
                   change_requests.requirement_id,
                   change_requests.project_id
            FROM change_requests
            LEFT JOIN requirements
              ON requirements.requirement_id = change_requests.requirement_id
             AND requirements.project_id = change_requests.project_id
                WHERE requirements.requirement_id IS NULL
                    OR (
                          change_requests.deleted_at IS NULL
                          AND requirements.deleted_at IS NOT NULL
                    )
            ORDER BY change_requests.change_request_id
            LIMIT 1
            """)).first()
    if invalid_change_request is not None:
        raise RuntimeError(
            "Change Request requirement references must be reviewed before migration: "
            f"{invalid_change_request.change_request_id} -> "
            f"{invalid_change_request.requirement_id} in "
            f"{invalid_change_request.project_id}."
        )

    with op.batch_alter_table("requirements") as batch_op:
        batch_op.create_unique_constraint(
            "uq_requirements_id_project",
            ["requirement_id", "project_id"],
        )
    with op.batch_alter_table("change_requests") as batch_op:
        batch_op.create_foreign_key(
            "fk_change_requests_requirement_project",
            "requirements",
            ["requirement_id", "project_id"],
            ["requirement_id", "project_id"],
        )


def downgrade() -> None:
    """Prevent weakening governed Change Request traceability."""
    raise RuntimeError("Change Request requirement integrity cannot be removed safely.")
