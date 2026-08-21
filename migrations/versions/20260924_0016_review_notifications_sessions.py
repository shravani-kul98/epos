"""Task review, notifications, account-owned actions, sessions, invitations and shared limits.

Revision ID: 20260924_0016
Revises: 20260914_0015
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "20260924_0016"
down_revision = "20260914_0015"
branch_labels = None
depends_on = None

_TEXT = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    """Add nullable or defaulted columns and new tables; no existing value is rewritten."""
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("review_status", _TEXT(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", _TEXT(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("review_note", _TEXT(), nullable=True))
        batch_op.create_index("ix_tasks_review_status", ["review_status"], unique=False)

    with op.batch_alter_table("actions") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_actions_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_foreign_key("fk_actions_owner_user", "users", ["owner_user_id"], ["id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", _TEXT(), nullable=False),
        sa.Column("title", _TEXT(), nullable=False),
        sa.Column("detail", _TEXT(), nullable=True),
        sa.Column("project_id", _TEXT(), nullable=True),
        sa.Column("entity_type", _TEXT(), nullable=True),
        sa.Column("entity_id", _TEXT(), nullable=True),
        sa.Column("actor_name", _TEXT(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_project_id", "notifications", ["project_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_read_at", "notifications", ["read_at"])

    op.create_table(
        "user_sessions",
        sa.Column("id", _TEXT(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", _TEXT(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"])

    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hash", _TEXT(), nullable=False),
        sa.Column("email", _TEXT(), nullable=False),
        sa.Column("role", _TEXT(), nullable=False),
        sa.Column("created_by", _TEXT(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitations_code_hash", "invitations", ["code_hash"], unique=True)
    op.create_index("ix_invitations_email", "invitations", ["email"])

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bucket", _TEXT(), nullable=False),
        sa.Column("key_hash", _TEXT(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_limit_events_bucket", "rate_limit_events", ["bucket"])
    op.create_index("ix_rate_limit_events_key_hash", "rate_limit_events", ["key_hash"])
    op.create_index("ix_rate_limit_events_occurred_at", "rate_limit_events", ["occurred_at"])


def downgrade() -> None:
    """Refuse destructive rollback of review, notification and session history."""
    raise RuntimeError("Downgrade is not supported; restore from a reviewed backup instead.")
