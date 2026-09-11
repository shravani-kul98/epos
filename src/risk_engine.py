"""Deterministic risk early-warning engine.

Generates specific, individually actionable ``EarlyWarningAlert`` objects from validated
synthetic portfolio data. Alerts are rule-based and evidence-cited; no AI, network, file or
system-clock access is used. Every public function takes an explicit ``as_of_date`` and treats
``PortfolioData`` as read-only.

Rule 8 uses only the existing simple requirement-to-test relationship in ``trace_links.csv``
(``link_type = verified_by``); it is not a full traceability engine.
"""

from __future__ import annotations

import hashlib
from datetime import date

from src import scoring_rules as sr
from src.data_loader import PortfolioData
from src.schemas import (
    Action,
    Dependency,
    EarlyWarningAlert,
    Milestone,
    Project,
    Requirement,
    Resource,
    Risk,
    Severity,
    TestCase,
    TraceLink,
)
from src.utils import days_between, reference_timestamp
from src.validators import DataValidationError, ensure_update_dates_not_future
from src.wording import count_of

_PRIORITY = sr.StatusDomain.PRIORITY
_SCHEDULE = sr.StatusDomain.SCHEDULE
_ACTION = sr.StatusDomain.ACTION
_DEPENDENCY = sr.StatusDomain.DEPENDENCY
_REQUIREMENT = sr.StatusDomain.REQUIREMENT
_TEST_CASE = sr.StatusDomain.TEST_CASE

# Alert type identifiers (stable; used in alert_id and for grouping).
ALERT_UNOWNED_RISK = "unowned_high_exposure_risk"
ALERT_MILESTONE_SLIP = "critical_milestone_slip"
ALERT_MILESTONE_DEPENDENCY = "milestone_delayed_dependency"
ALERT_BLOCKED_TASK = "blocked_task_critical_milestone"
ALERT_OVERDUE_ACTION = "overdue_high_priority_action"
ALERT_RESOURCE_OVERALLOCATION = "resource_over_allocation"
ALERT_STALE_STATUS = "stale_project_status"
ALERT_REQUIREMENT_VERIFICATION = "requirement_missing_verification"


def _make_alert(
    alert_type: str,
    project_id: str,
    severity: Severity,
    title: str,
    explanation: str,
    source_ids: list[str],
    recommended_next_step: str,
    as_of_date: date,
) -> EarlyWarningAlert:
    """Build an alert with a deterministic, stable id derived from type and source ids."""
    sorted_ids = sorted(set(source_ids))
    payload = alert_type + "|" + "|".join(sorted_ids)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return EarlyWarningAlert(
        alert_id=f"{alert_type}-{digest}",
        project_id=project_id,
        severity=severity,
        alert_type=alert_type,
        title=title,
        explanation=explanation,
        source_ids=sorted_ids,
        recommended_next_step=recommended_next_step,
        as_of_date=as_of_date,
        detected_at=reference_timestamp(as_of_date),
    )


def _rule_unowned_high_exposure_risk(
    project_id: str, risks: list[Risk], as_of_date: date
) -> list[EarlyWarningAlert]:
    alerts: list[EarlyWarningAlert] = []
    for risk in risks:
        if not sr.is_active_risk_status(risk.status):
            continue
        exposure = risk.probability * risk.impact
        if exposure < sr.ALERT_UNOWNED_RISK_EXPOSURE_MIN:
            continue
        if risk.mitigation_owner is not None:
            continue
        severity: Severity = "Critical" if risk.impact == 5 else "High"
        alerts.append(
            _make_alert(
                ALERT_UNOWNED_RISK,
                project_id,
                severity,
                "High-exposure risk has no mitigation owner",
                f"Risk {risk.risk_id} has probability {risk.probability} and impact "
                f"{risk.impact} (exposure {exposure}/25) but has no mitigation owner.",
                [risk.risk_id],
                "Assign a mitigation owner and confirm a dated mitigation plan.",
                as_of_date,
            )
        )
    return alerts


def _rule_critical_milestone_slip(
    project_id: str, milestones: list[Milestone], as_of_date: date
) -> list[EarlyWarningAlert]:
    alerts: list[EarlyWarningAlert] = []
    for milestone in milestones:
        criticality = sr.normalize_status(milestone.criticality, _PRIORITY)
        if criticality not in ("High", "Critical"):
            continue
        if milestone.baseline_date is None or milestone.forecast_date is None:
            continue
        slip = days_between(milestone.baseline_date, milestone.forecast_date)
        if slip <= 0:
            continue
        large = slip > sr.ALERT_MILESTONE_SLIP_LARGE_DAYS
        if criticality == "Critical":
            severity: Severity = "Critical" if large else "High"
        else:
            severity = "High" if large else "Medium"
        alerts.append(
            _make_alert(
                ALERT_MILESTONE_SLIP,
                project_id,
                severity,
                "Critical milestone forecast slip",
                f"Milestone {milestone.milestone_id} is forecast {slip} calendar days later "
                "than baseline.",
                [milestone.milestone_id],
                "Review the recovery plan, confirm affected dependencies and update the "
                "forecast owner.",
                as_of_date,
            )
        )
    return alerts


def _linked_milestone_ids(dependency: Dependency) -> list[str]:
    """Return milestone ids referenced by either end of a dependency."""
    linked: list[str] = []
    if dependency.predecessor_type == "Milestone":
        linked.append(dependency.predecessor_id)
    if dependency.successor_type == "Milestone":
        linked.append(dependency.successor_id)
    return linked


def _rule_milestone_delayed_dependency(
    project_id: str,
    dependencies: list[Dependency],
    milestone_criticality: dict[str, str],
    as_of_date: date,
) -> list[EarlyWarningAlert]:
    alerts: list[EarlyWarningAlert] = []
    for dependency in dependencies:
        status = sr.normalize_status(dependency.status, _DEPENDENCY)
        is_delayed = status in ("Delayed", "Blocked") or dependency.delay_days > 0
        if not is_delayed:
            continue
        for milestone_id in _linked_milestone_ids(dependency):
            criticality = milestone_criticality.get(milestone_id)
            if criticality not in ("High", "Critical"):
                continue
            blocked = status == "Blocked"
            large_delay = dependency.delay_days > sr.ALERT_DEPENDENCY_LARGE_DELAY_DAYS
            severity: Severity = (
                "Critical" if criticality == "Critical" and (blocked or large_delay) else "High"
            )
            dependency_state = (
                f"is Blocked with {count_of(dependency.delay_days, 'day')} of recorded delay"
                if blocked
                else f"is delayed by {count_of(dependency.delay_days, 'day')}"
            )
            alerts.append(
                _make_alert(
                    ALERT_MILESTONE_DEPENDENCY,
                    project_id,
                    severity,
                    "Critical milestone has delayed dependency",
                    f"Dependency {dependency.dependency_id} {dependency_state} and affects "
                    f"{milestone_id}, a "
                    f"{criticality} milestone.",
                    [dependency.dependency_id, milestone_id],
                    "Escalate the dependency owner and assess milestone recovery options.",
                    as_of_date,
                )
            )
    return alerts


def _rule_blocked_task_critical_milestone(
    project_id: str,
    tasks: list,
    milestone_criticality: dict[str, str],
    as_of_date: date,
) -> list[EarlyWarningAlert]:
    alerts: list[EarlyWarningAlert] = []
    for task in tasks:
        if sr.is_terminal_schedule_status(task.status):
            continue
        blocked = task.is_blocked or sr.normalize_status(task.status, _SCHEDULE) == "Blocked"
        if not blocked:
            continue
        criticality = milestone_criticality.get(task.milestone_id)
        if criticality not in ("High", "Critical"):
            continue
        severity: Severity = "Critical" if criticality == "Critical" else "High"
        alerts.append(
            _make_alert(
                ALERT_BLOCKED_TASK,
                project_id,
                severity,
                "Blocked task threatens critical milestone",
                f"Task {task.task_id} is blocked and is linked to {task.milestone_id}, a "
                f"{criticality} milestone.",
                [task.task_id, task.milestone_id],
                "Resolve the blocker or agree a mitigation/escalation path with the task owner.",
                as_of_date,
            )
        )
    return alerts


def _rule_overdue_high_priority_action(
    project_id: str, actions: list[Action], as_of_date: date
) -> list[EarlyWarningAlert]:
    alerts: list[EarlyWarningAlert] = []
    for action in actions:
        if sr.normalize_status(action.status, _ACTION) in sr.TERMINAL_ACTION_STATUSES:
            continue
        priority = sr.normalize_status(action.priority, _PRIORITY)
        if priority not in ("High", "Critical"):
            continue
        if action.due_date >= as_of_date:
            continue
        days_overdue = days_between(action.due_date, as_of_date)
        large = days_overdue > sr.ALERT_ACTION_OVERDUE_LARGE_DAYS
        if priority == "Critical":
            severity: Severity = "Critical" if large else "High"
        else:
            severity = "High" if large else "Medium"
        alerts.append(
            _make_alert(
                ALERT_OVERDUE_ACTION,
                project_id,
                severity,
                "High-priority action is overdue",
                f"Action {action.action_id} is {days_overdue} calendar days overdue and has "
                f"{priority} priority.",
                [action.action_id],
                "Confirm ownership, revised due date and the impact of non-completion.",
                as_of_date,
            )
        )
    return alerts


def _rule_resource_over_allocation(
    project_id: str, resources: list[Resource], as_of_date: date
) -> list[EarlyWarningAlert]:
    alerts: list[EarlyWarningAlert] = []
    for resource in resources:
        if resource.allocated_hours <= resource.capacity_hours:
            continue
        utilisation = resource.allocated_hours * 100 / resource.capacity_hours
        if utilisation > sr.ALERT_RESOURCE_UTIL_CRITICAL:
            severity: Severity = "Critical"
        elif utilisation > sr.ALERT_RESOURCE_UTIL_HIGH:
            severity = "High"
        else:
            severity = "Medium"
        alerts.append(
            _make_alert(
                ALERT_RESOURCE_OVERALLOCATION,
                project_id,
                severity,
                "Resource capacity exceeded",
                f"Resource {resource.resource_id} is allocated {resource.allocated_hours} hours "
                f"against {resource.capacity_hours} available hours ({utilisation:.1f}% "
                "utilisation).",
                [resource.resource_id],
                "Rebalance work, adjust capacity or escalate the staffing constraint.",
                as_of_date,
            )
        )
    return alerts


def _rule_stale_project_status(project: Project, as_of_date: date) -> list[EarlyWarningAlert]:
    updated = project.status_update_date
    ensure_update_dates_not_future([(project.project_id, updated)], as_of_date)
    if updated is None:
        return [
            _make_alert(
                ALERT_STALE_STATUS,
                project.project_id,
                "Critical",
                "Project status is stale",
                f"Project {project.project_id} has no recorded status update date.",
                [project.project_id],
                "Request a project-status update and verify milestone/risk information.",
                as_of_date,
            )
        ]
    age = days_between(updated, as_of_date)
    if age <= sr.ALERT_STALE_STATUS_TRIGGER_DAYS:
        return []
    severity: Severity = "High" if age > sr.ALERT_STALE_STATUS_SIGNIFICANT_DAYS else "Medium"
    return [
        _make_alert(
            ALERT_STALE_STATUS,
            project.project_id,
            severity,
            "Project status is stale",
            f"Project {project.project_id} status was last updated {age} calendar days ago.",
            [project.project_id],
            "Request a project-status update and verify milestone/risk information.",
            as_of_date,
        )
    ]


def _rule_requirement_missing_verification(
    project_id: str,
    requirements: list[Requirement],
    test_cases: list[TestCase],
    trace_links: list[TraceLink],
    as_of_date: date,
) -> list[EarlyWarningAlert]:
    test_case_by_id = {tc.test_case_id: tc for tc in test_cases}
    alerts: list[EarlyWarningAlert] = []
    for requirement in requirements:
        priority = sr.normalize_status(requirement.priority, _PRIORITY)
        if priority not in ("High", "Critical"):
            continue
        if (
            sr.normalize_status(requirement.status, _REQUIREMENT)
            not in sr.ACTIVE_REQUIREMENT_STATUSES
        ):
            continue

        verification_links = [
            link
            for link in trace_links
            if link.link_type == "verified_by"
            and link.source_type == "Requirement"
            and link.source_id == requirement.requirement_id
            and link.target_type == "TestCase"
            and link.target_id in test_case_by_id
        ]
        linked_tests = [test_case_by_id[link.target_id] for link in verification_links]

        if not linked_tests:
            severity: Severity = "Critical" if priority == "Critical" else "High"
            source_ids = [requirement.requirement_id]
        else:
            verified = any(
                sr.normalize_status(tc.status, _TEST_CASE) == "Passed"
                and tc.has_verification_evidence
                for tc in linked_tests
            )
            if verified:
                continue
            source_ids = (
                [requirement.requirement_id]
                + [tc.test_case_id for tc in linked_tests]
                + [link.trace_link_id for link in verification_links]
            )
            if any(sr.normalize_status(tc.status, _TEST_CASE) == "Not Run" for tc in linked_tests):
                severity = "Medium"
            else:
                severity = "Critical" if priority == "Critical" else "High"

        alerts.append(
            _make_alert(
                ALERT_REQUIREMENT_VERIFICATION,
                project_id,
                severity,
                "High-priority requirement lacks verification evidence",
                f"Requirement {requirement.requirement_id} is {priority} priority and lacks "
                "complete verification evidence.",
                source_ids,
                "Assign verification ownership and confirm the test/evidence plan before release.",
                as_of_date,
            )
        )
    return alerts


def _collect_project_alerts(
    project: Project, portfolio: PortfolioData, as_of_date: date
) -> list[EarlyWarningAlert]:
    """Run every rule for one project and return its alerts (unsorted, may include duplicates)."""
    project_id = project.project_id
    milestones = [m for m in portfolio.milestones if m.project_id == project_id]
    tasks = [t for t in portfolio.tasks if t.project_id == project_id]
    risks = [r for r in portfolio.risks if r.project_id == project_id]
    dependencies = [d for d in portfolio.dependencies if d.project_id == project_id]
    resources = [r for r in portfolio.resources if r.project_id == project_id]
    actions = [a for a in portfolio.actions if a.project_id == project_id]
    requirements = [r for r in portfolio.requirements if r.project_id == project_id]
    test_cases = [t for t in portfolio.test_cases if t.project_id == project_id]
    trace_links = [t for t in portfolio.trace_links if t.project_id == project_id]

    milestone_criticality = {
        m.milestone_id: (sr.normalize_status(m.criticality, _PRIORITY) or "Medium")
        for m in milestones
    }

    alerts: list[EarlyWarningAlert] = []
    alerts += _rule_unowned_high_exposure_risk(project_id, risks, as_of_date)
    alerts += _rule_critical_milestone_slip(project_id, milestones, as_of_date)
    alerts += _rule_milestone_delayed_dependency(
        project_id, dependencies, milestone_criticality, as_of_date
    )
    alerts += _rule_blocked_task_critical_milestone(
        project_id, tasks, milestone_criticality, as_of_date
    )
    alerts += _rule_overdue_high_priority_action(project_id, actions, as_of_date)
    alerts += _rule_resource_over_allocation(project_id, resources, as_of_date)
    alerts += _rule_stale_project_status(project, as_of_date)
    alerts += _rule_requirement_missing_verification(
        project_id, requirements, test_cases, trace_links, as_of_date
    )
    return alerts


def _finalise(alerts: list[EarlyWarningAlert]) -> list[EarlyWarningAlert]:
    """Deduplicate by alert_id and apply the stable output ordering."""
    unique: dict[str, EarlyWarningAlert] = {}
    for alert in alerts:
        unique.setdefault(alert.alert_id, alert)
    return sorted(
        unique.values(),
        key=lambda a: (
            -sr.SEVERITY_ORDER[a.severity],
            a.project_id,
            a.alert_type,
            a.alert_id,
        ),
    )


def generate_early_warnings(
    project_id: str, portfolio: PortfolioData, as_of_date: date
) -> list[EarlyWarningAlert]:
    """Return the deterministic early-warning alerts for a single project.

    Raises:
        DataValidationError: If ``project_id`` is not present in the portfolio.
    """
    project = portfolio.get_project(project_id)
    if project is None:
        raise DataValidationError([f"unknown project_id '{project_id}'"])
    return _finalise(_collect_project_alerts(project, portfolio, as_of_date))


def generate_portfolio_early_warnings(
    portfolio: PortfolioData, as_of_date: date
) -> list[EarlyWarningAlert]:
    """Return early-warning alerts across all projects using the same stable ordering."""
    alerts: list[EarlyWarningAlert] = []
    for project in portfolio.projects:
        alerts += _collect_project_alerts(project, portfolio, as_of_date)
    return _finalise(alerts)
