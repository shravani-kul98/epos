"""Deterministic change-impact analysis.

Traverses a change request to the artefacts it affects, using only relationships that exist in the
Version 1 data model: ``change_request -> requirement -> trace_links -> tasks / test cases /
milestones``, then ``dependencies`` referencing those tasks, then each affected task's own
milestone. Every returned ID is a real record from the loaded portfolio.

The schedule estimate and risk level come from lookup rules centralised in ``src.scoring_rules``.
No AI, network, file or system-clock access is used; ``PortfolioData`` is read-only.
See ``docs/change-impact-methodology.md``.
"""

from __future__ import annotations

from datetime import date

from src import scoring_rules as sr
from src.data_loader import PortfolioData
from src.schemas import ChangeImpactResult, ChangeRequest, Severity
from src.utils import reference_timestamp
from src.validators import DataValidationError
from src.wording import count_of

_PRIORITY = sr.StatusDomain.PRIORITY

# Highest-first ordering used when picking the driving milestone criticality.
_CRITICALITY_RANK = {name: rank for rank, name in enumerate(sr.CRITICALITY_LEVELS)}


def list_change_requests_for_project(
    project_id: str, portfolio: PortfolioData
) -> list[ChangeRequest]:
    """Return the project's change requests, ordered by id."""
    return sorted(
        (c for c in portfolio.change_requests if c.project_id == project_id),
        key=lambda c: c.change_request_id,
    )


def _highest_criticality(criticalities: list[str]) -> str | None:
    """Return the most severe criticality present, or None when there are none."""
    if not criticalities:
        return None
    return max(criticalities, key=lambda name: _CRITICALITY_RANK[name])


def _estimate_schedule_days(milestone_criticality: str | None, priority: str) -> int:
    """Look up the coarse Version 1 schedule estimate in calendar days."""
    if milestone_criticality is None:
        return sr.CHANGE_IMPACT_NO_MILESTONE_DAYS
    return sr.CHANGE_IMPACT_SCHEDULE_DAYS[(milestone_criticality, priority)]


def _risk_level(milestone_criticality: str | None, priority: str, artefact_count: int) -> Severity:
    """Assign the change risk level from milestone criticality, priority and impact breadth."""
    if artefact_count == 0:
        return "Low"
    if milestone_criticality == "Critical" and priority in ("High", "Critical"):
        return "Critical"
    if milestone_criticality in ("Critical", "High"):
        return "High"
    if artefact_count >= sr.CHANGE_IMPACT_BREADTH_THRESHOLD:
        return "High"
    return "Medium"


def calculate_change_impact(
    change_request_id: str, portfolio: PortfolioData, as_of_date: date
) -> ChangeImpactResult:
    """Analyse the deterministic impact of one change request.

    Args:
        change_request_id: The change request to analyse.
        portfolio: Validated, read-only portfolio data.
        as_of_date: Calculation reference date.

    Returns:
        A fully populated :class:`ChangeImpactResult`.

    Raises:
        DataValidationError: If the change request or its requirement does not exist.
    """
    change_request = next(
        (c for c in portfolio.change_requests if c.change_request_id == change_request_id), None
    )
    if change_request is None:
        raise DataValidationError([f"unknown change_request_id '{change_request_id}'"])

    project_id = change_request.project_id
    requirement = next(
        (
            r
            for r in portfolio.requirements
            if r.requirement_id == change_request.requirement_id and r.project_id == project_id
        ),
        None,
    )
    if requirement is None:
        raise DataValidationError(
            [
                f"change request '{change_request_id}' references unknown requirement "
                f"'{change_request.requirement_id}'"
            ]
        )

    tasks = {t.task_id: t for t in portfolio.tasks if t.project_id == project_id}
    test_case_ids = {t.test_case_id for t in portfolio.test_cases if t.project_id == project_id}
    milestones = {m.milestone_id: m for m in portfolio.milestones if m.project_id == project_id}
    dependencies = [d for d in portfolio.dependencies if d.project_id == project_id]

    affected_tasks: set[str] = set()
    affected_tests: set[str] = set()
    affected_milestones: set[str] = set()
    affected_dependencies: set[str] = set()
    affected_trace_links: set[str] = set()

    # Direct trace links from the changed requirement.
    for link in portfolio.trace_links:
        if link.project_id != project_id:
            continue
        if link.source_type != "Requirement" or link.source_id != requirement.requirement_id:
            continue
        expected_target = sr.CHANGE_IMPACT_LINK_TARGETS.get(link.link_type)
        if expected_target is None or link.target_type != expected_target:
            continue
        if expected_target == "Task" and link.target_id in tasks:
            affected_tasks.add(link.target_id)
            affected_trace_links.add(link.trace_link_id)
        elif expected_target == "TestCase" and link.target_id in test_case_ids:
            affected_tests.add(link.target_id)
            affected_trace_links.add(link.trace_link_id)
        elif expected_target == "Milestone" and link.target_id in milestones:
            affected_milestones.add(link.target_id)
            affected_trace_links.add(link.trace_link_id)

    # Dependencies that reference an affected task, plus the artefact at the other end.
    directly_affected_tasks = affected_tasks.copy()
    for dependency in dependencies:
        ends = (
            (dependency.predecessor_type, dependency.predecessor_id),
            (dependency.successor_type, dependency.successor_id),
        )
        if not any(kind == "Task" and ref in directly_affected_tasks for kind, ref in ends):
            continue
        affected_dependencies.add(dependency.dependency_id)
        for kind, ref in ends:
            if kind == "Task" and ref in tasks:
                affected_tasks.add(ref)
            elif kind == "Milestone" and ref in milestones:
                affected_milestones.add(ref)

    # Each affected task also implicates its own milestone.
    for task_id in list(affected_tasks):
        milestone_id = tasks[task_id].milestone_id
        if milestone_id in milestones:
            affected_milestones.add(milestone_id)

    priority = sr.normalize_status(change_request.priority, _PRIORITY) or "Medium"
    criticalities = [
        sr.normalize_status(milestones[mid].criticality, _PRIORITY) or "Medium"
        for mid in affected_milestones
    ]
    driving_criticality = _highest_criticality(criticalities)
    artefact_count = (
        len(affected_tasks)
        + len(affected_tests)
        + len(affected_milestones)
        + len(affected_dependencies)
    )
    estimated_days = _estimate_schedule_days(driving_criticality, priority)
    risk_level = _risk_level(driving_criticality, priority, artefact_count)

    limitations = [
        "The schedule estimate is a rule of thumb from milestone criticality and change "
        "priority, not a forecast.",
        "It follows the requirement's links to tasks and tests, the milestones those tasks "
        "belong to and the dependencies on them; knock-on effects between milestones are not "
        "followed.",
        "Release gates are counted as milestones.",
    ]

    if artefact_count == 0:
        explanation = (
            f"Change request {change_request_id} ({priority} priority) affects requirement "
            f"{requirement.requirement_id}, which has no trace links to tasks, test cases or "
            "milestones in the loaded data; no downstream artefacts were found. Impact cannot be "
            "assessed until the requirement is traced."
        )
        limitations.append(
            "No downstream artefacts were found; this may indicate incomplete trace-link data "
            "rather than a genuinely low-impact change."
        )
    else:
        explanation = (
            f"Change request {change_request_id} ({priority} priority) affects requirement "
            f"{requirement.requirement_id}, which traces to "
            f"{count_of(len(affected_tasks), 'task')}, "
            f"{count_of(len(affected_tests), 'test case')}, "
            f"{count_of(len(affected_milestones), 'milestone')} and "
            f"{count_of(len(affected_dependencies), 'dependency', 'dependencies')}. The most "
            f"critical affected milestone is {driving_criticality} criticality, giving an "
            f"estimated schedule impact of {count_of(estimated_days, 'calendar day')} and a "
            f"{risk_level} change risk level."
        )

    source_ids = sorted(
        {change_request_id, requirement.requirement_id}
        | affected_tasks
        | affected_tests
        | affected_milestones
        | affected_dependencies
        | affected_trace_links
    )

    return ChangeImpactResult(
        change_request_id=change_request_id,
        requirement_id=requirement.requirement_id,
        affected_task_ids=sorted(affected_tasks),
        affected_test_case_ids=sorted(affected_tests),
        affected_dependency_ids=sorted(affected_dependencies),
        affected_milestone_ids=sorted(affected_milestones),
        estimated_schedule_impact_days=estimated_days,
        risk_level=risk_level,
        deterministic_explanation=explanation,
        source_ids=source_ids,
        as_of_date=as_of_date,
        calculated_at=reference_timestamp(as_of_date),
        assumptions_or_limitations=limitations,
        evidence_status="Insufficient evidence" if artefact_count == 0 else "Assessed",
    )
