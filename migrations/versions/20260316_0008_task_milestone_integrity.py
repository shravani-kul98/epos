"""Require Task milestones to belong to the same project.

Revision ID: 20260316_0008
Revises: 20260316_0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0008"
down_revision = "20260316_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Refuse invalid legacy hierarchy before adding its composite foreign key."""
    invalid_task = op.get_bind().execute(sa.text("""
            SELECT tasks.task_id, tasks.milestone_id, tasks.project_id
            FROM tasks
            LEFT JOIN milestones
              ON milestones.milestone_id = tasks.milestone_id
             AND milestones.project_id = tasks.project_id
            WHERE milestones.milestone_id IS NULL
            LIMIT 1
            """)).first()
    if invalid_task is not None:
        raise RuntimeError(
            "Task milestone references must be reviewed before migration: "
            f"{invalid_task.task_id} -> {invalid_task.milestone_id} "
            f"in {invalid_task.project_id}."
        )

    with op.batch_alter_table("milestones") as batch_op:
        batch_op.create_unique_constraint(
            "uq_milestones_id_project", ["milestone_id", "project_id"]
        )
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.create_foreign_key(
            "fk_tasks_milestone_project",
            "milestones",
            ["milestone_id", "project_id"],
            ["milestone_id", "project_id"],
        )


def downgrade() -> None:
    """Prevent weakening the governed delivery hierarchy."""
    raise RuntimeError("Task milestone integrity cannot be removed safely.")
