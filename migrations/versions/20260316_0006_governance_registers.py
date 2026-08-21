"""Add governed issue and assumption registers.

Revision ID: 20260316_0006
Revises: 20260316_0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0006"
down_revision = "20260316_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create empty governance tables without changing existing project records."""
    op.create_table(
        "issues",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("raised_date", sa.Date(), nullable=False),
        sa.Column("target_resolution_date", sa.Date(), nullable=True),
        sa.Column("resolution_summary", sa.String(), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("source_reference", sa.String(), nullable=True),
        sa.CheckConstraint(
            "status IN ('Open', 'In Progress', 'Resolved', 'Closed')",
            name="ck_issues_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("issue_id"),
    )
    op.create_index("ix_issues_deleted_at", "issues", ["deleted_at"])
    op.create_index("ix_issues_project_id", "issues", ["project_id"])
    op.create_index("ix_issues_status", "issues", ["status"])

    op.create_table(
        "assumptions",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("assumption_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("assumption_text", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("validation_due_date", sa.Date(), nullable=True),
        sa.Column("impact_if_false", sa.String(), nullable=True),
        sa.Column("validation_evidence", sa.String(), nullable=True),
        sa.Column("validated_by", sa.String(), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("source_reference", sa.String(), nullable=True),
        sa.CheckConstraint(
            "status IN ('Proposed', 'Validated', 'Invalidated', 'Retired')",
            name="ck_assumptions_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("assumption_id"),
    )
    op.create_index("ix_assumptions_deleted_at", "assumptions", ["deleted_at"])
    op.create_index("ix_assumptions_project_id", "assumptions", ["project_id"])
    op.create_index("ix_assumptions_status", "assumptions", ["status"])


def downgrade() -> None:
    """Prevent destructive removal of governed records."""
    raise RuntimeError("Governance registers cannot be removed destructively.")
