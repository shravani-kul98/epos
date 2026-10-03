"""Tests for the deterministic Project Health Score engine."""

from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from src.data_loader import PortfolioData, load_portfolio
from src.health_engine import calculate_project_health, weighted_overall_score
from src.scoring_rules import HEALTH_FACTORS
from src.utils import health_band, reference_timestamp
from src.validators import DataValidationError

TEST_PROJECT_ID = "P-TEST"


def _healthy_portfolio(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_risk,
    make_dependency,
    make_resource,
    make_action,
) -> PortfolioData:
    return make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone()],
        tasks=[make_task()],
        risks=[make_risk()],
        dependencies=[make_dependency()],
        resources=[make_resource()],
        actions=[make_action()],
    )


def test_healthy_project_is_green_with_no_critical_drivers(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_risk,
    make_dependency,
    make_resource,
    make_action,
    as_of_date,
):
    portfolio = _healthy_portfolio(
        make_portfolio,
        make_project,
        make_milestone,
        make_task,
        make_risk,
        make_dependency,
        make_resource,
        make_action,
    )
    result = calculate_project_health(TEST_PROJECT_ID, portfolio, as_of_date)

    assert result.health_band == "Green"
    assert result.overall_score == 100.0
    assert all(score == 100.0 for score in result.factor_scores.values())
    assert result.critical_drivers == []


@pytest.mark.parametrize(
    ("slip", "expected"),
    [(0, 100), (1, 85), (5, 85), (6, 70), (10, 70), (11, 50), (20, 50), (21, 25)],
)
def test_schedule_performance_boundaries(make_project, make_portfolio, as_of_date, slip, expected):
    baseline = date(2026, 12, 31)
    project = make_project(
        baseline_end_date=baseline, forecast_end_date=baseline + timedelta(days=slip)
    )
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[project]), as_of_date
    )
    assert result.factor_scores["schedule_performance"] == expected


@pytest.mark.parametrize("missing", ["baseline_end_date", "forecast_end_date"])
def test_missing_schedule_dates_use_fallback(make_project, make_portfolio, as_of_date, missing):
    project = make_project(**{missing: None})
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[project]), as_of_date
    )
    assert result.factor_scores["schedule_performance"] == 50
    assert any(
        "cannot be fully assessed" in limitation for limitation in result.assumptions_or_limitations
    )


def test_schedule_slip_creates_driver(make_project, make_portfolio, as_of_date):
    baseline = date(2026, 12, 1)
    project = make_project(
        baseline_end_date=baseline, forecast_end_date=baseline + timedelta(days=30)
    )
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[project]), as_of_date
    )
    schedule_drivers = [
        d for d in result.critical_drivers if d.factor_name == "schedule_performance"
    ]
    assert schedule_drivers and schedule_drivers[0].severity == "Critical"
    assert TEST_PROJECT_ID in schedule_drivers[0].source_ids


def test_delayed_critical_milestone_penalty_and_driver(
    make_project, make_milestone, make_portfolio, as_of_date
):
    milestone = make_milestone(
        milestone_id="M-CRIT",
        criticality="Critical",
        baseline_date=date(2026, 6, 30),
        forecast_date=date(2026, 8, 15),
        status="Delayed",
    )
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], milestones=[milestone]),
        as_of_date,
    )
    # Critical slip (-25) plus Delayed (-15) from a base of 100.
    assert result.factor_scores["milestone_readiness"] == 60.0
    drivers = [d for d in result.critical_drivers if d.factor_name == "milestone_readiness"]
    assert drivers and drivers[0].severity == "Critical"
    assert "M-CRIT" in drivers[0].source_ids


def test_at_risk_medium_milestone_penalty(make_project, make_milestone, make_portfolio, as_of_date):
    milestone = make_milestone(
        criticality="Medium",
        baseline_date=date(2026, 6, 30),
        forecast_date=date(2026, 7, 30),
        status="At Risk",
    )
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], milestones=[milestone]),
        as_of_date,
    )
    # Medium slip (-10) plus At Risk (-8).
    assert result.factor_scores["milestone_readiness"] == 82.0


def test_no_milestones_uses_fallback(make_project, make_portfolio, as_of_date):
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()]), as_of_date
    )
    assert result.factor_scores["milestone_readiness"] == 50
    assert any("No milestones" in lim for lim in result.assumptions_or_limitations)


def test_blocked_task_on_critical_milestone(
    make_project, make_milestone, make_task, make_portfolio, as_of_date
):
    milestone = make_milestone(milestone_id="M-CRIT", criticality="Critical")
    task = make_task(task_id="T-BLK", milestone_id="M-CRIT", status="Blocked", is_blocked=True)
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], milestones=[milestone], tasks=[task]),
        as_of_date,
    )
    assert result.factor_scores["task_execution"] == 85.0
    drivers = [d for d in result.critical_drivers if d.factor_name == "task_execution"]
    assert drivers and drivers[0].severity == "Critical"
    assert {"T-BLK", "M-CRIT"} <= set(drivers[0].source_ids)


def test_overdue_task_on_critical_milestone(
    make_project, make_milestone, make_task, make_portfolio, as_of_date
):
    milestone = make_milestone(milestone_id="M-CRIT", criticality="Critical")
    task = make_task(
        milestone_id="M-CRIT",
        forecast_end_date=date(2026, 7, 1),
        planned_end_date=date(2026, 12, 1),
        completion_percent=80,
    )
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], milestones=[milestone], tasks=[task]),
        as_of_date,
    )
    # Overdue (-6) plus High/Critical extra (-6).
    assert result.factor_scores["task_execution"] == 88.0


def test_low_completion_only_penalised_when_planned_end_reached(
    make_project, make_milestone, make_task, make_portfolio, as_of_date
):
    milestone = make_milestone()
    reached = make_task(
        task_id="T-LOW",
        planned_end_date=date(2026, 7, 1),
        completion_percent=30,
        forecast_end_date=date(2026, 12, 1),
    )
    future = make_task(
        task_id="T-FUT",
        planned_end_date=date(2026, 12, 1),
        completion_percent=10,
        forecast_end_date=date(2026, 12, 1),
    )
    reached_result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], milestones=[milestone], tasks=[reached]),
        as_of_date,
    )
    future_result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], milestones=[milestone], tasks=[future]),
        as_of_date,
    )
    assert reached_result.factor_scores["task_execution"] == 95.0
    assert future_result.factor_scores["task_execution"] == 100.0


def test_task_missing_milestone_reference_is_non_critical(
    make_project, make_task, make_portfolio, as_of_date
):
    task = make_task(task_id="T-ORPH", milestone_id="M-UNKNOWN", is_blocked=True)
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], tasks=[task]),
        as_of_date,
    )
    # Non-critical blocked penalty is -8.
    assert result.factor_scores["task_execution"] == 92.0
    assert any("M-UNKNOWN" in lim for lim in result.assumptions_or_limitations)


@pytest.mark.parametrize(
    ("probability", "impact", "owner", "mitigation", "expected"),
    [
        (5, 5, None, "Not Started", 65.0),
        (4, 4, None, "In Progress", 85.0),
        (3, 3, "Pat Owner", "In Progress", 96.0),
        (1, 5, "Pat Owner", "In Progress", 100.0),
    ],
)
def test_risk_exposure_bands(
    make_project,
    make_risk,
    make_portfolio,
    as_of_date,
    probability,
    impact,
    owner,
    mitigation,
    expected,
):
    risk = make_risk(
        probability=probability,
        impact=impact,
        mitigation_owner=owner,
        mitigation_status=mitigation,
        status="Open",
    )
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], risks=[risk]), as_of_date
    )
    assert result.factor_scores["risk_exposure"] == expected


def test_mitigating_risk_uses_exposure_rules(make_project, make_risk, make_portfolio, as_of_date):
    risk = make_risk(
        probability=5,
        impact=5,
        mitigation_owner=None,
        mitigation_status="Not Started",
        status="Mitigating",
    )

    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], risks=[risk]), as_of_date
    )

    assert result.factor_scores["risk_exposure"] == 65.0
    assert any("remains Mitigating" in text for text in result.factor_explanations["risk_exposure"])


@pytest.mark.parametrize("status", ["Closed", "Accepted"])
def test_non_open_risks_are_not_penalised(
    make_project, make_risk, make_portfolio, as_of_date, status
):
    risk = make_risk(probability=5, impact=5, mitigation_owner=None, status=status)
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], risks=[risk]), as_of_date
    )
    assert result.factor_scores["risk_exposure"] == 100.0


def test_dependency_table_unavailable_fallback(make_project, make_portfolio, as_of_date):
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()]), as_of_date
    )
    assert result.factor_scores["dependency_status"] == 70
    assert any("No dependency data" in lim for lim in result.assumptions_or_limitations)


def test_dependency_table_present_but_project_has_none(
    make_project, make_dependency, make_portfolio, as_of_date
):
    other = make_dependency(dependency_id="D-OTHER", project_id="P-OTHER")
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], dependencies=[other]),
        as_of_date,
    )
    assert result.factor_scores["dependency_status"] == 100.0


def test_delayed_critical_dependency(make_project, make_dependency, make_portfolio, as_of_date):
    dependency = make_dependency(
        dependency_id="D-CRIT", criticality="Critical", status="Delayed", delay_days=5
    )
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], dependencies=[dependency]),
        as_of_date,
    )
    # 20 for a Critical delay plus 8 because the dependency is reported Delayed.
    assert result.factor_scores["dependency_status"] == 72.0
    drivers = [d for d in result.critical_drivers if d.factor_name == "dependency_status"]
    assert drivers and drivers[0].severity == "Critical"


@pytest.mark.parametrize("criticality", ["Low", "Medium", "High", "Critical"])
def test_worse_dependency_evidence_never_scores_better(
    criticality, make_project, make_dependency, make_portfolio, as_of_date
):
    def score(status: str, delay_days: int) -> float:
        dependency = make_dependency(
            dependency_id="D-MONO", criticality=criticality, status=status, delay_days=delay_days
        )
        return calculate_project_health(
            TEST_PROJECT_ID,
            make_portfolio(projects=[make_project()], dependencies=[dependency]),
            as_of_date,
        ).factor_scores["dependency_status"]

    assert score("Delayed", 10) <= score("At Risk", 10) <= score("On Track", 10)
    delays = [score("Delayed", days) for days in (1, 30, 61, 91, 181, 400)]
    assert delays == sorted(delays, reverse=True)
    assert delays[-1] < delays[0]


def test_blocked_high_and_at_risk_dependencies(
    make_project, make_dependency, make_portfolio, as_of_date
):
    blocked = make_dependency(
        dependency_id="D-BLK", criticality="High", status="Blocked", delay_days=0
    )
    at_risk = make_dependency(
        dependency_id="D-AR", criticality="Medium", status="At Risk", delay_days=0
    )
    blocked_result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], dependencies=[blocked]),
        as_of_date,
    )
    at_risk_result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], dependencies=[at_risk]),
        as_of_date,
    )
    assert blocked_result.factor_scores["dependency_status"] == 90.0
    assert at_risk_result.factor_scores["dependency_status"] == 95.0


@pytest.mark.parametrize(
    ("allocated", "capacity", "penalty"),
    [
        (90, 100, 0),
        (9001, 10000, 3),
        (100, 100, 3),
        (10001, 10000, 10),
        (110, 100, 10),
        (11001, 10000, 18),
        (125, 100, 18),
        (12501, 10000, 25),
    ],
)
def test_resource_utilisation_boundaries(
    make_project, make_resource, make_portfolio, as_of_date, allocated, capacity, penalty
):
    resource = make_resource(allocated_hours=allocated, capacity_hours=capacity)
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], resources=[resource]),
        as_of_date,
    )
    assert result.factor_scores["resource_capacity"] == 100 - penalty


def test_resource_table_unavailable_fallback(make_project, make_portfolio, as_of_date):
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()]), as_of_date
    )
    assert result.factor_scores["resource_capacity"] == 70


@pytest.mark.parametrize(
    ("priority", "penalty"),
    [("Low", 2), ("Medium", 4), ("High", 7), ("Critical", 10)],
)
def test_overdue_action_penalties(
    make_project, make_action, make_portfolio, as_of_date, priority, penalty
):
    action = make_action(due_date=date(2026, 8, 1), priority=priority, owner="Pat Owner")
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], actions=[action]),
        as_of_date,
    )
    assert result.factor_scores["action_closure"] == 100 - penalty


def test_ownerless_active_action_penalty(make_project, make_action, make_portfolio, as_of_date):
    action = make_action(owner=None, due_date=date(2026, 12, 31))
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], actions=[action]),
        as_of_date,
    )
    assert result.factor_scores["action_closure"] == 95.0


def test_complete_action_is_excluded(make_project, make_action, make_portfolio, as_of_date):
    action = make_action(status="Complete", due_date=date(2026, 8, 1), priority="High")
    result = calculate_project_health(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], actions=[action]),
        as_of_date,
    )
    assert result.factor_scores["action_closure"] == 100.0


def test_action_table_unavailable_fallback(make_project, make_portfolio, as_of_date):
    result = calculate_project_health(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()]), as_of_date
    )
    assert result.factor_scores["action_closure"] == 70


def test_weighted_overall_score_applies_weights_exactly():
    scores = dict.fromkeys(HEALTH_FACTORS, 0.0)
    scores["schedule_performance"] = 100.0
    assert weighted_overall_score(scores) == 25.0
    assert weighted_overall_score(dict.fromkeys(HEALTH_FACTORS, 100.0)) == 100.0


def test_weighted_overall_score_rejects_wrong_keys():
    with pytest.raises(ValueError):
        weighted_overall_score({"schedule_performance": 100.0})


@pytest.mark.parametrize(
    ("score", "band"),
    [(80.0, "Green"), (79.99, "Amber"), (60.0, "Amber"), (59.99, "Red")],
)
def test_health_band_boundaries(score, band):
    assert health_band(score) == band


def test_result_integrity(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_risk,
    make_dependency,
    make_resource,
    make_action,
    as_of_date,
):
    portfolio = _healthy_portfolio(
        make_portfolio,
        make_project,
        make_milestone,
        make_task,
        make_risk,
        make_dependency,
        make_resource,
        make_action,
    )
    result = calculate_project_health(TEST_PROJECT_ID, portfolio, as_of_date)

    assert set(result.factor_scores) == set(HEALTH_FACTORS)
    assert set(result.factor_weights) == set(HEALTH_FACTORS)
    assert round(sum(result.factor_weights.values()), 6) == 1.0
    assert result.source_ids == sorted(set(result.source_ids))
    assert result.calculated_at == reference_timestamp(as_of_date)
    assert all(0.0 <= score <= 100.0 for score in result.factor_scores.values())
    assert 0.0 <= result.overall_score <= 100.0


def test_unknown_project_raises(portfolio):
    with pytest.raises(DataValidationError) as exc:
        calculate_project_health("P-NONE", portfolio, date(2026, 8, 25))
    assert "P-NONE" in str(exc.value)


def test_engine_does_not_mutate_portfolio(portfolio):
    before = copy.deepcopy(portfolio)
    calculate_project_health("P-002", portfolio, date(2026, 8, 25))
    assert [p.model_dump() for p in portfolio.projects] == [p.model_dump() for p in before.projects]
    assert [m.model_dump() for m in portfolio.milestones] == [
        m.model_dump() for m in before.milestones
    ]
    assert [t.model_dump() for t in portfolio.tasks] == [t.model_dump() for t in before.tasks]
    assert [r.model_dump() for r in portfolio.risks] == [r.model_dump() for r in before.risks]


def test_real_portfolio_projects_differ_and_are_isolated():
    portfolio = load_portfolio()
    as_of = date(2026, 8, 25)
    p002 = calculate_project_health("P-002", portfolio, as_of)
    p007 = calculate_project_health("P-007", portfolio, as_of)

    assert p002.health_band == "Red"
    assert p007.health_band == "Red"
    assert p002.overall_score != p007.overall_score

    assert "R-2001" in p002.source_ids
    assert "R-2001" not in p007.source_ids
    assert "R-7001" in p007.source_ids
    assert "R-7001" not in p002.source_ids

    assert all(
        sid.startswith(("P-002", "M-2", "T-2", "R-2", "D-2", "RES-2", "A-2"))
        for sid in p002.source_ids
    )
    assert all(
        sid.startswith(("P-007", "M-7", "T-7", "R-7", "D-7", "RES-7", "A-7"))
        for sid in p007.source_ids
    )
