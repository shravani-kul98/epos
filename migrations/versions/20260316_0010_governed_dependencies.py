"""Add governed relationship metadata and constraints to dependencies.

Revision ID: 20260316_0010
Revises: 20260316_0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from src.delivery_rules import (
    SCHEDULABLE_ENDPOINT_TYPES,
    DeliveryNetworkError,
    DependencyEdge,
    DependencyEndpointType,
    ensure_acyclic_dependency_network,
    ensure_unique_dependency_edges,
)

revision = "20260316_0010"
down_revision = "20260316_0009"
branch_labels = None
depends_on = None

_PREDECESSOR_TYPES = "'Task', 'Milestone', 'Supplier', 'External', 'Customer'"
_SUCCESSOR_TYPES = "'Task', 'Milestone'"
_RELATIONSHIP_TYPES = "'Finish-to-Start', 'Start-to-Start', 'Finish-to-Finish', 'Start-to-Finish'"


def upgrade() -> None:
    """Refuse ambiguous legacy edges before installing governed constraints."""
    connection = op.get_bind()
    invalid = connection.execute(sa.text(f"""
            SELECT dependency_id FROM dependencies
            WHERE predecessor_type NOT IN ({_PREDECESSOR_TYPES})
               OR successor_type NOT IN ({_SUCCESSOR_TYPES})
               OR delay_days < 0
               OR (predecessor_type = successor_type AND predecessor_id = successor_id)
            LIMIT 1
            """)).first()
    if invalid is not None:
        raise RuntimeError(f"Dependency {invalid.dependency_id} must be reviewed before migration.")

    rows = list(connection.execute(sa.text("""
                SELECT dependency_id, project_id, predecessor_type, predecessor_id,
                       successor_type, successor_id, deleted_at
                FROM dependencies
                """)).mappings())
    endpoint_projects = {
        DependencyEndpointType.TASK: {
            (row.task_id, row.project_id)
            for row in connection.execute(
                sa.text("SELECT task_id, project_id FROM tasks WHERE deleted_at IS NULL")
            )
        },
        DependencyEndpointType.MILESTONE: {
            (row.milestone_id, row.project_id)
            for row in connection.execute(
                sa.text(
                    "SELECT milestone_id, project_id FROM milestones " "WHERE deleted_at IS NULL"
                )
            )
        },
    }
    for row in rows:
        if row["deleted_at"] is not None:
            continue
        for endpoint_type, endpoint_id in (
            (DependencyEndpointType(row["predecessor_type"]), row["predecessor_id"]),
            (DependencyEndpointType(row["successor_type"]), row["successor_id"]),
        ):
            if (
                endpoint_type in SCHEDULABLE_ENDPOINT_TYPES
                and (
                    endpoint_id,
                    row["project_id"],
                )
                not in endpoint_projects[endpoint_type]
            ):
                raise RuntimeError(
                    f"Dependency {row['dependency_id']} references {endpoint_type.value} "
                    f"{endpoint_id} outside project {row['project_id']}."
                )

    edges = [
        DependencyEdge(
            dependency_id=row["dependency_id"],
            predecessor_type=DependencyEndpointType(row["predecessor_type"]),
            predecessor_id=row["predecessor_id"],
            successor_type=DependencyEndpointType(row["successor_type"]),
            successor_id=row["successor_id"],
        )
        for row in rows
    ]
    try:
        ensure_unique_dependency_edges(edges)
        ensure_acyclic_dependency_network(
            edge for edge, row in zip(edges, rows, strict=True) if row["deleted_at"] is None
        )
    except DeliveryNetworkError as exc:
        raise RuntimeError(str(exc)) from exc

    with op.batch_alter_table("dependencies") as batch_op:
        batch_op.add_column(sa.Column("relationship_type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("lag_days", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_dependencies_predecessor_type",
            f"predecessor_type IN ({_PREDECESSOR_TYPES})",
        )
        batch_op.create_check_constraint(
            "ck_dependencies_successor_type",
            f"successor_type IN ({_SUCCESSOR_TYPES})",
        )
        batch_op.create_check_constraint(
            "ck_dependencies_relationship_type",
            f"relationship_type IS NULL OR relationship_type IN ({_RELATIONSHIP_TYPES})",
        )
        batch_op.create_check_constraint(
            "ck_dependencies_relationship_metadata",
            "(relationship_type IS NULL AND lag_days IS NULL) OR "
            "(relationship_type IS NOT NULL AND lag_days IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_dependencies_not_self_referencing",
            "predecessor_type != successor_type OR predecessor_id != successor_id",
        )
        batch_op.create_check_constraint("ck_dependencies_delay_days", "delay_days >= 0")
        batch_op.create_unique_constraint(
            "uq_dependencies_project_edge",
            [
                "project_id",
                "predecessor_type",
                "predecessor_id",
                "successor_type",
                "successor_id",
            ],
        )


def downgrade() -> None:
    """Prevent destructive removal of dependency relationship evidence."""
    raise RuntimeError("Governed dependency metadata cannot be removed safely.")
