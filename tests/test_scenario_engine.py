"""Tests for the non-mutating what-if scenario engine."""

from __future__ import annotations

import copy
from datetime import date

import pytest

from src import scoring_rules as sr
from src.confidence_engine import calculate_project_confidence
from src.data_loader import load_portfolio
from src.health_engine import calculate_project_health
from src.risk_engine import generate_early_warnings
from src.scenario_engine import SCENARIO_DEPENDENCY_DELAY, simulate_dependency_delay
from src.utils import reference_timestamp
from src.validators import DataValidationError

AS_OF = date(2026, 8, 25)


def test_simulation_changes_health_and_alerts(portfolio):
    # D-7002 links two Critical milestones and is On Track at baseline, so delaying it bites.
    result = simulate_dependency_delay("D-7002", 30, portfolio, AS_OF)
    comparison = result.affected_projects[0]

    assert result.scenario_type == SCENARIO_DEPENDENCY_DELAY
    assert comparison.project_id == "P-007"
    assert result.baseline_delay_days == 0
    assert result.scenario_delay_days == 30
    assert comparison.baseline_health_score == 51.15
    assert comparison.scenario_health_score == 48.35
    assert comparison.health_score_delta == -2.8
    assert sum(comparison.baseline_alert_counts.values()) == 9
    assert sum(comparison.scenario_alert_counts.values()) == 11
    assert len(comparison.new_alert_ids) == 2
    assert comparison.resolved_alert_ids == []


def test_simulation_changes_health_for_second_project(portfolio):
    result = simulate_dependency_delay("D-2002", 30, portfolio, AS_OF)
    comparison = result.affected_projects[0]
    assert comparison.project_id == "P-002"
    assert comparison.baseline_health_score == 49.9
    # Propagation pushes T-2002 past today, which removes its overdue penalty. The Delayed status
    # penalty outweighs that, so the delay lowers health, and the engine still reports the
    # task movement rather than presenting it as an improvement.
    assert comparison.scenario_health_score == 49.4
    assert comparison.health_score_delta < 0
    assert any(
        "rather than because delivery improved" in limit
        for limit in result.assumptions_or_limitations
    )


def test_already_delayed_dependency_reports_no_change(portfolio):
    # D-2001 is already Delayed, Critical and 30 days late; 30 more days crosses no threshold.
    result = simulate_dependency_delay("D-2001", 30, portfolio, AS_OF)
    comparison = result.affected_projects[0]
    assert comparison.health_score_delta == 0.0
    assert any(
        "crosses no scoring threshold" in limit for limit in result.assumptions_or_limitations
    )


def test_a_longer_dependency_delay_never_scores_better(portfolio):
    deltas = [
        simulate_dependency_delay("D-2001", days, portfolio, AS_OF)
        .affected_projects[0]
        .health_score_delta
        for days in (10, 40, 70, 160, 200)
    ]
    assert deltas == sorted(deltas, reverse=True)
    assert deltas[-1] < 0


def test_alert_severity_change_is_reported(
    make_project, make_milestone, make_dependency, make_portfolio
):
    milestone = make_milestone(milestone_id="M-SCEN", criticality="Critical")
    dependency = make_dependency(
        dependency_id="D-SCEN",
        successor_type="Milestone",
        successor_id="M-SCEN",
        status="Delayed",
        delay_days=sr.ALERT_DEPENDENCY_LARGE_DELAY_DAYS,
        criticality="Critical",
    )
    portfolio = make_portfolio(
        projects=[make_project()], milestones=[milestone], dependencies=[dependency]
    )

    result = simulate_dependency_delay("D-SCEN", 1, portfolio, AS_OF)
    comparison = result.affected_projects[0]

    assert len(comparison.changed_alert_ids) == 1
    assert comparison.baseline_alert_counts["High"] == 1
    assert comparison.scenario_alert_counts["Critical"] == 1


def test_baseline_data_is_not_mutated():
    portfolio = load_portfolio()
    snapshot = copy.deepcopy(portfolio)
    simulate_dependency_delay("D-7002", 45, portfolio, AS_OF)
    for attr in (
        "projects",
        "milestones",
        "tasks",
        "risks",
        "dependencies",
        "actions",
        "resources",
        "requirements",
        "test_cases",
        "trace_links",
        "change_requests",
    ):
        after = [r.model_dump() for r in getattr(portfolio, attr)]
        before = [r.model_dump() for r in getattr(snapshot, attr)]
        assert after == before


def test_reported_baseline_matches_the_real_engines(portfolio):
    result = simulate_dependency_delay("D-7002", 30, portfolio, AS_OF)
    comparison = result.affected_projects[0]

    health = calculate_project_health("P-007", portfolio, AS_OF)
    confidence = calculate_project_confidence("P-007", portfolio, AS_OF)
    alerts = generate_early_warnings("P-007", portfolio, AS_OF)

    assert comparison.baseline_health_score == health.overall_score
    assert comparison.baseline_health_band == health.health_band
    assert comparison.baseline_confidence_score == confidence.overall_score
    assert comparison.baseline_confidence_band == confidence.confidence_band
    assert sum(comparison.baseline_alert_counts.values()) == len(alerts)


def test_unknown_dependency_raises(portfolio):
    with pytest.raises(DataValidationError) as exc:
        simulate_dependency_delay("D-NONE", 10, portfolio, AS_OF)
    assert "D-NONE" in str(exc.value)


@pytest.mark.parametrize(
    "delay", [0, -1, sr.SCENARIO_MAX_DELAY_DAYS + 1, sr.SCENARIO_MIN_DELAY_DAYS - 1]
)
def test_invalid_delay_raises(portfolio, delay):
    with pytest.raises(DataValidationError) as exc:
        simulate_dependency_delay("D-7002", delay, portfolio, AS_OF)
    assert "additional_delay_days" in str(exc.value)


@pytest.mark.parametrize("delay", [sr.SCENARIO_MIN_DELAY_DAYS, sr.SCENARIO_MAX_DELAY_DAYS])
def test_delay_bounds_are_accepted(portfolio, delay):
    result = simulate_dependency_delay("D-7002", delay, portfolio, AS_OF)
    assert result.additional_delay_days == delay


def test_determinism(portfolio):
    first = simulate_dependency_delay("D-7002", 30, portfolio, AS_OF)
    second = simulate_dependency_delay("D-7002", 30, portfolio, AS_OF)
    assert first.model_dump() == second.model_dump()
    assert first.calculated_at == reference_timestamp(AS_OF)


def test_source_ids_are_real_records(portfolio):
    result = simulate_dependency_delay("D-7001", 10, portfolio, AS_OF)
    known = (
        portfolio.project_ids
        | {d.dependency_id for d in portfolio.dependencies}
        | {t.task_id for t in portfolio.tasks}
        | {m.milestone_id for m in portfolio.milestones}
    )
    assert set(result.source_ids) <= known
    assert result.source_ids == sorted(set(result.source_ids))


def test_external_endpoint_label_is_not_a_source_record(
    make_project, make_milestone, make_dependency, make_portfolio
):
    milestone = make_milestone(milestone_id="M-EXTERNAL", criticality="High")
    dependency = make_dependency(
        dependency_id="D-EXTERNAL",
        predecessor_type="Supplier",
        predecessor_id="SUPPLIER-EXTERNAL",
        successor_type="Milestone",
        successor_id="M-EXTERNAL",
    )
    portfolio = make_portfolio(
        projects=[make_project()], milestones=[milestone], dependencies=[dependency]
    )

    result = simulate_dependency_delay("D-EXTERNAL", 5, portfolio, AS_OF)

    assert result.source_ids == ["D-EXTERNAL", "M-EXTERNAL", "P-TEST"]


def test_blocked_dependency_explanation_preserves_status(
    make_project, make_milestone, make_dependency, make_portfolio
):
    milestone = make_milestone(milestone_id="M-BLOCKED", criticality="Critical")
    dependency = make_dependency(
        dependency_id="D-BLOCKED",
        successor_type="Milestone",
        successor_id="M-BLOCKED",
        status="Blocked",
    )
    portfolio = make_portfolio(
        projects=[make_project()], milestones=[milestone], dependencies=[dependency]
    )

    result = simulate_dependency_delay("D-BLOCKED", 5, portfolio, AS_OF)

    assert "leaves it Blocked" in result.deterministic_explanation
    assert "marks it Delayed" not in result.deterministic_explanation


@pytest.mark.parametrize(
    ("dependency_id", "project_id"), [("D-2002", "P-002"), ("D-7002", "P-007")]
)
def test_real_data_scenarios_are_valid(dependency_id, project_id):
    result = simulate_dependency_delay(dependency_id, 20, load_portfolio(), AS_OF)
    comparison = result.affected_projects[0]
    assert comparison.project_id == project_id
    assert dependency_id in result.deterministic_explanation
    assert 0.0 <= comparison.scenario_health_score <= 100.0
    assert any("do not modify baseline" in limit for limit in result.assumptions_or_limitations)


def test_simple_dependency_produces_valid_result(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_risk,
    make_dependency,
):
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone()],
        tasks=[make_task()],
        risks=[make_risk()],
        dependencies=[make_dependency(dependency_id="D-SIMPLE", criticality="Low")],
    )
    result = simulate_dependency_delay("D-SIMPLE", 5, portfolio, AS_OF)
    comparison = result.affected_projects[0]
    assert result.scenario_delay_days == 5
    # A Low-criticality dependency delay costs 5 points, and the simulated Delayed status 8 more,
    # at weight 0.10. Propagation also moves the successor milestone, which the milestone
    # readiness factor prices in as well.
    assert comparison.health_score_delta == -3.3
