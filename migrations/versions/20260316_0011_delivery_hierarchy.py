"""Add governed Work Packages, Deliverables, and optional Task hierarchy links.

Revision ID: 20260316_0011
Revises: 20260316_0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0011"
down_revision = "20260316_0010"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
    ]


def upgrade() -> None:
    """Create empty hierarchy records and preserve legacy Tasks with null links."""
    op.create_table(
        "work_packages",
        *_audit_columns(),
        sa.Column("work_package_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("work_package_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("accountable_owner", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("work_package_id"),
        sa.UniqueConstraint("work_package_id", "project_id", name="uq_work_packages_id_project"),
    )
    op.create_index("ix_work_packages_deleted_at", "work_packages", ["deleted_at"])
    op.create_index("ix_work_packages_project_id", "work_packages", ["project_id"])
    op.create_index("ix_work_packages_status", "work_packages", ["status"])

    op.create_table(
        "deliverables",
        *_audit_columns(),
        sa.Column("deliverable_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("work_package_id", sa.String(), nullable=False),
        sa.Column("deliverable_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("accountable_owner", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("acceptance_criteria", sa.String(), nullable=True),
        sa.Column("completion_evidence", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.ForeignKeyConstraint(
            ["work_package_id", "project_id"],
            ["work_packages.work_package_id", "work_packages.project_id"],
            name="fk_deliverables_work_package_project",
        ),
        sa.PrimaryKeyConstraint("deliverable_id"),
        sa.UniqueConstraint("deliverable_id", "project_id", name="uq_deliverables_id_project"),
    )
    op.create_index("ix_deliverables_deleted_at", "deliverables", ["deleted_at"])
    op.create_index("ix_deliverables_project_id", "deliverables", ["project_id"])
    op.create_index("ix_deliverables_status", "deliverables", ["status"])
    op.create_index("ix_deliverables_work_package_id", "deliverables", ["work_package_id"])

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.create_unique_constraint("uq_tasks_id_project", ["task_id", "project_id"])

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("deliverable_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("parent_task_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_deliverable_project",
            "deliverables",
            ["deliverable_id", "project_id"],
            ["deliverable_id", "project_id"],
        )
        batch_op.create_foreign_key(
            "fk_tasks_parent_project",
            "tasks",
            ["parent_task_id", "project_id"],
            ["task_id", "project_id"],
        )
        batch_op.create_check_constraint(
            "ck_tasks_not_own_parent", "parent_task_id IS NULL OR parent_task_id != task_id"
        )
        batch_op.create_index("ix_tasks_deliverable_id", ["deliverable_id"])
        batch_op.create_index("ix_tasks_parent_task_id", ["parent_task_id"])


def downgrade() -> None:
    """Prevent destructive removal of governed delivery hierarchy records."""
    raise RuntimeError("Delivery hierarchy records cannot be removed safely.")
