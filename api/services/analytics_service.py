"""Translate deterministic engine results into product-language API responses.

Nothing in this module calculates a score, band, severity or impact. Every number originates in
``src/`` and is passed through unchanged; only presentation vocabulary is added.
"""

from __future__ import annotations

from datetime import date

from api import labels
from api.schemas import (
    AlertOut,
    BandCounts,
    ChangeImpactOut,
    ConfidenceBandCounts,
    ConfidenceOut,
    DataQualityIssueOut,
    DriverOut,
    FactorBreakdown,
    HealthOut,
    PortfolioDashboard,
    PortfolioFilters,
    ProjectDashboard,
    ProjectSummary,
    ScenarioComparisonOut,
    ScenarioFactorDeltaOut,
    ScenarioInsightOut,
    ScenarioInterventionOut,
    ScenarioOut,
    ScenarioSensitivityOut,
    ScenarioThresholdOut,
    ScheduleMovementOut,
    SeverityCounts,
    TraceabilityMatrix,
    TraceabilityRow,
)
from api.serializers import project_out
from src import scenario_engine
from src.change_impact_engine import calculate_change_impact
from src.confidence_engine import calculate_project_confidence
from src.data_loader import PortfolioData
from src.health_engine import calculate_project_health
from src.project_assessment import assess_project_evidence
from src.risk_engine import generate_early_warnings, generate_portfolio_early_warnings
from src.scenario_engine import simulate_dependency_delay
from src.schemas import (
    ChangeImpactResult,
    ConfidenceResult,
    EarlyWarningAlert,
    HealthResult,
    ScenarioIntervention,
    ScenarioResult,
)
from src.scoring_rules import (
    ScenarioInterventionType,
    StatusDomain,
    needs_attention,
    normalize_status,
)
from src.ui_formatting import trace_status
from src.utils import safe_div
from src.workflow_rules import is_change_request_decided

_SEVERITY_FIELDS = {"Critical": "critical", "High": "high", "Medium": "medium", "Low": "low"}
_TOP_ALERT_LIMIT = 10


# --------------------------------------------------------------------------- helpers
def _severity_counts(alerts: list[EarlyWarningAlert]) -> SeverityCounts:
    """Tally alerts into the API severity shape."""
    counts = SeverityCounts()
    for alert in alerts:
        field = _SEVERITY_FIELDS.get(alert.severity)
        if field is not None:
            setattr(counts, field, getattr(counts, field) + 1)
    return counts


def _severity_counts_from_map(raw: dict[str, int]) -> SeverityCounts:
    """Convert an engine severity map into the API severity shape."""
    counts = SeverityCounts()
    for severity, value in raw.items():
        field = _SEVERITY_FIELDS.get(severity)
        if field is not None:
            setattr(counts, field, value)
    return counts


def _increment(counts: BandCounts | ConfidenceBandCounts, band: str) -> None:
    """Tally one engine-assigned band."""
    field = band.lower()
    if hasattr(counts, field):
        setattr(counts, field, getattr(counts, field) + 1)


def _factors(
    result: HealthResult | ConfidenceResult,
    label_for: object,
    descriptions: dict[str, str],
) -> list[FactorBreakdown]:
    """Build the ordered factor breakdown, weakest factor first."""
    ordered = sorted(result.factor_scores.items(), key=lambda item: (item[1], item[0]))
    breakdown: list[FactorBreakdown] = []
    for key, score in ordered:
        weight = result.factor_weights.get(key, 0.0)
        breakdown.append(
            FactorBreakdown(
                key=key,
                label=label_for(key),  # type: ignore[operator]
                description=descriptions.get(key, ""),
                score=score,
                weight=weight,
                weighted_contribution=round(score * weight, 2),
                explanations=labels.humanise_all(result.factor_explanations.get(key, [])),
            )
        )
    return breakdown


def health_out(result: HealthResult) -> HealthOut:
    """Present a health result."""
    return HealthOut(
        project_id=result.project_id,
        score=result.overall_score,
        band=result.health_band,
        factors=_factors(result, labels.health_factor_label, labels.HEALTH_FACTOR_DESCRIPTIONS),
        critical_drivers=[
            DriverOut(
                factor_label=labels.health_factor_label(driver.factor_name),
                severity=driver.severity,
                message=labels.humanise(driver.message),
                source_ids=driver.source_ids,
                score_impact_description=labels.humanise(driver.score_impact_description),
            )
            for driver in result.critical_drivers
        ],
        source_ids=result.source_ids,
        as_of_date=result.as_of_date,
        calculated_at=result.calculated_at,
        assumptions_or_limitations=labels.humanise_all(result.assumptions_or_limitations),
    )


def confidence_out(result: ConfidenceResult) -> ConfidenceOut:
    """Present a confidence result."""
    return ConfidenceOut(
        project_id=result.project_id,
        score=result.overall_score,
        band=result.confidence_band,
        factors=_factors(
            result, labels.confidence_factor_label, labels.CONFIDENCE_FACTOR_DESCRIPTIONS
        ),
        data_quality_issues=[
            DataQualityIssueOut(
                issue_type=issue.issue_type,
                severity=issue.severity,
                message=labels.humanise(issue.message),
                source_ids=issue.source_ids,
                remediation_hint=labels.humanise(issue.remediation_hint),
            )
            for issue in result.data_quality_issues
        ],
        source_ids=result.source_ids,
        as_of_date=result.as_of_date,
        calculated_at=result.calculated_at,
        assumptions_or_limitations=labels.humanise_all(result.assumptions_or_limitations),
    )


def alert_out(alert: EarlyWarningAlert) -> AlertOut:
    """Present an early-warning alert."""
    return AlertOut(
        alert_id=alert.alert_id,
        project_id=alert.project_id,
        severity=alert.severity,
        alert_type=alert.alert_type,
        alert_type_label=labels.alert_type_label(alert.alert_type),
        title=labels.humanise(alert.title),
        explanation=labels.humanise(alert.explanation),
        source_ids=alert.source_ids,
        recommended_next_step=labels.humanise(alert.recommended_next_step),
        as_of_date=alert.as_of_date,
        detected_at=alert.detected_at,
    )


def change_impact_out(result: ChangeImpactResult) -> ChangeImpactOut:
    """Present a change-impact result."""
    return ChangeImpactOut(
        change_request_id=result.change_request_id,
        requirement_id=result.requirement_id,
        affected_task_ids=result.affected_task_ids,
        affected_test_case_ids=result.affected_test_case_ids,
        affected_dependency_ids=result.affected_dependency_ids,
        affected_milestone_ids=result.affected_milestone_ids,
        estimated_schedule_impact_days=result.estimated_schedule_impact_days,
        risk_level=result.risk_level,
        explanation=labels.humanise(result.deterministic_explanation),
        source_ids=result.source_ids,
        as_of_date=result.as_of_date,
        calculated_at=result.calculated_at,
        assumptions_or_limitations=labels.humanise_all(result.assumptions_or_limitations),
        evidence_status=result.evidence_status,
    )


# --------------------------------------------------------------------------- dashboards
class PortfolioAnalysisError(RuntimeError):
    """A project could not be represented in the portfolio dashboard."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f"Portfolio analysis failed for project {project_id}.")


def project_dashboard(
    project_id: str, portfolio: PortfolioData, as_of_date: date
) -> ProjectDashboard:
    """Assemble one project's full intelligence view."""
    project = portfolio.get_project(project_id)
    if project is None:
        raise KeyError(project_id)

    health = calculate_project_health(project_id, portfolio, as_of_date)
    confidence = calculate_project_confidence(project_id, portfolio, as_of_date)
    alerts = generate_early_warnings(project_id, portfolio, as_of_date)

    return ProjectDashboard(
        project=project_out(project),
        assessment=assess_project_evidence(project_id, portfolio),
        health=health_out(health),
        confidence=confidence_out(confidence),
        alerts=[alert_out(alert) for alert in alerts],
    )


def _matches_portfolio_view(
    project: ProjectSummary, alerts: list[EarlyWarningAlert], filters: PortfolioFilters
) -> bool:
    """Select existing results without recalculating a band or severity."""
    if (
        (filters.health_band or filters.confidence_band)
        and project.assessment is not None
        and not project.assessment.is_assessed
    ):
        return False
    exact_fields = {
        "project_id": "project_id",
        "health_band": "health_band",
        "confidence_band": "confidence_band",
        "domain": "domain",
        "manager": "project_manager",
        "phase": "project_phase",
        "priority": "business_priority",
    }
    for filter_field, record_field in exact_fields.items():
        expected = getattr(filters, filter_field)
        if expected is not None and getattr(project, record_field) != expected:
            return False
    if filters.alert_severity and not any(
        alert.severity == filters.alert_severity for alert in alerts
    ):
        return False
    if filters.needs_attention is not None and (
        project.needs_attention != filters.needs_attention
        or (project.assessment is not None and not project.assessment.is_assessed)
    ):
        return False
    forecast = project.forecast_end_date
    if filters.forecast_after and (forecast is None or forecast < filters.forecast_after):
        return False
    return not (
        filters.forecast_before and (forecast is None or forecast > filters.forecast_before)
    )


def _first_failing_project(portfolio: PortfolioData, as_of_date: date) -> str:
    """Identify which project's records stopped the portfolio alert run."""
    for project in portfolio.projects:
        try:
            generate_early_warnings(project.project_id, portfolio, as_of_date)
        except Exception:  # noqa: BLE001 - the failure is re-raised by the caller
            return project.project_id
    return "portfolio"


def portfolio_dashboard(
    portfolio: PortfolioData, as_of_date: date, filters: PortfolioFilters | None = None
) -> PortfolioDashboard:
    """Assemble the portfolio overview without silently omitting failed projects."""
    try:
        alerts = generate_portfolio_early_warnings(portfolio, as_of_date)
    except Exception as exc:
        raise PortfolioAnalysisError(_first_failing_project(portfolio, as_of_date)) from exc
    alerts_by_project: dict[str, list[EarlyWarningAlert]] = {}
    for alert in alerts:
        alerts_by_project.setdefault(alert.project_id, []).append(alert)

    summaries: list[ProjectSummary] = []
    health_bands = BandCounts()
    confidence_bands = ConfidenceBandCounts()

    for project in portfolio.projects:
        try:
            health = calculate_project_health(project.project_id, portfolio, as_of_date)
            confidence = calculate_project_confidence(project.project_id, portfolio, as_of_date)
        except Exception as exc:
            raise PortfolioAnalysisError(project.project_id) from exc

        project_alerts = alerts_by_project.get(project.project_id, [])
        summary = ProjectSummary(
            project_id=project.project_id,
            project_name=project.project_name,
            domain=project.domain,
            project_manager=project.project_manager,
            project_phase=project.project_phase,
            business_priority=project.business_priority,
            forecast_end_date=project.forecast_end_date,
            health_score=health.overall_score,
            health_band=health.health_band,
            confidence_score=confidence.overall_score,
            confidence_band=confidence.confidence_band,
            open_alert_count=len(project_alerts),
            critical_alert_count=sum(1 for alert in project_alerts if alert.severity == "Critical"),
            needs_attention=needs_attention(
                health.health_band, (alert.severity for alert in project_alerts)
            ),
            assessment=assess_project_evidence(project.project_id, portfolio),
        )
        if filters is not None and not _matches_portfolio_view(summary, project_alerts, filters):
            continue
        summaries.append(summary)
        if summary.assessment.is_assessed:
            _increment(health_bands, health.health_band)
            _increment(confidence_bands, confidence.confidence_band)

    visible_ids = {summary.project_id for summary in summaries}
    alerts = [alert for alert in alerts if alert.project_id in visible_ids]
    return PortfolioDashboard(
        as_of_date=as_of_date,
        project_count=len(summaries),
        unassessed_count=sum(not summary.assessment.is_assessed for summary in summaries),
        health_bands=health_bands,
        confidence_bands=confidence_bands,
        alert_severities=_severity_counts(alerts),
        project_phases=dict(
            sorted(
                {
                    phase: sum(1 for project in summaries if project.project_phase == phase)
                    for phase in {project.project_phase for project in summaries}
                }.items()
            )
        ),
        project_domains=dict(
            sorted(
                {
                    domain: sum(1 for project in summaries if project.domain == domain)
                    for domain in {project.domain for project in summaries}
                }.items()
            )
        ),
        projects=sorted(summaries, key=lambda summary: summary.health_score),
        top_alerts=[alert_out(alert) for alert in alerts[:_TOP_ALERT_LIMIT]],
    )


# --------------------------------------------------------------------------- traceability
_VERIFIED_LINK_TYPE = "verified_by"


def traceability_matrix(
    portfolio: PortfolioData, as_of_date: date, project_id: str | None = None
) -> TraceabilityMatrix:
    """Build the requirement-to-test coverage view from trace links."""
    requirements = [
        requirement
        for requirement in portfolio.requirements
        if project_id is None or requirement.project_id == project_id
    ]
    tests_by_id = {test.test_case_id: test for test in portfolio.test_cases}

    rows: list[TraceabilityRow] = []
    status_counts: dict[str, int] = {}

    for requirement in requirements:
        linked_ids = [
            link.target_id
            for link in portfolio.trace_links
            if link.source_id == requirement.requirement_id
            and link.link_type == _VERIFIED_LINK_TYPE
        ]
        linked_tests = [tests_by_id[test_id] for test_id in linked_ids if test_id in tests_by_id]
        status = trace_status(
            [(test.status, test.has_verification_evidence) for test in linked_tests]
        )
        status_counts[status] = status_counts.get(status, 0) + 1

        rows.append(
            TraceabilityRow(
                requirement_id=requirement.requirement_id,
                requirement_text=requirement.requirement_text,
                project_id=requirement.project_id,
                requirement_status=requirement.status,
                priority=requirement.priority,
                owner=requirement.owner,
                linked_test_case_ids=sorted(linked_ids),
                verified_test_case_ids=sorted(
                    test.test_case_id
                    for test in linked_tests
                    if normalize_status(test.status, StatusDomain.TEST_CASE) == "Passed"
                    and test.has_verification_evidence
                ),
                trace_status=status,
                open_change_request_ids=sorted(
                    change.change_request_id
                    for change in portfolio.change_requests
                    if change.requirement_id == requirement.requirement_id
                    and not is_change_request_decided(change.status)
                ),
            )
        )

    verified = status_counts.get("Verified", 0)
    coverage = safe_div(verified * 100, len(rows), default=0.0)

    return TraceabilityMatrix(
        as_of_date=as_of_date,
        project_id=project_id,
        total_requirements=len(rows),
        status_counts=status_counts,
        coverage_percent=round(coverage, 1),
        rows=sorted(rows, key=lambda row: row.requirement_id),
    )


# --------------------------------------------------------------------------- scenarios
def scenario_out(result: ScenarioResult, portfolio: PortfolioData) -> ScenarioOut:
    """Present a scenario simulation, resolving ids to names for the reader."""
    names = {project.project_id: project.project_name for project in portfolio.projects}
    record_names = {task.task_id: task.task_name for task in portfolio.tasks}
    record_names.update(
        {milestone.milestone_id: milestone.milestone_name for milestone in portfolio.milestones}
    )
    dependency = next(
        (d for d in portfolio.dependencies if d.dependency_id == result.dependency_id), None
    )

    return ScenarioOut(
        scenario_type=result.scenario_type,
        dependency_id=result.dependency_id,
        dependency_name=dependency.dependency_name if dependency else result.dependency_id,
        additional_delay_days=result.additional_delay_days,
        baseline_delay_days=result.baseline_delay_days,
        scenario_delay_days=result.scenario_delay_days,
        affected_projects=[
            ScenarioComparisonOut(
                project_id=comparison.project_id,
                project_name=names.get(comparison.project_id, comparison.project_id),
                baseline_health_score=comparison.baseline_health_score,
                baseline_health_band=comparison.baseline_health_band,
                scenario_health_score=comparison.scenario_health_score,
                scenario_health_band=comparison.scenario_health_band,
                health_score_delta=comparison.health_score_delta,
                baseline_confidence_score=comparison.baseline_confidence_score,
                baseline_confidence_band=comparison.baseline_confidence_band,
                scenario_confidence_score=comparison.scenario_confidence_score,
                scenario_confidence_band=comparison.scenario_confidence_band,
                confidence_score_delta=comparison.confidence_score_delta,
                baseline_alert_counts=_severity_counts_from_map(comparison.baseline_alert_counts),
                scenario_alert_counts=_severity_counts_from_map(comparison.scenario_alert_counts),
                new_alert_ids=comparison.new_alert_ids,
                resolved_alert_ids=comparison.resolved_alert_ids,
                changed_alert_ids=comparison.changed_alert_ids,
                baseline_forecast_end_date=comparison.baseline_forecast_end_date,
                scenario_forecast_end_date=comparison.scenario_forecast_end_date,
                forecast_end_shift_days=comparison.forecast_end_shift_days,
                factor_deltas=[
                    ScenarioFactorDeltaOut(
                        factor=item.factor,
                        factor_label=labels.health_factor_label(item.factor),
                        baseline_score=item.baseline_score,
                        scenario_score=item.scenario_score,
                        score_delta=item.score_delta,
                        weight=item.weight,
                        weighted_contribution=item.weighted_contribution,
                    )
                    for item in comparison.factor_deltas
                ],
            )
            for comparison in result.affected_projects
        ],
        explanation=labels.humanise(result.deterministic_explanation),
        source_ids=result.source_ids,
        as_of_date=result.as_of_date,
        calculated_at=result.calculated_at,
        assumptions_or_limitations=labels.humanise_all(result.assumptions_or_limitations),
        interventions=[
            ScenarioInterventionOut(
                intervention_type=item.intervention_type,
                target_id=item.target_id,
                value=item.value,
                unit=item.unit,
                note=item.note,
            )
            for item in result.interventions
        ],
        schedule_movements=[
            ScheduleMovementOut(
                record_type=item.record_type,
                record_id=item.record_id,
                record_name=record_names.get(item.record_id, item.record_id),
                original_date=item.original_date,
                scenario_date=item.scenario_date,
                shift_days=item.shift_days,
                controlling_dependency_id=item.controlling_dependency_id,
                controlling_predecessor_id=item.controlling_predecessor_id,
                propagation_hop=item.propagation_hop,
            )
            for item in result.schedule_movements
        ],
        calculation_version=result.calculation_version,
        decision_brief=[
            ScenarioInsightOut(
                kind=item.kind,
                project_id=item.project_id,
                headline=labels.humanise(item.headline),
                detail=labels.humanise(item.detail),
                source_ids=item.source_ids,
            )
            for item in result.decision_brief
        ],
    )


def run_scenario(
    dependency_id: str,
    additional_delay_days: int,
    portfolio: PortfolioData,
    as_of_date: date,
) -> ScenarioOut:
    """Run a dependency-delay simulation and present the comparison."""
    result = simulate_dependency_delay(dependency_id, additional_delay_days, portfolio, as_of_date)
    return scenario_out(result, portfolio)


def run_multi_event_scenario(
    interventions: list[ScenarioIntervention],
    portfolio: PortfolioData,
    as_of_date: date,
) -> ScenarioOut:
    """Run a scenario carrying several simultaneous interventions."""
    return scenario_out(
        scenario_engine.run_scenario(interventions, portfolio, as_of_date), portfolio
    )


def run_sensitivity(
    intervention_type: ScenarioInterventionType,
    target_id: str,
    portfolio: PortfolioData,
    as_of_date: date,
    values: list[int] | None = None,
) -> ScenarioSensitivityOut:
    """Re-run one intervention across a range and present where outcomes change."""
    result = scenario_engine.analyse_sensitivity(
        intervention_type, target_id, portfolio, as_of_date, values
    )
    return ScenarioSensitivityOut(
        intervention_type=result.intervention_type,
        target_id=result.target_id,
        project_id=result.project_id,
        unit=result.unit,
        tested_values=result.tested_values,
        health_scores=result.health_scores,
        forecast_shift_days=result.forecast_shift_days,
        is_responsive=result.is_responsive,
        saturated_at_value=result.saturated_at_value,
        thresholds=[
            ScenarioThresholdOut(
                outcome=item.outcome,
                occurs_at_value=item.occurs_at_value,
                unit=item.unit,
                tested_values=item.tested_values,
                explanation=item.explanation,
            )
            for item in result.thresholds
        ],
        assumptions_or_limitations=labels.humanise_all(result.assumptions_or_limitations),
    )


def change_impact(
    change_request_id: str, portfolio: PortfolioData, as_of_date: date
) -> ChangeImpactOut:
    """Run the change-impact engine and present the result."""
    return change_impact_out(calculate_change_impact(change_request_id, portfolio, as_of_date))
