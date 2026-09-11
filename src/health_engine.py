"""Deterministic Project Health Score engine.

Calculates an explainable 0-100 Health score from validated synthetic portfolio data. All
weights, penalties and thresholds come from ``src.scoring_rules`` (no duplicated constants).
The engine reads ``PortfolioData`` as read-only, uses a caller-supplied ``as_of_date`` for all
time-relative logic, and performs no AI, network or file access.

Policy notes:
- Schedule variance uses calendar days in Version 1.
- ``Open`` and ``Mitigating`` risks incur exposure penalties; ``Closed`` and ``Accepted`` risks
    are excluded from delivery penalties.
- Optional-table fallbacks (dependencies, resources, actions) apply only when the dataset
  contains no records of that type at all; a project that legitimately has none scores 100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src import scoring_rules as sr
from src.data_loader import PortfolioData
from src.schemas import (
    Action,
    CriticalDriver,
    Dependency,
    HealthResult,
    Milestone,
    Project,
    Resource,
    Risk,
    Severity,
    Task,
)
from src.utils import clamp, days_between, health_band, reference_timestamp
from src.validators import DataValidationError
from src.wording import count_of

_PRIORITY = sr.StatusDomain.PRIORITY
_SCHEDULE = sr.StatusDomain.SCHEDULE
_RISK = sr.StatusDomain.RISK
_MITIGATION = sr.StatusDomain.MITIGATION
_ACTION = sr.StatusDomain.ACTION
_DEPENDENCY = sr.StatusDomain.DEPENDENCY


@dataclass
class _FactorOutcome:
    """The deterministic result of a single health factor."""

    score: float
    explanations: list[str]
    source_ids: list[str] = field(default_factory=list)
    drivers: list[CriticalDriver] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def _driver(
    factor: str,
    severity: Severity,
    message: str,
    source_ids: list[str],
    impact: str,
) -> CriticalDriver:
    """Build a structured critical driver with sorted, unique source IDs."""
    return CriticalDriver(
        factor_name=factor,
        severity=severity,
        message=message,
        source_ids=sorted(set(source_ids)),
        score_impact_description=impact,
    )


def _priority_or_default(raw: str | None) -> str:
    """Return canonical priority/criticality, defaulting unrecognised values to Medium."""
    return sr.normalize_status(raw, _PRIORITY) or "Medium"


def _schedule_score(slip_days: int) -> int:
    """Map a calendar-day slip to a schedule performance score."""
    for max_slip, score in sr.SCHEDULE_SLIP_THRESHOLDS:
        if slip_days <= max_slip:
            return score
    return sr.SCHEDULE_SLIP_BEYOND_SCORE


def _schedule_performance(project: Project) -> _FactorOutcome:
    baseline = project.baseline_end_date
    forecast = project.forecast_end_date
    if baseline is None or forecast is None:
        if baseline is None and forecast is None:
            missing = "baseline and forecast end dates"
        elif baseline is None:
            missing = "baseline end date"
        else:
            missing = "forecast end date"
        message = (
            f"Project {project.project_id} is missing its {missing}; "
            "schedule performance cannot be fully assessed."
        )
        return _FactorOutcome(
            score=sr.SCHEDULE_MISSING_FALLBACK,
            explanations=[message],
            source_ids=[project.project_id],
            limitations=[message],
        )

    slip = days_between(baseline, forecast)
    score = _schedule_score(slip)
    if slip <= 0:
        return _FactorOutcome(
            score=score,
            explanations=[
                f"Project {project.project_id} forecast end date is on or before its "
                f"baseline end date; schedule performance is {score}."
            ],
        )

    outcome = _FactorOutcome(
        score=score,
        explanations=[
            f"Project {project.project_id} forecast end date is {_calendar_days(slip)} "
            f"later than its baseline end date; schedule performance is {score}."
        ],
        source_ids=[project.project_id],
    )
    if slip > sr.ALERT_MILESTONE_SLIP_LARGE_DAYS:
        severity: Severity = "Critical" if slip > 20 else "High"
        outcome.drivers.append(
            _driver(
                "schedule_performance",
                severity,
                f"Project {project.project_id} forecast end date is {slip} calendar days "
                "later than baseline.",
                [project.project_id],
                f"Schedule performance factor scored {score}/100.",
            )
        )
    return outcome


def _milestone_readiness(milestones: list[Milestone]) -> _FactorOutcome:
    if not milestones:
        message = "No milestones are available; milestone readiness cannot be fully assessed."
        return _FactorOutcome(
            score=sr.MILESTONE_NONE_FALLBACK,
            explanations=[message],
            limitations=[message],
        )

    active = [m for m in milestones if not sr.is_terminal_schedule_status(m.status)]
    score = float(sr.FACTOR_BASE_SCORE)
    explanations: list[str] = []
    source_ids: list[str] = []
    drivers: list[CriticalDriver] = []
    limitations: list[str] = []

    for milestone in active:
        penalty = 0
        reasons: list[str] = []
        criticality = sr.normalize_status(milestone.criticality, _PRIORITY)
        if criticality is None:
            criticality = "Medium"
            limitations.append(
                f"Milestone {milestone.milestone_id} has unrecognised criticality "
                f"'{milestone.criticality}'; treated as Medium."
            )

        slip: int | None = None
        if milestone.baseline_date is not None and milestone.forecast_date is not None:
            slip = days_between(milestone.baseline_date, milestone.forecast_date)
            if slip > 0:
                slip_penalty = sr.MILESTONE_SLIP_PENALTY[criticality]
                penalty += slip_penalty
                reasons.append(
                    f"is forecast {_calendar_days(slip)} later than baseline "
                    f"(-{slip_penalty} for {criticality} criticality)"
                )
        else:
            limitations.append(
                f"Milestone {milestone.milestone_id} is missing a baseline or forecast date; "
                "slip could not be assessed."
            )

        status = sr.normalize_status(milestone.status, _SCHEDULE)
        if status in sr.MILESTONE_STATUS_PENALTY:
            status_penalty = sr.MILESTONE_STATUS_PENALTY[status]
            penalty += status_penalty
            reasons.append(f"is marked {status} (-{status_penalty})")

        if penalty > 0:
            score -= penalty
            source_ids.append(milestone.milestone_id)
            explanations.append(
                f"Milestone {milestone.milestone_id} ({milestone.milestone_name}) is "
                f"{criticality} and " + ", ".join(reasons) + "."
            )
            material = criticality in ("High", "Critical") and (
                (slip is not None and slip > 0) or status in ("Delayed", "Blocked")
            )
            if material:
                severity: Severity = "Critical" if criticality == "Critical" else "High"
                drivers.append(
                    _driver(
                        "milestone_readiness",
                        severity,
                        f"Milestone {milestone.milestone_id} ({milestone.milestone_name}) is a "
                        f"{criticality} milestone and " + " and ".join(reasons) + ".",
                        [milestone.milestone_id],
                        f"Reduced milestone readiness by {penalty} points.",
                    )
                )

    score = clamp(score)
    if not explanations:
        explanations.append(
            f"{_all_of(len(active), 'active milestone')} on track; milestone readiness is {score}."
        )
    return _FactorOutcome(score, explanations, source_ids, drivers, limitations)


def _task_execution(
    tasks: list[Task], milestone_criticality: dict[str, str], as_of_date: date
) -> _FactorOutcome:
    if not tasks:
        message = "No tasks are available; task execution cannot be fully assessed."
        return _FactorOutcome(
            score=sr.TASK_NONE_FALLBACK, explanations=[message], limitations=[message]
        )

    active = [t for t in tasks if not sr.is_terminal_schedule_status(t.status)]
    score = float(sr.FACTOR_BASE_SCORE)
    explanations: list[str] = []
    source_ids: list[str] = []
    drivers: list[CriticalDriver] = []
    limitations: list[str] = []

    for task in active:
        penalty = 0
        reasons: list[str] = []
        criticality = milestone_criticality.get(task.milestone_id)
        if criticality is None:
            high_or_critical = False
            limitations.append(
                f"Task {task.task_id} references milestone {task.milestone_id} which is not "
                "available; treated as non-critical."
            )
        else:
            high_or_critical = criticality in ("High", "Critical")

        blocked = task.is_blocked or sr.normalize_status(task.status, _SCHEDULE) == "Blocked"
        if blocked:
            block_penalty = (
                sr.TASK_BLOCKED_HIGH_CRIT_PENALTY if high_or_critical else sr.TASK_BLOCKED_PENALTY
            )
            penalty += block_penalty
            reasons.append(f"is blocked (-{block_penalty})")
            if high_or_critical and criticality is not None:
                severity: Severity = "Critical" if criticality == "Critical" else "High"
                drivers.append(
                    _driver(
                        "task_execution",
                        severity,
                        f"Task {task.task_id} is blocked and is linked to {task.milestone_id}, "
                        f"a {criticality} milestone.",
                        [task.task_id, task.milestone_id],
                        f"Reduced task execution by {block_penalty} points.",
                    )
                )

        if task.forecast_end_date < as_of_date:
            overdue_penalty = sr.TASK_OVERDUE_PENALTY
            if high_or_critical:
                overdue_penalty += sr.TASK_OVERDUE_HIGH_CRIT_EXTRA
            penalty += overdue_penalty
            reasons.append(
                f"is overdue (forecast end {task.forecast_end_date.isoformat()} before "
                f"{as_of_date.isoformat()}) (-{overdue_penalty})"
            )

        if (
            task.planned_end_date <= as_of_date
            and task.completion_percent < sr.TASK_LOW_COMPLETION_THRESHOLD
        ):
            penalty += sr.TASK_LOW_COMPLETION_PENALTY
            reasons.append(
                f"has {task.completion_percent}% completion with planned end "
                f"{task.planned_end_date.isoformat()} reached (-{sr.TASK_LOW_COMPLETION_PENALTY})"
            )

        if penalty > 0:
            score -= penalty
            source_ids.append(task.task_id)
            explanations.append(
                f"Task {task.task_id} ({task.task_name}) " + ", ".join(reasons) + "."
            )

    score = clamp(score)
    if not explanations:
        explanations.append(
            f"{_all_of(len(active), 'active task')} progressing without blockers or overdue "
            f"dates; task execution is {score}."
        )
    return _FactorOutcome(score, explanations, source_ids, drivers, limitations)


def _exposure_band(exposure: int) -> tuple[int, int, int] | None:
    """Return (open_penalty, no_owner_extra, not_started_extra) for an exposure value."""
    for low, high, open_penalty, no_owner_extra, not_started_extra in sr.RISK_EXPOSURE_BANDS:
        if low <= exposure <= high:
            return open_penalty, no_owner_extra, not_started_extra
    return None


def _risk_exposure(risks: list[Risk]) -> _FactorOutcome:
    score = float(sr.FACTOR_BASE_SCORE)
    explanations: list[str] = []
    source_ids: list[str] = []
    drivers: list[CriticalDriver] = []

    active_risks = [
        (risk, sr.normalize_status(risk.status, _RISK) or risk.status)
        for risk in risks
        if sr.is_active_risk_status(risk.status)
    ]
    for risk, status in active_risks:
        exposure = risk.probability * risk.impact
        band = _exposure_band(exposure)
        if band is None:
            continue
        open_penalty, no_owner_extra, not_started_extra = band
        if open_penalty == 0:
            continue

        penalty = open_penalty
        missing_owner = risk.mitigation_owner is None
        if missing_owner and no_owner_extra:
            penalty += no_owner_extra
        if (
            sr.normalize_status(risk.mitigation_status, _MITIGATION) == "Not Started"
            and not_started_extra
        ):
            penalty += not_started_extra

        score -= penalty
        source_ids.append(risk.risk_id)
        explanations.append(
            f"Risk {risk.risk_id} has probability {risk.probability} and impact {risk.impact}, "
            f"giving exposure {exposure}/25; it remains {status}"
            + (" and has no mitigation owner" if missing_owner else "")
            + f" (-{penalty})."
        )
        if exposure >= sr.ALERT_UNOWNED_RISK_EXPOSURE_MIN:
            severity: Severity = "Critical" if missing_owner else "High"
            drivers.append(
                _driver(
                    "risk_exposure",
                    severity,
                    f"Risk {risk.risk_id} has probability {risk.probability} and impact "
                    f"{risk.impact} (exposure {exposure}/25) and remains {status}"
                    + (" with no mitigation owner" if missing_owner else "")
                    + ".",
                    [risk.risk_id],
                    f"Reduced risk exposure by {penalty} points.",
                )
            )

    score = clamp(score)
    if not explanations:
        explanations.append(
            f"No Open or Mitigating risks exceed the exposure penalty threshold; risk exposure "
            f"is {score}."
        )
    return _FactorOutcome(score, explanations, source_ids, drivers)


def _days(count: int) -> str:
    return count_of(count, "day")


def _calendar_days(count: int) -> str:
    return count_of(count, "calendar day")


def _all_of(count: int, noun: str) -> str:
    """ "The 1 active task is" or "All 3 active tasks are"."""
    return f"The 1 {noun} is" if count == 1 else f"All {count_of(count, noun)} are"


def _long_delay_extra(delay_days: int) -> int:
    """Extra dependency penalty for very long delays, so a longer delay never scores better."""
    for max_days, extra in sr.DEPENDENCY_LONG_DELAY_EXTRAS:
        if delay_days <= max_days:
            return extra
    return sr.DEPENDENCY_LONG_DELAY_BEYOND_EXTRA


def _dependency_status(
    project_id: str, dependencies: list[Dependency], table_available: bool
) -> _FactorOutcome:
    if not table_available:
        message = "No dependency data is available; dependency health is only partially assessed."
        return _FactorOutcome(
            score=sr.DEPENDENCY_NONE_FALLBACK,
            explanations=[message],
            drivers=[
                _driver(
                    "dependency_status",
                    "Medium",
                    message,
                    [project_id],
                    f"Dependency status used fallback score {sr.DEPENDENCY_NONE_FALLBACK}.",
                )
            ],
            limitations=[message],
        )
    if not dependencies:
        return _FactorOutcome(
            score=float(sr.FACTOR_BASE_SCORE),
            explanations=[f"Project {project_id} has no dependencies; dependency status is 100."],
        )

    score = float(sr.FACTOR_BASE_SCORE)
    explanations: list[str] = []
    source_ids: list[str] = []
    drivers: list[CriticalDriver] = []

    for dependency in dependencies:
        status = sr.normalize_status(dependency.status, _DEPENDENCY)
        if status in sr.TERMINAL_DEPENDENCY_STATUSES:
            continue
        criticality = _priority_or_default(dependency.criticality)
        penalty = 0
        reasons: list[str] = []
        if dependency.delay_days > 0:
            delay_penalty = sr.DEPENDENCY_DELAY_PENALTY[criticality] + _long_delay_extra(
                dependency.delay_days
            )
            penalty += delay_penalty
            reasons.append(
                f"is delayed by {_days(dependency.delay_days)} (-{delay_penalty} for {criticality})"
            )
        if status == "Blocked":
            penalty += sr.DEPENDENCY_BLOCKED_EXTRA
            reasons.append(f"is Blocked (-{sr.DEPENDENCY_BLOCKED_EXTRA})")
        elif status == "Delayed":
            penalty += sr.DEPENDENCY_DELAYED_EXTRA
            reasons.append(f"is Delayed (-{sr.DEPENDENCY_DELAYED_EXTRA})")
        elif status == "At Risk":
            penalty += sr.DEPENDENCY_AT_RISK_EXTRA
            reasons.append(f"is At Risk (-{sr.DEPENDENCY_AT_RISK_EXTRA})")

        if penalty > 0:
            score -= penalty
            source_ids.append(dependency.dependency_id)
            explanations.append(
                f"Dependency {dependency.dependency_id} ({dependency.predecessor_id} -> "
                f"{dependency.successor_id}) " + ", ".join(reasons) + "."
            )
            if criticality in ("High", "Critical") and (
                dependency.delay_days > 0 or status in ("Blocked", "Delayed")
            ):
                severity: Severity = "Critical" if criticality == "Critical" else "High"
                drivers.append(
                    _driver(
                        "dependency_status",
                        severity,
                        f"Dependency {dependency.dependency_id} is {criticality} and "
                        + " and ".join(reasons)
                        + f"; it affects {dependency.successor_id}.",
                        [dependency.dependency_id],
                        f"Reduced dependency status by {penalty} points.",
                    )
                )

    score = clamp(score)
    if not explanations:
        explanations.append(f"All active dependencies are on track; dependency status is {score}.")
    return _FactorOutcome(score, explanations, source_ids, drivers)


def _utilisation_penalty(utilisation: float) -> int:
    """Map a utilisation percentage to a resource capacity penalty."""
    for max_util, penalty in sr.RESOURCE_UTIL_THRESHOLDS:
        if utilisation <= max_util:
            return penalty
    return sr.RESOURCE_UTIL_BEYOND_PENALTY


def _resource_capacity(
    project_id: str, resources: list[Resource], table_available: bool
) -> _FactorOutcome:
    if not table_available:
        message = "No resource data is available; resource capacity is only partially assessed."
        return _FactorOutcome(
            score=sr.RESOURCE_NONE_FALLBACK,
            explanations=[message],
            drivers=[
                _driver(
                    "resource_capacity",
                    "Medium",
                    message,
                    [project_id],
                    f"Resource capacity used fallback score {sr.RESOURCE_NONE_FALLBACK}.",
                )
            ],
            limitations=[message],
        )
    if not resources:
        return _FactorOutcome(
            score=float(sr.FACTOR_BASE_SCORE),
            explanations=[f"Project {project_id} has no resource allocations; capacity is 100."],
        )

    score = float(sr.FACTOR_BASE_SCORE)
    explanations: list[str] = []
    source_ids: list[str] = []
    drivers: list[CriticalDriver] = []

    for resource in resources:
        utilisation = resource.allocated_hours * 100 / resource.capacity_hours
        penalty = _utilisation_penalty(utilisation)
        if penalty > 0:
            score -= penalty
            source_ids.append(resource.resource_id)
            explanations.append(
                f"Resource {resource.resource_id} ({resource.resource_name}) is allocated "
                f"{resource.allocated_hours} hours against {resource.capacity_hours} available "
                f"({utilisation:.1f}% utilisation) (-{penalty})."
            )
            if utilisation > sr.ALERT_RESOURCE_UTIL_HIGH:
                severity: Severity = (
                    "Critical" if utilisation > sr.ALERT_RESOURCE_UTIL_CRITICAL else "High"
                )
                drivers.append(
                    _driver(
                        "resource_capacity",
                        severity,
                        f"Resource {resource.resource_id} is at {utilisation:.1f}% utilisation "
                        f"({resource.allocated_hours}/{resource.capacity_hours} hours).",
                        [resource.resource_id],
                        f"Reduced resource capacity by {penalty} points.",
                    )
                )

    score = clamp(score)
    if not explanations:
        explanations.append(
            f"All resource allocations are within 90% utilisation; resource capacity is {score}."
        )
    return _FactorOutcome(score, explanations, source_ids, drivers)


def _action_closure(
    project_id: str, actions: list[Action], table_available: bool, as_of_date: date
) -> _FactorOutcome:
    if not table_available:
        message = "No action data is available; action closure is only partially assessed."
        return _FactorOutcome(
            score=sr.ACTION_NONE_FALLBACK,
            explanations=[message],
            drivers=[
                _driver(
                    "action_closure",
                    "Medium",
                    message,
                    [project_id],
                    f"Action closure used fallback score {sr.ACTION_NONE_FALLBACK}.",
                )
            ],
            limitations=[message],
        )

    active = [
        a
        for a in actions
        if sr.normalize_status(a.status, _ACTION) not in sr.TERMINAL_ACTION_STATUSES
    ]
    if not active:
        return _FactorOutcome(
            score=float(sr.FACTOR_BASE_SCORE),
            explanations=[f"Project {project_id} has no active actions; action closure is 100."],
        )

    score = float(sr.FACTOR_BASE_SCORE)
    explanations: list[str] = []
    source_ids: list[str] = []
    drivers: list[CriticalDriver] = []

    for action in active:
        penalty = 0
        reasons: list[str] = []
        priority = _priority_or_default(action.priority)
        overdue = action.due_date < as_of_date
        days_overdue = days_between(action.due_date, as_of_date)
        if overdue:
            overdue_penalty = sr.ACTION_OVERDUE_PENALTY[priority]
            penalty += overdue_penalty
            reasons.append(f"is {_days(days_overdue)} overdue (-{overdue_penalty} for {priority})")
        if action.owner is None:
            penalty += sr.ACTION_NO_OWNER_EXTRA
            reasons.append(f"has no owner (-{sr.ACTION_NO_OWNER_EXTRA})")

        if penalty > 0:
            score -= penalty
            source_ids.append(action.action_id)
            explanations.append(f"Action {action.action_id} " + ", ".join(reasons) + ".")
            if overdue and priority in ("High", "Critical"):
                severity: Severity = "Critical" if priority == "Critical" else "High"
                drivers.append(
                    _driver(
                        "action_closure",
                        severity,
                        f"Action {action.action_id} is {days_overdue} calendar days overdue and "
                        f"has {priority} priority.",
                        [action.action_id],
                        f"Reduced action closure by {penalty} points.",
                    )
                )

    score = clamp(score)
    if not explanations:
        explanations.append(f"All active actions are on track; action closure is {score}.")
    return _FactorOutcome(score, explanations, source_ids, drivers)


def weighted_overall_score(factor_scores: dict[str, float]) -> float:
    """Combine seven factor scores using the central health weights, clamped to [0, 100]."""
    if set(factor_scores) != set(sr.HEALTH_FACTORS):
        raise ValueError(
            f"factor_scores keys {sorted(factor_scores)} must equal {sorted(sr.HEALTH_FACTORS)}"
        )
    total = sum(sr.HEALTH_WEIGHTS[factor] * factor_scores[factor] for factor in sr.HEALTH_FACTORS)
    return clamp(total)


def _ordered_drivers(drivers: list[CriticalDriver]) -> list[CriticalDriver]:
    """Deduplicate and stably sort drivers by severity, factor name and first source id."""
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    unique: list[CriticalDriver] = []
    for driver in drivers:
        key = (driver.factor_name, driver.severity, driver.message, tuple(driver.source_ids))
        if key in seen:
            continue
        seen.add(key)
        unique.append(driver)
    unique.sort(
        key=lambda d: (
            -sr.SEVERITY_ORDER[d.severity],
            d.factor_name,
            d.source_ids[0] if d.source_ids else "",
        )
    )
    return unique


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def calculate_project_health(
    project_id: str, portfolio: PortfolioData, as_of_date: date
) -> HealthResult:
    """Calculate the deterministic Health score for a single project.

    Args:
        project_id: The project to score.
        portfolio: Validated, read-only portfolio data.
        as_of_date: Calculation reference date for all time-relative logic.

    Returns:
        A fully populated :class:`HealthResult`.

    Raises:
        DataValidationError: If ``project_id`` is not present in the portfolio.
    """
    project = portfolio.get_project(project_id)
    if project is None:
        raise DataValidationError([f"unknown project_id '{project_id}'"])

    milestones = [m for m in portfolio.milestones if m.project_id == project_id]
    tasks = [t for t in portfolio.tasks if t.project_id == project_id]
    risks = [r for r in portfolio.risks if r.project_id == project_id]
    dependencies = [d for d in portfolio.dependencies if d.project_id == project_id]
    resources = [r for r in portfolio.resources if r.project_id == project_id]
    actions = [a for a in portfolio.actions if a.project_id == project_id]

    milestone_criticality = {
        m.milestone_id: _priority_or_default(m.criticality) for m in milestones
    }

    outcomes: dict[str, _FactorOutcome] = {
        "schedule_performance": _schedule_performance(project),
        "milestone_readiness": _milestone_readiness(milestones),
        "task_execution": _task_execution(tasks, milestone_criticality, as_of_date),
        "risk_exposure": _risk_exposure(risks),
        "dependency_status": _dependency_status(
            project_id, dependencies, bool(portfolio.dependencies)
        ),
        "resource_capacity": _resource_capacity(project_id, resources, bool(portfolio.resources)),
        "action_closure": _action_closure(project_id, actions, bool(portfolio.actions), as_of_date),
    }

    factor_scores = {name: round(outcome.score, 2) for name, outcome in outcomes.items()}
    factor_explanations = {name: outcome.explanations for name, outcome in outcomes.items()}
    overall = round(weighted_overall_score({n: o.score for n, o in outcomes.items()}), 2)

    drivers = _ordered_drivers([d for outcome in outcomes.values() for d in outcome.drivers])
    source_ids = sorted(
        {project_id}
        | {sid for outcome in outcomes.values() for sid in outcome.source_ids}
        | {sid for driver in drivers for sid in driver.source_ids}
    )
    limitations = _dedupe_preserving_order(
        ["Schedule performance uses calendar-day variance (Version 1)."]
        + [lim for outcome in outcomes.values() for lim in outcome.limitations]
    )

    return HealthResult(
        project_id=project_id,
        overall_score=overall,
        health_band=health_band(overall),
        factor_scores=factor_scores,
        factor_weights=dict(sr.HEALTH_WEIGHTS),
        factor_explanations=factor_explanations,
        critical_drivers=drivers,
        source_ids=source_ids,
        as_of_date=as_of_date,
        calculated_at=reference_timestamp(as_of_date),
        assumptions_or_limitations=limitations,
    )
