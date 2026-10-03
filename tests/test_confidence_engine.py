"""Tests for the deterministic Data Confidence Score engine."""

from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from src.confidence_engine import (
    _completeness_score,
    calculate_portfolio_confidence,
    calculate_project_confidence,
    weighted_confidence_score,
)
from src.data_loader import load_portfolio
from src.health_engine import calculate_project_health
from src.scoring_rules import CONFIDENCE_FACTORS, RECORD_COVERAGE_COMPLETENESS_CAPS
from src.utils import confidence_band, reference_timestamp
from src.validators import DataValidationError

TEST_PROJECT_ID = "P-TEST"
AS_OF = date(2026, 8, 25)


def _full_portfolio(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_risk,
    make_dependency,
    make_resource,
    make_action,
    make_requirement,
    make_test_case,
    make_trace_link,
    make_change_request,
    **project_overrides,
):
    """A portfolio with one healthy record in every table (source reliability = 100)."""
    return make_portfolio(
        projects=[make_project(**project_overrides)],
        milestones=[make_milestone()],
        tasks=[make_task()],
        risks=[make_risk()],
        dependencies=[make_dependency()],
        resources=[make_resource()],
        actions=[make_action()],
        requirements=[make_requirement()],
        test_cases=[make_test_case()],
        trace_links=[make_trace_link()],
        change_requests=[make_change_request()],
    )


def test_fresh_complete_owned_project_is_high(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_risk,
    make_dependency,
    make_resource,
    make_action,
    make_requirement,
    make_test_case,
    make_trace_link,
    make_change_request,
):
    portfolio = _full_portfolio(
        make_portfolio,
        make_project,
        make_milestone,
        make_task,
        make_risk,
        make_dependency,
        make_resource,
        make_action,
        make_requirement,
        make_test_case,
        make_trace_link,
        make_change_request,
    )
    result = calculate_project_confidence(TEST_PROJECT_ID, portfolio, AS_OF)
    assert result.confidence_band == "High"
    assert all(score == 100.0 for score in result.factor_scores.values())
    assert all(issue.severity not in ("High", "Critical") for issue in result.data_quality_issues)


# --------------------------------------------------------------------- Factor 1
@pytest.mark.parametrize(
    ("age_days", "expected"),
    [(0, 100), (7, 100), (8, 90), (14, 90), (15, 80), (21, 80), (22, 65)],
)
def test_project_status_freshness_boundaries(make_project, make_portfolio, age_days, expected):
    project = make_project(status_update_date=AS_OF - timedelta(days=age_days))
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[project]), AS_OF
    )
    assert result.factor_scores["data_freshness"] == expected


def test_future_project_status_date_is_rejected(make_project, make_portfolio):
    project = make_project(status_update_date=AS_OF + timedelta(days=1))

    with pytest.raises(DataValidationError, match=TEST_PROJECT_ID):
        calculate_project_confidence(TEST_PROJECT_ID, make_portfolio(projects=[project]), AS_OF)


def test_future_active_record_update_date_is_rejected(make_project, make_task, make_portfolio):
    task = make_task(task_id="T-FUTURE", last_updated_date=AS_OF + timedelta(days=1))

    with pytest.raises(DataValidationError, match="T-FUTURE"):
        calculate_project_confidence(
            TEST_PROJECT_ID,
            make_portfolio(projects=[make_project()], tasks=[task]),
            AS_OF,
        )


def test_missing_project_status_is_freshness_60_with_critical_issue(make_project, make_portfolio):
    project = make_project(status_update_date=None)
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[project]), AS_OF
    )
    assert result.factor_scores["data_freshness"] == 60
    assert any(
        issue.issue_type == "missing_status_update" and issue.severity == "Critical"
        for issue in result.data_quality_issues
    )


@pytest.mark.parametrize(
    ("fresh", "stale", "expected"),
    [(10, 0, 100), (9, 1, 100), (8, 2, 90), (3, 1, 90), (7, 3, 75), (2, 2, 75), (2, 3, 60)],
)
def test_active_record_stale_percentage(
    make_project, make_task, make_portfolio, fresh, stale, expected
):
    tasks = [
        make_task(task_id=f"T-F{i}", last_updated_date=AS_OF - timedelta(days=5))
        for i in range(fresh)
    ]
    tasks += [
        make_task(task_id=f"T-S{i}", last_updated_date=AS_OF - timedelta(days=30))
        for i in range(stale)
    ]
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], tasks=tasks), AS_OF
    )
    assert result.factor_scores["data_freshness"] == expected


def test_terminal_status_excluded_from_staleness(make_project, make_task, make_portfolio):
    active_fresh = make_task(task_id="T-A", last_updated_date=AS_OF - timedelta(days=3))
    terminal_stale = make_task(
        task_id="T-DONE", status="Complete", last_updated_date=AS_OF - timedelta(days=60)
    )
    result = calculate_project_confidence(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], tasks=[active_fresh, terminal_stale]),
        AS_OF,
    )
    assert result.factor_scores["data_freshness"] == 100


def test_missing_last_updated_on_active_task(make_project, make_task, make_portfolio):
    task = make_task(task_id="T-NONE", last_updated_date=None)
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], tasks=[task]), AS_OF
    )
    assert result.factor_scores["data_freshness"] == 60
    assert any(
        issue.issue_type == "missing_last_updated" and "T-NONE" in issue.source_ids
        for issue in result.data_quality_issues
    )


def test_missing_last_updated_on_requirement_and_test_case(
    make_project, make_requirement, make_test_case, make_portfolio
):
    requirement = make_requirement(requirement_id="REQ-NONE", last_updated_date=None)
    test_case = make_test_case(test_case_id="TC-NONE", last_updated_date=None)
    result = calculate_project_confidence(
        TEST_PROJECT_ID,
        make_portfolio(
            projects=[make_project()], requirements=[requirement], test_cases=[test_case]
        ),
        AS_OF,
    )
    # Both active records missing -> 100% stale -> freshness 60.
    assert result.factor_scores["data_freshness"] == 60


# --------------------------------------------------------------------- Factor 2
@pytest.mark.parametrize(
    ("missing_percentage", "expected"),
    [
        (5.0, 100),
        (5.01, 80),
        (15.0, 80),
        (15.01, 60),
        (30.0, 60),
        (30.01, 35),
        (50.0, 35),
        (50.01, 10),
    ],
)
def test_completeness_score_boundaries(missing_percentage, expected):
    assert _completeness_score(missing_percentage) == expected


def test_critical_missing_field_is_high_issue(make_project, make_portfolio):
    project = make_project(baseline_end_date=None)
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[project]), AS_OF
    )
    assert any(
        issue.issue_type == "missing_field"
        and issue.severity == "High"
        and TEST_PROJECT_ID in issue.source_ids
        for issue in result.data_quality_issues
    )
    assert result.factor_scores["data_completeness"] < 100


def test_unrecognised_status_reduces_completeness_and_is_sourced(
    make_project, make_milestone, make_task, make_risk, make_portfolio
):
    # Tasks and risks are present so the missing-record-type cap does not mask the anomaly.
    records = {"tasks": [make_task()], "risks": [make_risk()]}
    valid = make_portfolio(
        projects=[make_project()], milestones=[make_milestone(status="On Track")], **records
    )
    anomalous = make_portfolio(
        projects=[make_project()], milestones=[make_milestone(status="Wobbling")], **records
    )

    valid_result = calculate_project_confidence(TEST_PROJECT_ID, valid, AS_OF)
    anomalous_result = calculate_project_confidence(TEST_PROJECT_ID, anomalous, AS_OF)

    assert (
        anomalous_result.factor_scores["data_completeness"]
        < valid_result.factor_scores["data_completeness"]
    )
    assert any(
        issue.issue_type == "unrecognised_status" and issue.source_ids == ["M1"]
        for issue in anomalous_result.data_quality_issues
    )


def test_a_project_without_a_plan_cannot_report_complete_evidence(make_project, make_portfolio):
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()]), AS_OF
    )
    assert result.factor_scores["data_completeness"] <= min(
        RECORD_COVERAGE_COMPLETENESS_CAPS.values()
    )
    missing = {
        issue.message
        for issue in result.data_quality_issues
        if issue.issue_type == "record_type_missing"
    }
    assert missing == {
        f"Project {TEST_PROJECT_ID} has no {record_type} recorded."
        for record_type in ("tasks", "milestones", "risks")
    }


# --------------------------------------------------------------------- Factor 3
def test_ownership_single_missing_task_owner(make_project, make_task, make_portfolio):
    task = make_task(owner=None)
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], tasks=[task]), AS_OF
    )
    assert result.factor_scores["ownership_coverage"] == 95.0


def test_ownership_task_cap(make_project, make_task, make_portfolio):
    tasks = [make_task(task_id=f"T{i}", owner=None) for i in range(6)]
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], tasks=tasks), AS_OF
    )
    assert result.factor_scores["ownership_coverage"] == 75.0


def test_ownership_risk_cap(make_project, make_risk, make_portfolio):
    risks = [make_risk(risk_id=f"R{i}", mitigation_owner=None) for i in range(4)]
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], risks=risks), AS_OF
    )
    assert result.factor_scores["ownership_coverage"] == 65.0


def test_ownership_action_cap(make_project, make_action, make_portfolio):
    actions = [make_action(action_id=f"A{i}", owner=None) for i in range(4)]
    result = calculate_project_confidence(
        TEST_PROJECT_ID, make_portfolio(projects=[make_project()], actions=actions), AS_OF
    )
    assert result.factor_scores["ownership_coverage"] == 75.0


def test_ownership_requirement_cap(make_project, make_requirement, make_portfolio):
    requirements = [make_requirement(requirement_id=f"REQ{i}", owner=None) for i in range(4)]
    result = calculate_project_confidence(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], requirements=requirements),
        AS_OF,
    )
    assert result.factor_scores["ownership_coverage"] == 85.0


def test_ownership_change_request_cap(make_project, make_change_request, make_portfolio):
    change_requests = [
        make_change_request(change_request_id=f"CR{i}", requested_by=None) for i in range(3)
    ]
    result = calculate_project_confidence(
        TEST_PROJECT_ID,
        make_portfolio(projects=[make_project()], change_requests=change_requests),
        AS_OF,
    )
    assert result.factor_scores["ownership_coverage"] == 90.0


# --------------------------------------------------------------------- Factor 4
def test_source_reliability_all_available(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_risk,
    make_dependency,
    make_resource,
    make_action,
    make_requirement,
    make_test_case,
    make_trace_link,
    make_change_request,
):
    portfolio = _full_portfolio(
        make_portfolio,
        make_project,
        make_milestone,
        make_task,
        make_risk,
        make_dependency,
        make_resource,
        make_action,
        make_requirement,
        make_test_case,
        make_trace_link,
        make_change_request,
    )
    result = calculate_project_confidence(TEST_PROJECT_ID, portfolio, AS_OF)
    assert result.factor_scores["source_reliability"] == 100


def test_source_reliability_optional_unavailable(
    make_project, make_milestone, make_task, make_risk, make_portfolio
):
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone()],
        tasks=[make_task()],
        risks=[make_risk()],
    )
    result = calculate_project_confidence(TEST_PROJECT_ID, portfolio, AS_OF)
    assert result.factor_scores["source_reliability"] == 70


def test_source_reliability_critical_unavailable(
    make_project, make_task, make_risk, make_portfolio
):
    # No milestones -> a critical table is unavailable.
    portfolio = make_portfolio(projects=[make_project()], tasks=[make_task()], risks=[make_risk()])
    result = calculate_project_confidence(TEST_PROJECT_ID, portfolio, AS_OF)
    assert result.factor_scores["source_reliability"] == 40
    assert any(
        issue.issue_type == "critical_source_unavailable" and issue.severity == "High"
        for issue in result.data_quality_issues
    )


def test_source_reliability_projects_unavailable_raises(make_portfolio):
    with pytest.raises(DataValidationError):
        calculate_project_confidence(TEST_PROJECT_ID, make_portfolio(), AS_OF)


def test_table_available_but_no_records_for_project_is_not_critical(
    make_project, make_milestone, make_task, make_risk, make_portfolio
):
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone(milestone_id="M-O", project_id="P-OTHER")],
        tasks=[make_task(task_id="T-O", project_id="P-OTHER")],
        risks=[make_risk(risk_id="R-O", project_id="P-OTHER")],
    )
    result = calculate_project_confidence(TEST_PROJECT_ID, portfolio, AS_OF)
    # Critical tables are populated (for another project), so no critical penalty.
    assert result.factor_scores["source_reliability"] == 70


# --------------------------------------------------------------------- aggregation
@pytest.mark.parametrize(
    ("score", "band"),
    [(80.0, "High"), (79.99, "Medium"), (60.0, "Medium"), (59.99, "Low")],
)
def test_confidence_band_boundaries(score, band):
    assert confidence_band(score) == band


def test_weighted_confidence_score_applies_weights_exactly():
    scores = dict.fromkeys(CONFIDENCE_FACTORS, 0.0)
    scores["data_freshness"] = 100.0
    assert weighted_confidence_score(scores) == 40.0
    assert weighted_confidence_score(dict.fromkeys(CONFIDENCE_FACTORS, 80.0)) == 80.0


def test_weighted_confidence_score_rejects_wrong_keys():
    with pytest.raises(ValueError):
        weighted_confidence_score({"data_freshness": 100.0})


def test_result_integrity(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_risk,
    make_dependency,
    make_resource,
    make_action,
    make_requirement,
    make_test_case,
    make_trace_link,
    make_change_request,
):
    portfolio = _full_portfolio(
        make_portfolio,
        make_project,
        make_milestone,
        make_task,
        make_risk,
        make_dependency,
        make_resource,
        make_action,
        make_requirement,
        make_test_case,
        make_trace_link,
        make_change_request,
    )
    result = calculate_project_confidence(TEST_PROJECT_ID, portfolio, AS_OF)
    assert set(result.factor_scores) == set(CONFIDENCE_FACTORS)
    assert set(result.factor_weights) == set(CONFIDENCE_FACTORS)
    assert round(sum(result.factor_weights.values()), 6) == 1.0
    assert result.source_ids == sorted(set(result.source_ids))
    assert result.calculated_at == reference_timestamp(AS_OF)
    assert all(0.0 <= score <= 100.0 for score in result.factor_scores.values())
    assert 0.0 <= result.overall_score <= 100.0


def test_unknown_project_raises(portfolio):
    with pytest.raises(DataValidationError) as exc:
        calculate_project_confidence("P-NONE", portfolio, AS_OF)
    assert "P-NONE" in str(exc.value)


def test_engine_does_not_mutate_portfolio(portfolio):
    before = copy.deepcopy(portfolio)
    calculate_portfolio_confidence(portfolio, AS_OF)
    assert [t.model_dump() for t in portfolio.tasks] == [t.model_dump() for t in before.tasks]
    assert [r.model_dump() for r in portfolio.requirements] == [
        r.model_dump() for r in before.requirements
    ]
    assert [p.model_dump() for p in portfolio.projects] == [p.model_dump() for p in before.projects]


def test_real_portfolio_confidence_distinct_and_scoped():
    portfolio = load_portfolio()
    p002 = calculate_project_confidence("P-002", portfolio, AS_OF)
    p007 = calculate_project_confidence("P-007", portfolio, AS_OF)

    assert p002.overall_score != p007.overall_score
    # P-007 status is 51 days stale -> lower freshness and a High stale-status issue.
    assert p007.factor_scores["data_freshness"] < p002.factor_scores["data_freshness"]
    assert any(
        issue.issue_type == "stale_status_update" and issue.severity == "High"
        for issue in p007.data_quality_issues
    )
    # No cross-project leakage.
    assert all(
        sid.startswith(("P-007", "M-7", "T-7", "R-7", "REQ-7", "TC-7")) for sid in p007.source_ids
    )


def test_health_green_but_confidence_reduced(
    make_project, make_milestone, make_task, make_risk, make_portfolio
):
    # Healthy delivery signals, but stale/missing reporting data.
    project = make_project(
        baseline_end_date=date(2026, 12, 31),
        forecast_end_date=date(2026, 12, 31),
        status_update_date=None,
    )
    milestone = make_milestone(status="On Track")
    task = make_task(last_updated_date=None)
    risk = make_risk()
    portfolio = make_portfolio(
        projects=[project], milestones=[milestone], tasks=[task], risks=[risk]
    )
    health = calculate_project_health(TEST_PROJECT_ID, portfolio, AS_OF)
    confidence = calculate_project_confidence(TEST_PROJECT_ID, portfolio, AS_OF)

    assert health.health_band == "Green"
    assert confidence.confidence_band in ("Low", "Medium")
    assert confidence.overall_score < health.overall_score
