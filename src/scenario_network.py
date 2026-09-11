"""Deterministic schedule propagation across the delivery dependency network.

The scenario engine previously changed one dependency's ``delay_days`` and re-ran the scoring
engines. Because the Health engine reads *dates* (project baseline versus forecast, milestone
baseline versus forecast), and no date ever moved, delay magnitude could not affect the result: a
one-day slip and a one-year slip produced the same score.

This module supplies the missing causal step. It shifts the forecast dates of the records that a
delay actually reaches, by walking the dependency graph, so the existing graded thresholds in
``src.health_engine`` respond to the size of the delay without any new penalty curve.

Conventions, applied consistently and never mixed:

- **Calendar days.** ``src.health_engine`` grades slip in calendar days, so propagation does too.
- **Durations are preserved.** A delayed activity shifts as a whole. Under that assumption all four
  relationship types move a successor by the same magnitude, so the relationship type governs which
  dates are compared for float, not how much delay travels.
- **Free float is absorbed before delay propagates.** Slack recorded between a predecessor's
  planned finish (plus lag) and a successor's planned start absorbs delay first. Float that cannot
  be evidenced is treated as zero, which propagates the full delay rather than hiding it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final

from src.data_loader import PortfolioData
from src.delivery_rules import (
    SCHEDULABLE_ENDPOINT_TYPES,
    DeliveryNetworkError,
    DependencyEdge,
    DependencyEndpointType,
    ensure_acyclic_dependency_network,
)
from src.wording import count_of

TASK: Final[str] = DependencyEndpointType.TASK.value
MILESTONE: Final[str] = DependencyEndpointType.MILESTONE.value

# A project finishes no earlier than its latest scheduled endpoint. This is the only rule that
# converts endpoint movement into project-level movement, and it introduces no constant.
PROJECT_FINISH_RULE: Final[str] = (
    "Project forecast end date is moved to the latest scenario endpoint date when propagation "
    "pushes an endpoint beyond it; a project cannot finish before its last activity."
)

# The graph node key: endpoint type plus endpoint id.
Node = tuple[str, str]


@dataclass(frozen=True)
class PropagationStep:
    """One evidenced movement of one record, and what controlled it."""

    record_type: str
    record_id: str
    original_date: date
    scenario_date: date
    shift_days: int
    absorbed_float_days: int
    controlling_dependency_id: str | None
    controlling_predecessor_id: str | None
    hop: int

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        ids = [self.record_id]
        if self.controlling_dependency_id:
            ids.append(self.controlling_dependency_id)
        if self.controlling_predecessor_id:
            ids.append(self.controlling_predecessor_id)
        return tuple(ids)


@dataclass
class PropagationResult:
    """Scenario dates, the path that produced them, and what could not be evidenced."""

    task_dates: dict[str, date] = field(default_factory=dict)
    milestone_dates: dict[str, date] = field(default_factory=dict)
    project_dates: dict[str, date] = field(default_factory=dict)
    steps: list[PropagationStep] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @property
    def moved_record_ids(self) -> tuple[str, ...]:
        return tuple(sorted({step.record_id for step in self.steps}))

    def shift_for(self, record_id: str) -> int:
        """Largest evidenced shift applied to one record, or zero when untouched."""
        shifts = [step.shift_days for step in self.steps if step.record_id == record_id]
        return max(shifts) if shifts else 0


def _edges(portfolio: PortfolioData) -> list[DependencyEdge]:
    """Schedulable Task/Milestone edges only; other endpoint types carry no dates here."""
    edges: list[DependencyEdge] = []
    for dependency in portfolio.dependencies:
        try:
            predecessor_type = DependencyEndpointType(dependency.predecessor_type)
            successor_type = DependencyEndpointType(dependency.successor_type)
        except ValueError:
            continue
        if (
            predecessor_type not in SCHEDULABLE_ENDPOINT_TYPES
            or successor_type not in SCHEDULABLE_ENDPOINT_TYPES
        ):
            continue
        edges.append(
            DependencyEdge(
                dependency_id=dependency.dependency_id,
                predecessor_type=predecessor_type,
                predecessor_id=dependency.predecessor_id,
                successor_type=successor_type,
                successor_id=dependency.successor_id,
            )
        )
    return edges


def _lag_days(dependency: object) -> int:
    """Recorded lag, or zero when the legacy record carries no lag evidence."""
    value = getattr(dependency, "lag_days", None)
    return int(value) if isinstance(value, int) else 0


def _planned_finish(portfolio: PortfolioData, node: Node) -> date | None:
    node_type, record_id = node
    if node_type == TASK:
        task = next((item for item in portfolio.tasks if item.task_id == record_id), None)
        return task.planned_end_date if task else None
    milestone = next(
        (item for item in portfolio.milestones if item.milestone_id == record_id), None
    )
    return milestone.baseline_date if milestone else None


def _planned_start(portfolio: PortfolioData, node: Node) -> date | None:
    """A milestone is a zero-duration event, so its date is both its start and its finish."""
    node_type, record_id = node
    if node_type == TASK:
        task = next((item for item in portfolio.tasks if item.task_id == record_id), None)
        return getattr(task, "planned_start_date", None) if task else None
    milestone = next(
        (item for item in portfolio.milestones if item.milestone_id == record_id), None
    )
    return milestone.baseline_date if milestone else None


def _forecast_date(portfolio: PortfolioData, node: Node) -> date | None:
    node_type, record_id = node
    if node_type == TASK:
        task = next((item for item in portfolio.tasks if item.task_id == record_id), None)
        return task.forecast_end_date if task else None
    milestone = next(
        (item for item in portfolio.milestones if item.milestone_id == record_id), None
    )
    return milestone.forecast_date if milestone else None


def free_float_days(
    portfolio: PortfolioData, edge: DependencyEdge, lag_days: int
) -> tuple[int, str | None]:
    """Slack on one edge, and why it could not be evidenced when that is the case.

    Float is the gap between the successor's planned start and the earliest start its predecessor
    permits. Absent evidence yields zero float, which propagates delay rather than concealing it.
    """
    predecessor_finish = _planned_finish(
        portfolio, (edge.predecessor_type.value, edge.predecessor_id)
    )
    successor_start = _planned_start(portfolio, (edge.successor_type.value, edge.successor_id))
    if predecessor_finish is None or successor_start is None:
        return 0, (
            f"Dependency {edge.dependency_id} has no recorded planned dates on both endpoints, "
            "so no float could be evidenced and the full delay was propagated."
        )
    earliest_permitted_start = predecessor_finish + timedelta(days=lag_days)
    return max(0, (successor_start - earliest_permitted_start).days), None


def _topological_order(edges: list[DependencyEdge]) -> list[Node]:
    """Stable predecessor-before-successor order, so no node is settled twice."""
    outgoing: dict[Node, list[Node]] = defaultdict(list)
    indegree: dict[Node, int] = {}
    for edge in edges:
        predecessor = (edge.predecessor_type.value, edge.predecessor_id)
        successor = (edge.successor_type.value, edge.successor_id)
        outgoing[predecessor].append(successor)
        indegree.setdefault(predecessor, 0)
        indegree[successor] = indegree.get(successor, 0) + 1

    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    order: list[Node] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for successor in sorted(outgoing[node]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
                ready.sort()
    return order


def propagate(
    portfolio: PortfolioData,
    seed_shifts: dict[Node, int],
) -> PropagationResult:
    """Move every record a delay actually reaches, and record why each one moved.

    Args:
        portfolio: The scenario copy. Never the caller's baseline.
        seed_shifts: Calendar-day shifts applied directly by the interventions.

    Returns:
        A :class:`PropagationResult` holding scenario dates, evidenced steps and limitations.

    Raises:
        DeliveryNetworkError: When the dependency network contains a cycle.
    """
    edges = _edges(portfolio)
    ensure_acyclic_dependency_network(edges)

    lag_by_dependency = {
        dependency.dependency_id: _lag_days(dependency) for dependency in portfolio.dependencies
    }
    incoming: dict[Node, list[DependencyEdge]] = defaultdict(list)
    for edge in edges:
        incoming[(edge.successor_type.value, edge.successor_id)].append(edge)

    result = PropagationResult()
    shift: dict[Node, int] = {node: days for node, days in seed_shifts.items() if days > 0}
    hop: dict[Node, int] = dict.fromkeys(shift, 0)
    controlling: dict[Node, tuple[str | None, str | None]] = {}
    seen_limitations: set[str] = set()

    for node in _topological_order(edges):
        best_shift = shift.get(node, 0)
        best_source: tuple[str | None, str | None] = controlling.get(node, (None, None))
        best_hop = hop.get(node, 0)
        # Convergence: several predecessors may reach one successor. The latest controlling
        # predecessor wins, and delay is never added twice.
        for edge in sorted(incoming[node], key=lambda item: item.dependency_id):
            predecessor = (edge.predecessor_type.value, edge.predecessor_id)
            inherited = shift.get(predecessor, 0)
            if inherited <= 0:
                continue
            lag = lag_by_dependency.get(edge.dependency_id, 0)
            float_days, limitation = free_float_days(portfolio, edge, lag)
            if limitation and limitation not in seen_limitations:
                seen_limitations.add(limitation)
                result.limitations.append(limitation)
            transmitted = max(0, inherited - float_days)
            if transmitted > best_shift:
                best_shift = transmitted
                best_source = (edge.dependency_id, edge.predecessor_id)
                best_hop = hop.get(predecessor, 0) + 1

        if best_shift <= 0:
            continue
        shift[node] = best_shift
        controlling[node] = best_source
        hop[node] = best_hop

    # Seeded nodes with no incoming edge still need to be recorded.
    for node, days in seed_shifts.items():
        if days > 0 and node not in shift:
            shift[node] = days
            hop[node] = 0
            controlling[node] = (None, None)

    for node in sorted(shift):
        days = shift[node]
        if days <= 0:
            continue
        original = _forecast_date(portfolio, node)
        if original is None:
            result.limitations.append(
                f"{node[0]} {node[1]} has no recorded forecast date, so its movement could not "
                "be calculated."
            )
            continue
        scenario_date = original + timedelta(days=days)
        dependency_id, predecessor_id = controlling.get(node, (None, None))
        result.steps.append(
            PropagationStep(
                record_type=node[0],
                record_id=node[1],
                original_date=original,
                scenario_date=scenario_date,
                shift_days=days,
                absorbed_float_days=0,
                controlling_dependency_id=dependency_id,
                controlling_predecessor_id=predecessor_id,
                hop=hop.get(node, 0),
            )
        )
        if node[0] == TASK:
            result.task_dates[node[1]] = scenario_date
        else:
            result.milestone_dates[node[1]] = scenario_date

    result.steps.sort(key=lambda step: (step.hop, step.record_type, step.record_id))
    _apply_to_portfolio(portfolio, result)
    return result


def _apply_to_portfolio(portfolio: PortfolioData, result: PropagationResult) -> None:
    """Write scenario dates onto the scenario copy, including project finish movement."""
    if result.task_dates:
        portfolio.tasks = [
            (
                task.model_copy(update={"forecast_end_date": result.task_dates[task.task_id]})
                if task.task_id in result.task_dates
                else task
            )
            for task in portfolio.tasks
        ]
    if result.milestone_dates:
        portfolio.milestones = [
            (
                milestone.model_copy(
                    update={"forecast_date": result.milestone_dates[milestone.milestone_id]}
                )
                if milestone.milestone_id in result.milestone_dates
                else milestone
            )
            for milestone in portfolio.milestones
        ]

    latest_by_project: dict[str, date] = {}
    for task in portfolio.tasks:
        if task.task_id in result.task_dates:
            current = latest_by_project.get(task.project_id)
            moved = result.task_dates[task.task_id]
            latest_by_project[task.project_id] = max(current, moved) if current else moved
    for milestone in portfolio.milestones:
        if milestone.milestone_id in result.milestone_dates:
            current = latest_by_project.get(milestone.project_id)
            moved = result.milestone_dates[milestone.milestone_id]
            latest_by_project[milestone.project_id] = max(current, moved) if current else moved

    updated_projects = []
    for project in portfolio.projects:
        latest = latest_by_project.get(project.project_id)
        forecast = project.forecast_end_date
        if latest is not None and forecast is not None and latest > forecast:
            result.project_dates[project.project_id] = latest
            updated_projects.append(project.model_copy(update={"forecast_end_date": latest}))
            continue
        if latest is not None and forecast is None:
            result.limitations.append(
                f"Project {project.project_id} has no forecast end date, so project-level "
                "schedule movement could not be calculated."
            )
        updated_projects.append(project)
    portfolio.projects = updated_projects


def network_is_acyclic(portfolio: PortfolioData) -> tuple[bool, str | None]:
    """Report whether the network can be simulated, without raising."""
    try:
        ensure_acyclic_dependency_network(_edges(portfolio))
    except DeliveryNetworkError as exc:
        return False, str(exc)
    return True, None


def critical_path_data_is_complete(portfolio: PortfolioData) -> tuple[bool, list[str]]:
    """Whether a formal Critical Path Method calculation is supportable.

    CPM needs an activity duration for every node. Tasks record a planned finish but their planned
    start is optional, so duration is frequently underivable. When it is missing this returns
    ``False`` and the caller must not use Critical Path terminology; controlling dependencies and
    downstream exposure are reported instead.
    """
    missing = sorted(
        task.task_id
        for task in portfolio.tasks
        if getattr(task, "planned_start_date", None) is None
    )
    if missing:
        return False, [
            "Critical Path Method is not supported for this data: "
            f"{count_of(len(missing), 'task')} record no planned start date, so activity duration cannot be "
            "derived. Controlling dependencies and downstream exposure are reported instead of "
            "float or a critical path.",
        ]
    return True, []


def downstream_exposure(portfolio: PortfolioData) -> dict[str, int]:
    """How many Task and Milestone records sit downstream of each schedulable node.

    This is reachability through the dependency graph, not float. It ranks what a delay would
    touch without claiming a critical path the data cannot support.
    """
    edges = _edges(portfolio)
    outgoing: dict[Node, list[Node]] = defaultdict(list)
    for edge in edges:
        outgoing[(edge.predecessor_type.value, edge.predecessor_id)].append(
            (edge.successor_type.value, edge.successor_id)
        )

    exposure: dict[str, int] = {}
    for node in sorted({(edge.predecessor_type.value, edge.predecessor_id) for edge in edges}):
        seen: set[Node] = set()
        queue = list(outgoing[node])
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(outgoing[current])
        exposure[node[1]] = len(seen)
    return exposure


def edge_free_float(portfolio: PortfolioData) -> dict[str, int | None]:
    """Recorded slack on each schedulable dependency, or ``None`` when unevidenced."""
    lag_by_dependency = {
        dependency.dependency_id: _lag_days(dependency) for dependency in portfolio.dependencies
    }
    result: dict[str, int | None] = {}
    for edge in _edges(portfolio):
        days, limitation = free_float_days(
            portfolio, edge, lag_by_dependency.get(edge.dependency_id, 0)
        )
        result[edge.dependency_id] = None if limitation else days
    return result
