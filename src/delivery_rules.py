"""Deterministic validation rules for engineering delivery networks."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class DependencyEndpointType(StrEnum):
    TASK = "Task"
    MILESTONE = "Milestone"
    SUPPLIER = "Supplier"
    EXTERNAL = "External"
    CUSTOMER = "Customer"


class DependencyRelationshipType(StrEnum):
    FINISH_TO_START = "Finish-to-Start"
    START_TO_START = "Start-to-Start"
    FINISH_TO_FINISH = "Finish-to-Finish"
    START_TO_FINISH = "Start-to-Finish"


SCHEDULABLE_ENDPOINT_TYPES: Final[frozenset[DependencyEndpointType]] = frozenset(
    {DependencyEndpointType.TASK, DependencyEndpointType.MILESTONE}
)

# Ten years either way: beyond this a lag or delay is a data-entry error, not a plan.
DEPENDENCY_MAX_LAG_DAYS: Final[int] = 3650
DEPENDENCY_MAX_DELAY_DAYS: Final[int] = 3650


class DeliveryNetworkError(ValueError):
    """Raised when governed dependency evidence is incomplete or cyclic."""


class DeliveryHierarchyError(ValueError):
    """Raised when governed delivery hierarchy evidence is invalid."""


@dataclass(frozen=True)
class TaskHierarchyNode:
    """The fields needed to validate one Task's optional parent relationship."""

    task_id: str
    project_id: str
    parent_task_id: str | None
    deliverable_id: str | None = None


@dataclass(frozen=True)
class DependencyEdge:
    """The graph fields needed to validate one persisted dependency."""

    dependency_id: str
    predecessor_type: DependencyEndpointType
    predecessor_id: str
    successor_type: DependencyEndpointType
    successor_id: str


def ensure_valid_task_hierarchy(nodes: Iterable[TaskHierarchyNode]) -> None:
    """Reject missing, cross-project, self-referencing, or cyclic Task parents."""
    by_id: dict[str, TaskHierarchyNode] = {}
    for node in nodes:
        if node.task_id in by_id:
            raise DeliveryHierarchyError(
                f"Task hierarchy contains duplicate source record {node.task_id}."
            )
        by_id[node.task_id] = node

    for node in by_id.values():
        if node.parent_task_id is None:
            continue
        if node.parent_task_id == node.task_id:
            raise DeliveryHierarchyError(f"Task {node.task_id} cannot be its own parent.")
        parent = by_id.get(node.parent_task_id)
        if parent is None:
            raise DeliveryHierarchyError(
                f"Task {node.task_id} references missing parent Task {node.parent_task_id}."
            )
        if parent.project_id != node.project_id:
            raise DeliveryHierarchyError(
                f"Task {node.task_id} and parent Task {parent.task_id} belong to "
                "different projects."
            )
        if parent.deliverable_id != node.deliverable_id:
            raise DeliveryHierarchyError(
                f"Task {node.task_id} and parent Task {parent.task_id} belong to "
                "different Deliverables."
            )

    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(task_id: str) -> None:
        state[task_id] = 1
        stack.append(task_id)
        parent_id = by_id[task_id].parent_task_id
        if parent_id is not None:
            parent_state = state.get(parent_id, 0)
            if parent_state == 0:
                visit(parent_id)
            elif parent_state == 1:
                cycle_start = stack.index(parent_id)
                source_ids = sorted(stack[cycle_start:])
                raise DeliveryHierarchyError(
                    "Task hierarchy contains a parent cycle supported by source records: "
                    f"{', '.join(source_ids)}."
                )
        stack.pop()
        state[task_id] = 2

    for task_id in sorted(by_id):
        if state.get(task_id, 0) == 0:
            visit(task_id)


def ensure_dependency_metadata(
    edge: DependencyEdge,
    relationship_type: DependencyRelationshipType | None,
    lag_days: int | None,
    *,
    require_complete: bool,
) -> None:
    """Reject self-links and incomplete schedule relationship metadata."""
    predecessor = (edge.predecessor_type, edge.predecessor_id)
    successor = (edge.successor_type, edge.successor_id)
    if predecessor == successor:
        raise DeliveryNetworkError(
            f"Dependency {edge.dependency_id} cannot link a record to itself."
        )
    if (relationship_type is None) != (lag_days is None):
        raise DeliveryNetworkError(
            f"Dependency {edge.dependency_id} must record relationship type and lag together."
        )
    if lag_days is not None and abs(lag_days) > DEPENDENCY_MAX_LAG_DAYS:
        raise DeliveryNetworkError(
            f"Dependency {edge.dependency_id} lag must be within {DEPENDENCY_MAX_LAG_DAYS} days."
        )
    if (
        require_complete
        and edge.predecessor_type in SCHEDULABLE_ENDPOINT_TYPES
        and relationship_type is None
    ):
        raise DeliveryNetworkError(
            f"Dependency {edge.dependency_id} requires relationship type and lag for its "
            "schedulable endpoints."
        )


def ensure_unique_dependency_edges(edges: Iterable[DependencyEdge]) -> list[DependencyEdge]:
    """Reject duplicate endpoint pairs and return a reusable materialized edge list."""
    edge_list = list(edges)
    seen: dict[tuple[DependencyEndpointType, str, DependencyEndpointType, str], str] = {}
    for edge in edge_list:
        key = (
            edge.predecessor_type,
            edge.predecessor_id,
            edge.successor_type,
            edge.successor_id,
        )
        previous_id = seen.get(key)
        if previous_id is not None:
            raise DeliveryNetworkError(
                f"Dependencies {previous_id} and {edge.dependency_id} duplicate the same edge."
            )
        seen[key] = edge.dependency_id
    return edge_list


def ensure_acyclic_dependency_network(edges: Iterable[DependencyEdge]) -> None:
    """Reject cycles among Task and Milestone endpoints and cite supporting IDs."""
    edge_list = ensure_unique_dependency_edges(edges)

    schedulable = [
        edge
        for edge in edge_list
        if edge.predecessor_type in SCHEDULABLE_ENDPOINT_TYPES
        and edge.successor_type in SCHEDULABLE_ENDPOINT_TYPES
    ]
    outgoing: dict[
        tuple[DependencyEndpointType, str],
        list[tuple[DependencyEndpointType, str]],
    ] = defaultdict(list)
    indegree: dict[tuple[DependencyEndpointType, str], int] = {}
    for edge in schedulable:
        predecessor = (edge.predecessor_type, edge.predecessor_id)
        successor = (edge.successor_type, edge.successor_id)
        outgoing[predecessor].append(successor)
        indegree.setdefault(predecessor, 0)
        indegree[successor] = indegree.get(successor, 0) + 1

    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    processed: set[tuple[DependencyEndpointType, str]] = set()
    while ready:
        node = ready.pop(0)
        processed.add(node)
        for successor in sorted(outgoing[node]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
                ready.sort()

    if len(processed) == len(indegree):
        return

    unresolved = set(indegree) - processed
    source_ids = sorted(
        edge.dependency_id
        for edge in schedulable
        if (edge.predecessor_type, edge.predecessor_id) in unresolved
        and (edge.successor_type, edge.successor_id) in unresolved
    )
    raise DeliveryNetworkError(
        "Dependency network contains a cycle supported by source records: "
        f"{', '.join(source_ids)}."
    )
