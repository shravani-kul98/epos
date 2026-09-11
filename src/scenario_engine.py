"""Non-mutating what-if scenario engine.

Builds an independent copy of the portfolio, applies validated interventions to that copy,
propagates the resulting schedule movement across the dependency network, and re-runs the existing
Health, Confidence and Risk engines against the modified copy. The baseline is never modified.

This module contains no scoring logic of its own. Its responsibilities are: validating
interventions, building the modified copy, invoking :mod:`src.scenario_network` for propagation,
invoking the three existing engines for baseline and scenario, and structuring the comparison.
See ``docs/scenario-methodology.md``.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from datetime import date

from src import scoring_rules as sr
from src.confidence_engine import calculate_project_confidence
from src.data_loader import PortfolioData
from src.delivery_rules import DependencyEdge, DependencyEndpointType
from src.health_engine import calculate_project_health
from src.risk_engine import generate_early_warnings
from src.scenario_network import (
    MILESTONE,
    TASK,
    Node,
    PropagationResult,
    edge_free_float,
    free_float_days,
    propagate,
)
from src.schemas import (
    EarlyWarningAlert,
    ScenarioFactorDelta,
    ScenarioInsight,
    ScenarioIntervention,
    ScenarioProjectComparison,
    ScenarioResult,
    ScenarioSensitivity,
    ScenarioThreshold,
    ScheduleMovement,
)
from src.ui_formatting import format_score, format_signed_score
from src.utils import reference_timestamp
from src.validators import DataValidationError
from src.wording import count_of, joined

SCENARIO_DEPENDENCY_DELAY = "dependency_delay"
SCENARIO_MULTI_EVENT = "multi_event"


def _alert_counts(alerts: list[EarlyWarningAlert]) -> dict[str, int]:
    counts = dict.fromkeys(sr.SEVERITY_ORDER, 0)
    for alert in alerts:
        counts[alert.severity] = counts.get(alert.severity, 0) + 1
    return counts


def validate_interventions(
    interventions: Sequence[ScenarioIntervention], portfolio: PortfolioData
) -> None:
    """Reject unknown targets, out-of-range values and conflicting edits before any work.

    Raises:
        DataValidationError: Listing every problem found, so one round trip reports them all.
    """
    if not interventions:
        raise DataValidationError(["a scenario requires at least one intervention"])

    known: dict[sr.ScenarioInterventionType, set[str]] = {
        sr.ScenarioInterventionType.DEPENDENCY_DELAY: {
            item.dependency_id for item in portfolio.dependencies
        },
        sr.ScenarioInterventionType.TASK_DELAY: {item.task_id for item in portfolio.tasks},
        sr.ScenarioInterventionType.MILESTONE_DELAY: {
            item.milestone_id for item in portfolio.milestones
        },
        sr.ScenarioInterventionType.RISK_PROBABILITY: {item.risk_id for item in portfolio.risks},
        sr.ScenarioInterventionType.RISK_IMPACT: {item.risk_id for item in portfolio.risks},
        sr.ScenarioInterventionType.RESOURCE_CAPACITY: {
            item.resource_id for item in portfolio.resources
        },
    }

    issues: list[str] = []
    seen: set[tuple[str, str]] = set()
    for intervention in interventions:
        kind = intervention.intervention_type
        if intervention.target_id not in known[kind]:
            issues.append(f"unknown {kind.value} target '{intervention.target_id}'")
        low, high = sr.SCENARIO_INTERVENTION_BOUNDS[kind]
        if not low <= intervention.value <= high:
            issues.append(
                f"{kind.value} value {intervention.value} for '{intervention.target_id}' must be "
                f"between {low} and {high} {intervention.unit}"
            )
        key = (kind.value, intervention.target_id)
        if key in seen:
            issues.append(
                f"conflicting interventions: {kind.value} is applied to "
                f"'{intervention.target_id}' more than once"
            )
        seen.add(key)

    if issues:
        raise DataValidationError(issues)


def _seeded_edge_float(portfolio: PortfolioData, dependency) -> int:
    """Free float on the delayed link itself, which absorbs delay before anything moves."""
    try:
        edge = DependencyEdge(
            dependency_id=dependency.dependency_id,
            predecessor_type=DependencyEndpointType(dependency.predecessor_type),
            predecessor_id=dependency.predecessor_id,
            successor_type=DependencyEndpointType(dependency.successor_type),
            successor_id=dependency.successor_id,
        )
    except ValueError:
        return 0
    float_days, _ = free_float_days(portfolio, edge, dependency.lag_days or 0)
    return float_days


def _seed_shifts(
    interventions: Sequence[ScenarioIntervention], portfolio: PortfolioData
) -> dict[Node, int]:
    """Translate schedule interventions into the graph nodes they move directly."""
    dependencies = {item.dependency_id: item for item in portfolio.dependencies}
    seeds: dict[Node, int] = {}
    for intervention in interventions:
        kind = intervention.intervention_type
        value = intervention.value
        if kind is sr.ScenarioInterventionType.DEPENDENCY_DELAY:
            dependency = dependencies.get(intervention.target_id)
            if dependency is None:
                continue
            node = (dependency.successor_type, dependency.successor_id)
            value = max(0, value - _seeded_edge_float(portfolio, dependency))
        elif kind is sr.ScenarioInterventionType.TASK_DELAY:
            node = (TASK, intervention.target_id)
        elif kind is sr.ScenarioInterventionType.MILESTONE_DELAY:
            node = (MILESTONE, intervention.target_id)
        else:
            continue
        # Convergent seeds on one node take the largest, never the sum.
        seeds[node] = max(seeds.get(node, 0), value)
    return seeds


def _apply_non_schedule(
    scenario: PortfolioData, interventions: Sequence[ScenarioIntervention]
) -> None:
    """Apply risk and capacity interventions to the scenario copy."""
    risk_probability = {
        item.target_id: item.value
        for item in interventions
        if item.intervention_type is sr.ScenarioInterventionType.RISK_PROBABILITY
    }
    risk_impact = {
        item.target_id: item.value
        for item in interventions
        if item.intervention_type is sr.ScenarioInterventionType.RISK_IMPACT
    }
    capacity = {
        item.target_id: item.value
        for item in interventions
        if item.intervention_type is sr.ScenarioInterventionType.RESOURCE_CAPACITY
    }

    if risk_probability or risk_impact:
        scenario.risks = [
            risk.model_copy(
                update={
                    key: value
                    for key, value in (
                        ("probability", risk_probability.get(risk.risk_id)),
                        ("impact", risk_impact.get(risk.risk_id)),
                    )
                    if value is not None
                }
            )
            for risk in scenario.risks
        ]
    if capacity:
        scenario.resources = [
            (
                resource.model_copy(update={"capacity_hours": capacity[resource.resource_id]})
                if resource.resource_id in capacity and capacity[resource.resource_id] > 0
                else resource
            )
            for resource in scenario.resources
        ]


def _apply_dependency_delays(
    scenario: PortfolioData, interventions: Sequence[ScenarioIntervention]
) -> dict[str, tuple[int, int]]:
    """Raise recorded delay on targeted dependencies, returning before and after delay."""
    delays = {
        item.target_id: item.value
        for item in interventions
        if item.intervention_type is sr.ScenarioInterventionType.DEPENDENCY_DELAY
    }
    if not delays:
        return {}

    movement: dict[str, tuple[int, int]] = {}
    updated = []
    for dependency in scenario.dependencies:
        extra = delays.get(dependency.dependency_id)
        if extra is None:
            updated.append(dependency)
            continue
        baseline_delay = dependency.delay_days
        scenario_delay = baseline_delay + extra
        movement[dependency.dependency_id] = (baseline_delay, scenario_delay)
        status = (
            dependency.status
            if sr.normalize_status(dependency.status, sr.StatusDomain.DEPENDENCY) == "Blocked"
            else sr.SCENARIO_DELAYED_STATUS
        )
        updated.append(
            dependency.model_copy(update={"delay_days": scenario_delay, "status": status})
        )
    scenario.dependencies = updated
    return movement


def _factor_deltas(baseline_health, scenario_health) -> list[ScenarioFactorDelta]:
    """Attribute the overall score movement to the factors that produced it."""
    weights = baseline_health.factor_weights
    deltas = []
    for factor in sr.HEALTH_FACTORS:
        before = baseline_health.factor_scores[factor]
        after = scenario_health.factor_scores[factor]
        weight = weights[factor]
        deltas.append(
            ScenarioFactorDelta(
                factor=factor,
                baseline_score=round(before, 2),
                scenario_score=round(after, 2),
                score_delta=round(after - before, 2),
                weight=weight,
                weighted_contribution=round((after - before) * weight, 2),
            )
        )
    deltas.sort(key=lambda item: (item.weighted_contribution, item.factor))
    return deltas


def _compare_project(
    project_id: str,
    baseline: PortfolioData,
    scenario: PortfolioData,
    as_of_date: date,
) -> ScenarioProjectComparison:
    baseline_health = calculate_project_health(project_id, baseline, as_of_date)
    baseline_confidence = calculate_project_confidence(project_id, baseline, as_of_date)
    baseline_alerts = generate_early_warnings(project_id, baseline, as_of_date)

    scenario_health = calculate_project_health(project_id, scenario, as_of_date)
    scenario_confidence = calculate_project_confidence(project_id, scenario, as_of_date)
    scenario_alerts = generate_early_warnings(project_id, scenario, as_of_date)

    baseline_by_id = {alert.alert_id: alert for alert in baseline_alerts}
    scenario_by_id = {alert.alert_id: alert for alert in scenario_alerts}
    baseline_ids = set(baseline_by_id)
    scenario_ids = set(scenario_by_id)

    baseline_project = baseline.get_project(project_id)
    scenario_project = scenario.get_project(project_id)
    baseline_end = baseline_project.forecast_end_date if baseline_project else None
    scenario_end = scenario_project.forecast_end_date if scenario_project else None
    shift = (scenario_end - baseline_end).days if baseline_end and scenario_end else 0

    return ScenarioProjectComparison(
        project_id=project_id,
        baseline_health_score=baseline_health.overall_score,
        baseline_health_band=baseline_health.health_band,
        scenario_health_score=scenario_health.overall_score,
        scenario_health_band=scenario_health.health_band,
        health_score_delta=round(scenario_health.overall_score - baseline_health.overall_score, 2),
        baseline_confidence_score=baseline_confidence.overall_score,
        baseline_confidence_band=baseline_confidence.confidence_band,
        scenario_confidence_score=scenario_confidence.overall_score,
        scenario_confidence_band=scenario_confidence.confidence_band,
        confidence_score_delta=round(
            scenario_confidence.overall_score - baseline_confidence.overall_score, 2
        ),
        baseline_alert_counts=_alert_counts(baseline_alerts),
        scenario_alert_counts=_alert_counts(scenario_alerts),
        new_alert_ids=sorted(scenario_ids - baseline_ids),
        resolved_alert_ids=sorted(baseline_ids - scenario_ids),
        changed_alert_ids=sorted(
            alert_id
            for alert_id in baseline_ids & scenario_ids
            if baseline_by_id[alert_id].severity != scenario_by_id[alert_id].severity
        ),
        baseline_forecast_end_date=baseline_end,
        scenario_forecast_end_date=scenario_end,
        forecast_end_shift_days=shift,
        factor_deltas=_factor_deltas(baseline_health, scenario_health),
    )


def _affected_project_ids(
    interventions: Sequence[ScenarioIntervention],
    portfolio: PortfolioData,
    propagation: PropagationResult,
) -> list[str]:
    """Every project a scenario reaches, whether targeted directly or through propagation."""
    tasks = {item.task_id: item.project_id for item in portfolio.tasks}
    milestones = {item.milestone_id: item.project_id for item in portfolio.milestones}
    lookup: dict[sr.ScenarioInterventionType, dict[str, str]] = {
        sr.ScenarioInterventionType.DEPENDENCY_DELAY: {
            item.dependency_id: item.project_id for item in portfolio.dependencies
        },
        sr.ScenarioInterventionType.TASK_DELAY: tasks,
        sr.ScenarioInterventionType.MILESTONE_DELAY: milestones,
        sr.ScenarioInterventionType.RISK_PROBABILITY: {
            item.risk_id: item.project_id for item in portfolio.risks
        },
        sr.ScenarioInterventionType.RISK_IMPACT: {
            item.risk_id: item.project_id for item in portfolio.risks
        },
        sr.ScenarioInterventionType.RESOURCE_CAPACITY: {
            item.resource_id: item.project_id for item in portfolio.resources
        },
    }

    project_ids = {
        lookup[item.intervention_type][item.target_id]
        for item in interventions
        if item.target_id in lookup[item.intervention_type]
    }
    for step in propagation.steps:
        owner = tasks.get(step.record_id) if step.record_type == TASK else None
        if owner is None:
            owner = milestones.get(step.record_id)
        if owner:
            project_ids.add(owner)
    return sorted(project_ids)


def _explain(
    interventions: Sequence[ScenarioIntervention],
    comparisons: Sequence[ScenarioProjectComparison],
    movements: Sequence[ScheduleMovement],
    project_names: dict[str, str] | None = None,
) -> str:
    applied = "; ".join(item.describe for item in interventions)
    if not comparisons:
        return f"Applying {applied} moved no project that EPOS can measure."

    parts = []
    for comparison in comparisons:
        schedule = (
            f"its forecast end date moves {count_of(comparison.forecast_end_shift_days, 'calendar day')}"
            if comparison.forecast_end_shift_days
            else "its forecast end date does not move"
        )
        parts.append(
            f"For {((project_names or {}).get(comparison.project_id, 'project'))} "
            f"({comparison.project_id}), {schedule}. Health moves from "
            f"{format_score(comparison.baseline_health_score)} "
            f"({comparison.baseline_health_band}) to "
            f"{format_score(comparison.scenario_health_score)} "
            f"({comparison.scenario_health_band}), "
            f"Confidence from {format_score(comparison.baseline_confidence_score)} "
            f"({comparison.baseline_confidence_band}) to "
            f"{format_score(comparison.scenario_confidence_score)} "
            f"({comparison.scenario_confidence_band})."
        )
    reach = (
        f" {count_of(len(movements), 'record')} moved through the dependency network."
        if movements
        else " No downstream record moved."
    )
    return f"Applying {applied}. " + " ".join(parts) + reach


def _threshold_note(dependency_id: str, baseline_delay: int, scenario_delay: int) -> str:
    """Explain why more delay on an already late dependency left health where it was."""
    dependency_steps = joined([str(days) for days, _ in sr.DEPENDENCY_LONG_DELAY_EXTRAS])
    slip_steps = joined([str(days) for days, _ in sr.SCHEDULE_SLIP_THRESHOLDS])
    return (
        f"Moving {dependency_id} from {count_of(baseline_delay, 'day')} to "
        f"{count_of(scenario_delay, 'day')} of delay crosses no scoring threshold, so health "
        f"does not move. Dependency penalties step up beyond {dependency_steps} days of delay, "
        f"and schedule performance steps down beyond {slip_steps} calendar days of slip."
    )


def _saturation_notes(
    comparisons: Sequence[ScenarioProjectComparison],
    has_schedule_interventions: bool = True,
) -> list[str]:
    """Explain any factor that could not move, or that moved in a counter-intuitive direction."""
    notes: list[str] = []
    for comparison in comparisons:
        for factor in comparison.factor_deltas:
            if (
                factor.score_delta > 0
                and has_schedule_interventions
                and factor.factor == "task_execution"
            ):
                # Task execution penalises work whose forecast is already behind today. Pushing a
                # late forecast into the future removes that penalty, so added delay can raise the
                # factor. The movement is reported rather than hidden, and must not be read as the
                # delay improving delivery.
                notes.append(
                    f"Project {comparison.project_id}: {factor.factor} rose by "
                    f"{factor.score_delta} because delay moved work past a date-based threshold "
                    "rather than because delivery improved. Judge this scenario on the forecast "
                    "date movement."
                )
                continue
            if factor.score_delta != 0:
                continue
            if factor.scenario_score <= 0:
                notes.append(
                    f"Project {comparison.project_id}: {factor.factor} is already at its minimum "
                    "of 0, so further delay cannot lower it. Judge this scenario on the forecast "
                    "date movement instead."
                )
            elif factor.factor == "schedule_performance" and factor.scenario_score <= (
                sr.SCHEDULE_SLIP_BEYOND_SCORE
            ):
                notes.append(
                    f"Project {comparison.project_id}: schedule performance is already at its "
                    f"floor of {sr.SCHEDULE_SLIP_BEYOND_SCORE}, reached once slip exceeds "
                    f"{sr.SCHEDULE_SLIP_THRESHOLDS[-1][0]} calendar days, so further delay cannot "
                    "lower it."
                )
    return notes


def _decision_brief(
    interventions: Sequence[ScenarioIntervention],
    comparisons: Sequence[ScenarioProjectComparison],
    movements: Sequence[ScheduleMovement],
    portfolio: PortfolioData,
) -> list[ScenarioInsight]:
    """Explain the comparison without introducing predictions or unrecorded actions."""
    insights: list[ScenarioInsight] = []
    sources = [item.target_id for item in interventions]
    names = {project.project_id: project.project_name for project in portfolio.projects}
    dependencies = {item.dependency_id: item for item in portfolio.dependencies}
    floats = edge_free_float(portfolio)
    for item in interventions:
        if item.intervention_type != sr.ScenarioInterventionType.DEPENDENCY_DELAY:
            continue
        dependency = dependencies[item.target_id]
        slack = floats.get(item.target_id)
        if slack is not None and slack > 0:
            absorbed = min(slack, item.value)
            insights.append(
                ScenarioInsight(
                    kind="schedule",
                    project_id=dependency.project_id,
                    headline=f"{absorbed} of {item.value} added days fit within recorded handoff slack",
                    detail=f"{dependency.dependency_name} has {slack} calendar days of recorded gap after lag. "
                    "This is link-level slack, not proof of a project critical path or a safe delivery plan.",
                    source_ids=[
                        dependency.dependency_id,
                        dependency.predecessor_id,
                        dependency.successor_id,
                    ],
                )
            )

    for comparison in comparisons:
        project_id = comparison.project_id
        label = names.get(project_id, project_id)
        ids = list(dict.fromkeys([project_id, *sources]))
        if comparison.baseline_forecast_end_date is None:
            headline = f"{label}: project completion impact is not measurable"
            detail = (
                "No project forecast finish is recorded. Review the moved tasks and milestones; "
                "an absent project date is not a zero-day impact."
            )
        elif comparison.forecast_end_shift_days:
            headline = f"{label}: completion moves {comparison.forecast_end_shift_days} calendar days later"
            detail = (
                f"Recorded forecast {comparison.baseline_forecast_end_date.isoformat()} → "
                f"scenario {comparison.scenario_forecast_end_date.isoformat()}. "
                "The latest reached delivery record controls this comparison; no probability is estimated."
            )
        else:
            headline = f"{label}: recorded completion date does not move"
            detail = (
                "The simulated records do not push the recorded project finish later. "
                "Inspect local movement, existing slack and score warnings before treating this as no impact."
            )
        insights.append(
            ScenarioInsight(
                kind="schedule",
                project_id=project_id,
                headline=headline,
                detail=detail,
                source_ids=ids,
            )
        )
        changed = [factor for factor in comparison.factor_deltas if factor.score_delta]
        if changed:
            factor = max(changed, key=lambda entry: abs(entry.weighted_contribution))
            caution = (
                " A better score alongside a later date is not a delivery improvement."
                if (comparison.forecast_end_shift_days > 0 and comparison.health_score_delta > 0)
                else ""
            )
            insights.append(
                ScenarioInsight(
                    kind="score",
                    project_id=project_id,
                    headline=f"{label}: health {format_score(comparison.baseline_health_score)} → "
                    f"{format_score(comparison.scenario_health_score)} ({format_signed_score(comparison.health_score_delta)} points)",
                    detail=f"Largest weighted movement: {factor.factor}, {format_score(factor.baseline_score)} → "
                    f"{format_score(factor.scenario_score)} factor points at {factor.weight:.0%} weight, contributing "
                    f"{format_signed_score(factor.weighted_contribution)} overall points.{caution}",
                    source_ids=ids,
                )
            )
        if (
            comparison.new_alert_ids
            or comparison.resolved_alert_ids
            or comparison.changed_alert_ids
        ):
            insights.append(
                ScenarioInsight(
                    kind="review",
                    project_id=project_id,
                    headline=f"{label}: review the changed warning picture",
                    detail=f"{len(comparison.new_alert_ids)} new, {len(comparison.resolved_alert_ids)} no longer triggered, "
                    f"and {len(comparison.changed_alert_ids)} severity changes. These are simulated warnings, "
                    "not closed risks or completed mitigations.",
                    source_ids=ids,
                )
            )
    insights.append(
        ScenarioInsight(
            kind="coverage",
            headline=f"{len(movements)} delivery records move in this run",
            detail="Follow each movement to its controlling dependency. The model uses recorded calendar-day "
            "relationships; it does not forecast unrecorded work, cost, recovery effort or delivery probability.",
            source_ids=list(dict.fromkeys([*sources, *(item.record_id for item in movements)])),
        )
    )
    return insights


def run_scenario(
    interventions: Sequence[ScenarioIntervention],
    portfolio: PortfolioData,
    as_of_date: date,
) -> ScenarioResult:
    """Apply validated interventions to a copy and compare every project they reach.

    Args:
        interventions: Validated changes to apply. At least one is required.
        portfolio: Validated, read-only baseline portfolio. Never modified.
        as_of_date: Calculation reference date.

    Returns:
        A :class:`ScenarioResult` comparing baseline and scenario outcomes.

    Raises:
        DataValidationError: If an intervention is invalid or the network cannot be simulated.
    """
    validate_interventions(interventions, portfolio)
    # Ordering is normalised so logically commutative interventions cannot change the result.
    ordered = sorted(interventions, key=lambda item: (item.intervention_type.value, item.target_id))

    scenario = copy.deepcopy(portfolio)
    delay_movement = _apply_dependency_delays(scenario, ordered)
    _apply_non_schedule(scenario, ordered)
    status_notes = [
        (
            f"Dependency {dependency.dependency_id} "
            + (
                "leaves it Blocked"
                if sr.normalize_status(dependency.status, sr.StatusDomain.DEPENDENCY) == "Blocked"
                else f"marks it {sr.SCENARIO_DELAYED_STATUS}"
            )
            + "."
        )
        for dependency in scenario.dependencies
        if dependency.dependency_id in delay_movement
    ]

    try:
        propagation = propagate(scenario, _seed_shifts(ordered, scenario))
    except ValueError as exc:
        raise DataValidationError([f"the dependency network cannot be simulated: {exc}"]) from exc

    project_ids = _affected_project_ids(ordered, portfolio, propagation)
    comparisons = [
        _compare_project(project_id, portfolio, scenario, as_of_date) for project_id in project_ids
    ]

    movements = [
        ScheduleMovement(
            record_type=step.record_type,
            record_id=step.record_id,
            original_date=step.original_date,
            scenario_date=step.scenario_date,
            shift_days=step.shift_days,
            controlling_dependency_id=step.controlling_dependency_id,
            controlling_predecessor_id=step.controlling_predecessor_id,
            propagation_hop=step.hop,
        )
        for step in propagation.steps
    ]

    source_id_set = {item.target_id for item in ordered}
    source_id_set.update(project_ids)
    for step in propagation.steps:
        source_id_set.update(step.evidence_ids)

    primary = next(
        (
            item
            for item in ordered
            if item.intervention_type is sr.ScenarioInterventionType.DEPENDENCY_DELAY
        ),
        None,
    )
    dependency_id = primary.target_id if primary else ""
    baseline_delay, scenario_delay = delay_movement.get(dependency_id, (0, 0))

    limitations = [
        "Scenario results are simulated and do not modify baseline project data.",
        "Delay propagates in calendar days, matching the Health engine's slip thresholds.",
        "Activity durations are preserved: a delayed record shifts as a whole, so every "
        "relationship type transmits the same magnitude.",
        *propagation.limitations,
        *_saturation_notes(comparisons, bool(_seed_shifts(ordered, portfolio))),
    ]
    if (
        primary
        and baseline_delay > 0
        and comparisons
        and all(comparison.health_score_delta == 0 for comparison in comparisons)
    ):
        limitations.append(_threshold_note(dependency_id, baseline_delay, scenario_delay))
    if not propagation.steps:
        limitations.append(
            "No downstream forecast movement was calculated. Recorded link slack may absorb the "
            "delay, the intervention may not change schedules, or forecast-bearing links may be absent."
        )

    brief = _decision_brief(ordered, comparisons, movements, portfolio)
    source_id_set.update(source_id for item in brief for source_id in item.source_ids)

    return ScenarioResult(
        scenario_type=(
            SCENARIO_DEPENDENCY_DELAY if len(ordered) == 1 and primary else SCENARIO_MULTI_EVENT
        ),
        dependency_id=dependency_id,
        additional_delay_days=primary.value if primary else 0,
        baseline_delay_days=baseline_delay,
        scenario_delay_days=scenario_delay,
        affected_projects=comparisons,
        deterministic_explanation=" ".join(
            [
                _explain(
                    ordered,
                    comparisons,
                    movements,
                    {item.project_id: item.project_name for item in portfolio.projects},
                ),
                *status_notes,
            ]
        ),
        source_ids=sorted(source_id_set),
        as_of_date=as_of_date,
        calculated_at=reference_timestamp(as_of_date),
        assumptions_or_limitations=limitations,
        interventions=list(ordered),
        schedule_movements=movements,
        decision_brief=brief,
    )


def _threshold(
    outcome: str,
    values: Sequence[int],
    triggered: Sequence[bool],
    unit: str,
    scores: Sequence[float],
    explanation_when_never: str,
) -> ScenarioThreshold:
    """The smallest tested value at which an outcome first holds."""
    first = next((value for value, hit in zip(values, triggered, strict=True) if hit), None)
    return ScenarioThreshold(
        outcome=outcome,
        occurs_at_value=first,
        unit=unit,
        tested_values=list(values),
        observed_scores=list(scores),
        explanation=(
            f"{outcome} first occurs at the tested value of {first} {unit}; intermediate values were not evaluated."
            if first is not None
            else explanation_when_never
        ),
    )


def analyse_sensitivity(
    intervention_type: sr.ScenarioInterventionType,
    target_id: str,
    portfolio: PortfolioData,
    as_of_date: date,
    values: Sequence[int] | None = None,
) -> ScenarioSensitivity:
    """Re-run one intervention across a range and report where outcomes change.

    Every point is a full deterministic run of the same engine, so the response curve and the
    thresholds below are calculated, never interpolated or estimated.

    Raises:
        DataValidationError: If the intervention target or any tested value is invalid.
    """
    tested = list(values) if values is not None else list(sr.SCENARIO_SENSITIVITY_DELAY_DAYS)
    low, high = sr.SCENARIO_INTERVENTION_BOUNDS[intervention_type]
    tested = sorted({value for value in tested if low <= value <= high})
    if not tested:
        raise DataValidationError(
            [f"no tested value falls inside the {low}-{high} bound for {intervention_type.value}"]
        )

    results = [
        run_scenario(
            [
                ScenarioIntervention(
                    intervention_type=intervention_type, target_id=target_id, value=value
                )
            ],
            portfolio,
            as_of_date,
        )
        for value in tested
    ]

    project_id = ""
    for result in results:
        if result.affected_projects:
            project_id = result.affected_projects[0].project_id
            break

    def _comparison(result: ScenarioResult):
        return next(
            (item for item in result.affected_projects if item.project_id == project_id), None
        )

    scores: list[float] = []
    shifts: list[int] = []
    band_changed: list[bool] = []
    schedule_moved: list[bool] = []
    for result in results:
        comparison = _comparison(result)
        scores.append(comparison.scenario_health_score if comparison else 0.0)
        shifts.append(comparison.forecast_end_shift_days if comparison else 0)
        band_changed.append(
            bool(comparison) and comparison.scenario_health_band != comparison.baseline_health_band
        )
        schedule_moved.append(bool(comparison) and comparison.forecast_end_shift_days > 0)

    unit = sr.SCENARIO_INTERVENTION_UNITS[intervention_type]
    responsive = len(set(scores)) > 1 or len(set(shifts)) > 1
    saturated = None
    for index in range(1, len(tested)):
        if len(set(zip(scores[index - 1 :], shifts[index - 1 :], strict=True))) == 1:
            saturated = tested[index - 1]
            break

    limitations = [
        "Each point is a full deterministic re-run; no value between tested points is estimated.",
        "A threshold is reported at the smallest tested value, so the true threshold lies between "
        "it and the previous tested value.",
    ]
    if not responsive:
        limitations.append(
            "This input did not change the outcome at any tested value. Every affected factor is "
            "already at a bound, or the target reaches no record carrying a forecast date."
        )

    return ScenarioSensitivity(
        intervention_type=intervention_type,
        target_id=target_id,
        project_id=project_id,
        unit=unit,
        tested_values=tested,
        health_scores=scores,
        forecast_shift_days=shifts,
        is_responsive=responsive,
        saturated_at_value=saturated,
        thresholds=[
            _threshold(
                "The project forecast end date moves",
                tested,
                schedule_moved,
                unit,
                scores,
                "The project forecast end date did not move at any tested value, because recorded "
                "float absorbs the delay or the project already finishes later than the record.",
            ),
            _threshold(
                "The project health band changes",
                tested,
                band_changed,
                unit,
                scores,
                "The health band did not change at any tested value.",
            ),
        ],
        assumptions_or_limitations=limitations,
    )


def simulate_dependency_delay(
    dependency_id: str,
    additional_delay_days: int,
    portfolio: PortfolioData,
    as_of_date: date,
) -> ScenarioResult:
    """Simulate additional delay on one dependency and compare against the baseline.

    Retained as the single-dependency entry point used by the API and Ask EPOS.

    Raises:
        DataValidationError: If the dependency is unknown or the delay is out of bounds.
    """
    if not (sr.SCENARIO_MIN_DELAY_DAYS <= additional_delay_days <= sr.SCENARIO_MAX_DELAY_DAYS):
        raise DataValidationError(
            [
                f"additional_delay_days {additional_delay_days} must be between "
                f"{sr.SCENARIO_MIN_DELAY_DAYS} and {sr.SCENARIO_MAX_DELAY_DAYS}"
            ]
        )
    if not any(item.dependency_id == dependency_id for item in portfolio.dependencies):
        raise DataValidationError([f"unknown dependency_id '{dependency_id}'"])

    return run_scenario(
        [
            ScenarioIntervention(
                intervention_type=sr.ScenarioInterventionType.DEPENDENCY_DELAY,
                target_id=dependency_id,
                value=additional_delay_days,
            )
        ],
        portfolio,
        as_of_date,
    )
