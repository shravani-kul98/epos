"""Add governed stage Gates, criteria, and immutable review outcomes.

Revision ID: 20260316_0012
Revises: 20260316_0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0012"
down_revision = "20260316_0011"
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
    """Create empty Gate governance tables without inventing historical reviews."""
    op.create_table(
        "gates",
        *_audit_columns(),
        sa.Column("gate_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("milestone_id", sa.String(), nullable=True),
        sa.Column("gate_name", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("planned_review_date", sa.Date(), nullable=False),
        sa.Column("actual_review_date", sa.Date(), nullable=True),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("review_cycle", sa.Integer(), nullable=False),
        sa.Column("applicable_baseline", sa.String(), nullable=True),
        sa.CheckConstraint("sequence > 0", name="ck_gates_positive_sequence"),
        sa.CheckConstraint("review_cycle > 0", name="ck_gates_positive_review_cycle"),
        sa.CheckConstraint(
            "status IN ('Not Started', 'Preparing', 'Ready for Review', 'In Review', "
            "'Passed', 'Passed with Conditions', 'Failed', 'Deferred', 'Withdrawn')",
            name="ck_gates_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.ForeignKeyConstraint(
            ["milestone_id", "project_id"],
            ["milestones.milestone_id", "milestones.project_id"],
            name="fk_gates_milestone_project",
        ),
        sa.PrimaryKeyConstraint("gate_id"),
        sa.UniqueConstraint("gate_id", "project_id", name="uq_gates_id_project"),
        sa.UniqueConstraint("project_id", "sequence", name="uq_gates_project_sequence"),
    )
    op.create_index("ix_gates_deleted_at", "gates", ["deleted_at"])
    op.create_index("ix_gates_milestone_id", "gates", ["milestone_id"])
    op.create_index("ix_gates_project_id", "gates", ["project_id"])
    op.create_index("ix_gates_status", "gates", ["status"])

    op.create_table(
        "gate_criteria",
        *_audit_columns(),
        sa.Column("criterion_id", sa.String(), nullable=False),
        sa.Column("gate_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("criterion_type", sa.String(), nullable=False),
        sa.Column("criterion_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False),
        sa.Column("evidence_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("evidence_reference", sa.String(), nullable=True),
        sa.Column("assessment_rationale", sa.String(), nullable=True),
        sa.Column("assessed_by", sa.String(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("criterion_type IN ('Entry', 'Exit')", name="ck_gate_criteria_type"),
        sa.CheckConstraint(
            "status IN ('Not Assessed', 'Met', 'Not Met')",
            name="ck_gate_criteria_status",
        ),
        sa.CheckConstraint(
            "status != 'Met' OR evidence_required = 0 OR "
            "(evidence_reference IS NOT NULL AND length(trim(evidence_reference)) > 0)",
            name="ck_gate_criteria_required_evidence",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.ForeignKeyConstraint(
            ["gate_id", "project_id"],
            ["gates.gate_id", "gates.project_id"],
            name="fk_gate_criteria_gate_project",
        ),
        sa.PrimaryKeyConstraint("criterion_id"),
    )
    op.create_index("ix_gate_criteria_deleted_at", "gate_criteria", ["deleted_at"])
    op.create_index("ix_gate_criteria_gate_id", "gate_criteria", ["gate_id"])
    op.create_index("ix_gate_criteria_project_id", "gate_criteria", ["project_id"])
    op.create_index("ix_gate_criteria_status", "gate_criteria", ["status"])

    op.create_table(
        "gate_reviews",
        sa.Column("review_id", sa.String(), nullable=False),
        sa.Column("gate_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("reviewer", sa.String(), nullable=False),
        sa.Column("review_cycle", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=False),
        sa.Column("conditions", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('Approved', 'Approved with Conditions', 'Rejected', 'Deferred')",
            name="ck_gate_reviews_outcome",
        ),
        sa.CheckConstraint("review_cycle > 0", name="ck_gate_reviews_positive_cycle"),
        sa.CheckConstraint(
            "(outcome = 'Approved with Conditions' AND conditions IS NOT NULL "
            "AND length(trim(conditions)) > 0) OR "
            "(outcome != 'Approved with Conditions' AND conditions IS NULL)",
            name="ck_gate_reviews_conditions",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.ForeignKeyConstraint(
            ["gate_id", "project_id"],
            ["gates.gate_id", "gates.project_id"],
            name="fk_gate_reviews_gate_project",
        ),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint("gate_id", "review_cycle", name="uq_gate_reviews_gate_cycle"),
    )
    op.create_index("ix_gate_reviews_gate_id", "gate_reviews", ["gate_id"])
    op.create_index("ix_gate_reviews_outcome", "gate_reviews", ["outcome"])
    op.create_index("ix_gate_reviews_project_id", "gate_reviews", ["project_id"])
    op.create_index("ix_gate_reviews_reviewed_at", "gate_reviews", ["reviewed_at"])
    op.execute("""
        CREATE TRIGGER gate_reviews_no_update
        BEFORE UPDATE ON gate_reviews
        BEGIN
            SELECT RAISE(ABORT, 'Gate Reviews are immutable');
        END
        """)
    op.execute("""
        CREATE TRIGGER gate_reviews_no_delete
        BEFORE DELETE ON gate_reviews
        BEGIN
            SELECT RAISE(ABORT, 'Gate Reviews are immutable');
        END
        """)


def downgrade() -> None:
    """Prevent destructive removal of Gate governance and approval evidence."""
    raise RuntimeError("Stage-Gate governance records cannot be removed safely.")
