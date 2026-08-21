"""Add planned, forecast, and actual delivery schedule facts.

Revision ID: 20260316_0009
Revises: 20260316_0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260316_0009"
down_revision = "20260316_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable schedule evidence while preserving every existing record."""
    with op.batch_alter_table("milestones") as batch_op:
        batch_op.add_column(sa.Column("actual_date", sa.Date(), nullable=True))

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("planned_start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("forecast_start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("actual_start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("actual_end_date", sa.Date(), nullable=True))
        batch_op.create_check_constraint(
            "ck_tasks_planned_date_order",
            "planned_start_date IS NULL OR planned_start_date <= planned_end_date",
        )
        batch_op.create_check_constraint(
            "ck_tasks_forecast_date_order",
            "forecast_start_date IS NULL OR forecast_start_date <= forecast_end_date",
        )
        batch_op.create_check_constraint(
            "ck_tasks_actual_end_requires_start",
            "actual_end_date IS NULL OR actual_start_date IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_tasks_actual_date_order",
            "actual_start_date IS NULL OR actual_end_date IS NULL "
            "OR actual_start_date <= actual_end_date",
        )


def downgrade() -> None:
    """Prevent destructive removal of recorded schedule evidence."""
    raise RuntimeError("Delivery schedule facts cannot be removed safely.")
