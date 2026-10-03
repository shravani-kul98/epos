"""Deterministic engineering delivery-network contracts."""

from __future__ import annotations

import pytest

from src.delivery_rules import (
    DeliveryHierarchyError,
    DeliveryNetworkError,
    DependencyEdge,
    DependencyEndpointType,
    DependencyRelationshipType,
    TaskHierarchyNode,
    ensure_acyclic_dependency_network,
    ensure_dependency_metadata,
    ensure_valid_task_hierarchy,
)


def _edge(
    dependency_id: str,
    predecessor_id: str,
    successor_id: str,
    predecessor_type: DependencyEndpointType = DependencyEndpointType.TASK,
    successor_type: DependencyEndpointType = DependencyEndpointType.TASK,
) -> DependencyEdge:
    return DependencyEdge(
        dependency_id=dependency_id,
        predecessor_type=predecessor_type,
        predecessor_id=predecessor_id,
        successor_type=successor_type,
        successor_id=successor_id,
    )


def _task(
    task_id: str,
    parent_task_id: str | None = None,
    project_id: str = "P-1",
    deliverable_id: str | None = None,
) -> TaskHierarchyNode:
    return TaskHierarchyNode(
        task_id=task_id,
        project_id=project_id,
        parent_task_id=parent_task_id,
        deliverable_id=deliverable_id,
    )


def test_task_hierarchy_accepts_roots_and_nested_tasks() -> None:
    ensure_valid_task_hierarchy([_task("T-1"), _task("T-2", "T-1"), _task("T-3", "T-2")])


def test_task_hierarchy_rejects_a_missing_parent_with_source_ids() -> None:
    with pytest.raises(DeliveryHierarchyError, match="T-2.*T-MISSING"):
        ensure_valid_task_hierarchy([_task("T-1"), _task("T-2", "T-MISSING")])


def test_task_hierarchy_rejects_a_cross_project_parent_with_source_ids() -> None:
    with pytest.raises(DeliveryHierarchyError, match="T-2.*T-1"):
        ensure_valid_task_hierarchy([_task("T-1", project_id="P-1"), _task("T-2", "T-1", "P-2")])


def test_task_hierarchy_rejects_a_cross_deliverable_parent_with_source_ids() -> None:
    with pytest.raises(DeliveryHierarchyError, match="T-2.*T-1.*Deliverables"):
        ensure_valid_task_hierarchy(
            [
                _task("T-1", deliverable_id="DEL-1"),
                _task("T-2", "T-1", deliverable_id="DEL-2"),
            ]
        )


def test_task_hierarchy_cycle_identifies_every_supporting_task() -> None:
    with pytest.raises(DeliveryHierarchyError, match="T-1, T-2, T-3"):
        ensure_valid_task_hierarchy([_task("T-1", "T-3"), _task("T-2", "T-1"), _task("T-3", "T-2")])


def test_dependency_chain_is_acyclic() -> None:
    ensure_acyclic_dependency_network(
        [
            _edge("D-1", "T-1", "T-2"),
            _edge(
                "D-2",
                "T-2",
                "M-1",
                successor_type=DependencyEndpointType.MILESTONE,
            ),
        ]
    )


def test_external_predecessor_does_not_create_a_schedulable_cycle() -> None:
    ensure_acyclic_dependency_network(
        [
            _edge("D-1", "T-1", "T-2"),
            _edge(
                "D-2",
                "SUP-1",
                "T-1",
                predecessor_type=DependencyEndpointType.SUPPLIER,
            ),
        ]
    )


def test_cycle_error_identifies_every_supporting_dependency() -> None:
    with pytest.raises(DeliveryNetworkError, match="D-1, D-2"):
        ensure_acyclic_dependency_network([_edge("D-1", "T-1", "T-2"), _edge("D-2", "T-2", "T-1")])


def test_duplicate_edge_error_identifies_both_source_records() -> None:
    with pytest.raises(DeliveryNetworkError, match="D-1 and D-2"):
        ensure_acyclic_dependency_network([_edge("D-1", "T-1", "T-2"), _edge("D-2", "T-1", "T-2")])


def test_relationship_type_and_lag_are_recorded_together() -> None:
    edge = _edge("D-1", "T-1", "T-2")
    with pytest.raises(DeliveryNetworkError, match="D-1"):
        ensure_dependency_metadata(
            edge,
            DependencyRelationshipType.FINISH_TO_START,
            None,
            require_complete=True,
        )


def test_new_schedulable_dependency_requires_complete_metadata() -> None:
    with pytest.raises(DeliveryNetworkError, match="D-1"):
        ensure_dependency_metadata(
            _edge("D-1", "T-1", "T-2"),
            None,
            None,
            require_complete=True,
        )


def test_legacy_incomplete_dependency_can_still_be_read() -> None:
    ensure_dependency_metadata(
        _edge("D-1", "T-1", "T-2"),
        None,
        None,
        require_complete=False,
    )
