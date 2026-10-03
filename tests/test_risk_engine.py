"""Tests for the deterministic risk early-warning engine."""

from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from src.data_loader import load_portfolio
from src.risk_engine import (
    ALERT_OVERDUE_ACTION,
    ALERT_REQUIREMENT_VERIFICATION,
    ALERT_STALE_STATUS,
    ALERT_UNOWNED_RISK,
    generate_early_warnings,
    generate_portfolio_early_warnings,
)
from src.scoring_rules import SEVERITY_ORDER
from src.validators import DataValidationError

TEST_PROJECT_ID = "P-TEST"
AS_OF = date(2026, 8, 25)


def _alerts_of_type(alerts, alert_type):
    return [a for a in alerts if a.alert_type == alert_type]


# --------------------------------------------------------------------------- Rule 1
@pytest.mark.parametrize(
    ("probability", "impact", "owner", "status", "expected"),
    [
        (5, 5, None, "Open", "Critical"),
        (5, 4, None, "Open", "High"),
        (5, 5, None, "Mitigating", "Critical"),
        (4, 4, None, "Open", None),  # exposure 16 < 20
        (5, 5, "Pat Owner", "Open", None),
        (5, 5, None, "Closed", None),
    ],
)
def test_rule1_unowned_high_exposure_risk(
    make_project, make_risk, make_portfolio, probability, impact, owner, status, expected
):
    risk = make_risk(probability=probability, impact=impact, mitigation_owner=owner, status=status)
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID, make_portfolio(projects=[make_project()], risks=[risk]), AS_OF
        ),
        ALERT_UNOWNED_RISK,
    )
    if expected is None:
        assert alerts == []
    else:
        assert len(alerts) == 1 and alerts[0].severity == expected


# --------------------------------------------------------------------------- Rule 2
@pytest.mark.parametrize(
    ("criticality", "slip", "expected"),
    [
        ("Critical", 11, "Critical"),
        ("Critical", 10, "High"),
        ("Critical", 1, "High"),
        ("High", 11, "High"),
        ("High", 5, "Medium"),
        ("Critical", 0, None),
        ("Medium", 11, None),
        ("Low", 11, None),
    ],
)
def test_rule2_critical_milestone_slip(
    make_project, make_milestone, make_portfolio, criticality, slip, expected
):
    baseline = date(2026, 6, 1)
    milestone = make_milestone(
        criticality=criticality,
        baseline_date=baseline,
        forecast_date=baseline + timedelta(days=slip),
        status="On Track",
    )
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            make_portfolio(projects=[make_project()], milestones=[milestone]),
            AS_OF,
        ),
        "critical_milestone_slip",
    )
    if expected is None:
        assert alerts == []
    else:
        assert len(alerts) == 1 and alerts[0].severity == expected


# --------------------------------------------------------------------------- Rule 3
@pytest.mark.parametrize(
    ("criticality", "status", "delay", "expected"),
    [
        ("Critical", "Blocked", 0, "Critical"),
        ("Critical", "Delayed", 11, "Critical"),
        ("Critical", "Delayed", 5, "High"),
        ("High", "Delayed", 5, "High"),
        ("Medium", "Delayed", 5, None),
        ("Low", "Blocked", 20, None),
    ],
)
def test_rule3_milestone_delayed_dependency(
    make_project,
    make_milestone,
    make_dependency,
    make_portfolio,
    criticality,
    status,
    delay,
    expected,
):
    milestone = make_milestone(milestone_id="M-DEP", criticality=criticality)
    dependency = make_dependency(
        dependency_id="D-DEP",
        successor_type="Milestone",
        successor_id="M-DEP",
        status=status,
        delay_days=delay,
        criticality=criticality,
    )
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            make_portfolio(
                projects=[make_project()], milestones=[milestone], dependencies=[dependency]
            ),
            AS_OF,
        ),
        "milestone_delayed_dependency",
    )
    if expected is None:
        assert alerts == []
    else:
        assert len(alerts) == 1 and alerts[0].severity == expected
        assert {"D-DEP", "M-DEP"} == set(alerts[0].source_ids)


def test_rule3_blocked_dependency_does_not_claim_zero_day_delay(
    make_project, make_milestone, make_dependency, make_portfolio
):
    milestone = make_milestone(milestone_id="M-DEP", criticality="Critical")
    dependency = make_dependency(
        dependency_id="D-BLOCKED",
        successor_type="Milestone",
        successor_id="M-DEP",
        status="Blocked",
        delay_days=0,
    )
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            make_portfolio(
                projects=[make_project()], milestones=[milestone], dependencies=[dependency]
            ),
            AS_OF,
        ),
        "milestone_delayed_dependency",
    )

    assert len(alerts) == 1
    assert "is Blocked" in alerts[0].explanation
    assert "delayed by 0 days" not in alerts[0].explanation


# --------------------------------------------------------------------------- Rule 4
@pytest.mark.parametrize(
    ("criticality", "blocked", "expected"),
    [
        ("Critical", True, "Critical"),
        ("High", True, "High"),
        ("Medium", True, None),
        ("Low", True, None),
        ("Critical", False, None),
    ],
)
def test_rule4_blocked_task_critical_milestone(
    make_project, make_milestone, make_task, make_portfolio, criticality, blocked, expected
):
    milestone = make_milestone(milestone_id="M-BT", criticality=criticality)
    task = make_task(
        task_id="T-BT",
        milestone_id="M-BT",
        is_blocked=blocked,
        status="Blocked" if blocked else "In Progress",
    )
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            make_portfolio(projects=[make_project()], milestones=[milestone], tasks=[task]),
            AS_OF,
        ),
        "blocked_task_critical_milestone",
    )
    if expected is None:
        assert alerts == []
    else:
        assert len(alerts) == 1 and alerts[0].severity == expected


# --------------------------------------------------------------------------- Rule 5
@pytest.mark.parametrize(
    ("priority", "overdue_days", "expected"),
    [
        ("Critical", 8, "Critical"),
        ("Critical", 7, "High"),
        ("High", 8, "High"),
        ("High", 7, "Medium"),
        ("Low", 8, None),
        ("Medium", 8, None),
    ],
)
def test_rule5_overdue_action(
    make_project, make_action, make_portfolio, priority, overdue_days, expected
):
    action = make_action(
        priority=priority, due_date=AS_OF - timedelta(days=overdue_days), status="Open"
    )
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID, make_portfolio(projects=[make_project()], actions=[action]), AS_OF
        ),
        ALERT_OVERDUE_ACTION,
    )
    if expected is None:
        assert alerts == []
    else:
        assert len(alerts) == 1 and alerts[0].severity == expected


def test_rule5_not_yet_due_and_completed_excluded(make_project, make_action, make_portfolio):
    future = make_action(action_id="A-FUT", priority="Critical", due_date=AS_OF + timedelta(days=5))
    done = make_action(
        action_id="A-DONE",
        priority="Critical",
        due_date=AS_OF - timedelta(days=30),
        status="Complete",
    )
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            make_portfolio(projects=[make_project()], actions=[future, done]),
            AS_OF,
        ),
        ALERT_OVERDUE_ACTION,
    )
    assert alerts == []


# --------------------------------------------------------------------------- Rule 6
@pytest.mark.parametrize(
    ("allocated", "capacity", "expected"),
    [
        (100, 100, None),
        (10001, 10000, "Medium"),
        (110, 100, "Medium"),
        (11001, 10000, "High"),
        (125, 100, "High"),
        (12501, 10000, "Critical"),
    ],
)
def test_rule6_resource_over_allocation(
    make_project, make_resource, make_portfolio, allocated, capacity, expected
):
    resource = make_resource(allocated_hours=allocated, capacity_hours=capacity)
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID, make_portfolio(projects=[make_project()], resources=[resource]), AS_OF
        ),
        "resource_over_allocation",
    )
    if expected is None:
        assert alerts == []
    else:
        assert len(alerts) == 1 and alerts[0].severity == expected


# --------------------------------------------------------------------------- Rule 7
@pytest.mark.parametrize(
    ("age_days", "expected"),
    [(14, None), (15, "Medium"), (21, "Medium"), (22, "High")],
)
def test_rule7_stale_project_status(make_project, make_portfolio, age_days, expected):
    project = make_project(status_update_date=AS_OF - timedelta(days=age_days))
    alerts = _alerts_of_type(
        generate_early_warnings(TEST_PROJECT_ID, make_portfolio(projects=[project]), AS_OF),
        ALERT_STALE_STATUS,
    )
    if expected is None:
        assert alerts == []
    else:
        assert len(alerts) == 1 and alerts[0].severity == expected


def test_rule7_future_status_date_is_rejected(make_project, make_portfolio):
    project = make_project(status_update_date=AS_OF + timedelta(days=1))

    with pytest.raises(DataValidationError, match=TEST_PROJECT_ID):
        generate_early_warnings(TEST_PROJECT_ID, make_portfolio(projects=[project]), AS_OF)


def test_rule7_missing_status_date_is_critical(make_project, make_portfolio):
    project = make_project(status_update_date=None)
    alerts = _alerts_of_type(
        generate_early_warnings(TEST_PROJECT_ID, make_portfolio(projects=[project]), AS_OF),
        ALERT_STALE_STATUS,
    )
    assert len(alerts) == 1 and alerts[0].severity == "Critical"


# --------------------------------------------------------------------------- Rule 8
def _rule8_portfolio(make_portfolio, make_project, requirement, test_cases, trace_links):
    return make_portfolio(
        projects=[make_project()],
        requirements=[requirement],
        test_cases=test_cases,
        trace_links=trace_links,
    )


def test_rule8_critical_requirement_no_linked_test(make_project, make_requirement, make_portfolio):
    requirement = make_requirement(requirement_id="REQ-C", priority="Critical", status="Approved")
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            _rule8_portfolio(make_portfolio, make_project, requirement, [], []),
            AS_OF,
        ),
        ALERT_REQUIREMENT_VERIFICATION,
    )
    assert len(alerts) == 1 and alerts[0].severity == "Critical"
    assert alerts[0].source_ids == ["REQ-C"]


def test_rule8_high_requirement_test_not_run_is_medium(
    make_project, make_requirement, make_test_case, make_trace_link, make_portfolio
):
    requirement = make_requirement(requirement_id="REQ-H", priority="High")
    test_case = make_test_case(test_case_id="TC-NR", status="Not Run", verification_evidence=None)
    link = make_trace_link(trace_link_id="TL-VERIFY", source_id="REQ-H", target_id="TC-NR")
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            _rule8_portfolio(make_portfolio, make_project, requirement, [test_case], [link]),
            AS_OF,
        ),
        ALERT_REQUIREMENT_VERIFICATION,
    )
    assert len(alerts) == 1 and alerts[0].severity == "Medium"
    assert set(alerts[0].source_ids) == {"REQ-H", "TC-NR", "TL-VERIFY"}


def test_rule8_high_requirement_failed_no_evidence_is_high(
    make_project, make_requirement, make_test_case, make_trace_link, make_portfolio
):
    requirement = make_requirement(requirement_id="REQ-H", priority="High")
    test_case = make_test_case(test_case_id="TC-F", status="Failed", verification_evidence=None)
    link = make_trace_link(source_id="REQ-H", target_id="TC-F")
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            _rule8_portfolio(make_portfolio, make_project, requirement, [test_case], [link]),
            AS_OF,
        ),
        ALERT_REQUIREMENT_VERIFICATION,
    )
    assert len(alerts) == 1 and alerts[0].severity == "High"


def test_rule8_verified_requirement_has_no_alert(
    make_project, make_requirement, make_test_case, make_trace_link, make_portfolio
):
    requirement = make_requirement(requirement_id="REQ-V", priority="Critical")
    test_case = make_test_case(test_case_id="TC-P", status="Passed", verification_evidence="EVID")
    link = make_trace_link(source_id="REQ-V", target_id="TC-P")
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            _rule8_portfolio(make_portfolio, make_project, requirement, [test_case], [link]),
            AS_OF,
        ),
        ALERT_REQUIREMENT_VERIFICATION,
    )
    assert alerts == []


@pytest.mark.parametrize("priority", ["Low", "Medium"])
def test_rule8_low_priority_requirement_never_triggers(
    make_project, make_requirement, make_portfolio, priority
):
    requirement = make_requirement(requirement_id="REQ-L", priority=priority)
    alerts = _alerts_of_type(
        generate_early_warnings(
            TEST_PROJECT_ID,
            _rule8_portfolio(make_portfolio, make_project, requirement, [], []),
            AS_OF,
        ),
        ALERT_REQUIREMENT_VERIFICATION,
    )
    assert alerts == []


# --------------------------------------------------------------------------- cross-cutting
def test_alert_ids_are_deterministic_and_unique(make_project, make_risk, make_portfolio):
    risk = make_risk(probability=5, impact=5, mitigation_owner=None, status="Open")
    portfolio = make_portfolio(projects=[make_project()], risks=[risk])
    first = generate_early_warnings(TEST_PROJECT_ID, portfolio, AS_OF)
    second = generate_early_warnings(TEST_PROJECT_ID, portfolio, AS_OF)
    assert [a.alert_id for a in first] == [a.alert_id for a in second]
    assert len({a.alert_id for a in first}) == len(first)


def test_stable_ordering(make_project, make_risk, make_action, make_resource, make_portfolio):
    # Two projects, mixed severities across several rules.
    project_a = make_project(project_id="P-A")
    project_b = make_project(project_id="P-B")
    crit_risk = make_risk(
        risk_id="R-A", project_id="P-A", probability=5, impact=5, mitigation_owner=None
    )
    med_resource = make_resource(
        resource_id="RES-B", project_id="P-B", allocated_hours=105, capacity_hours=100
    )
    high_action = make_action(
        action_id="A-B",
        project_id="P-B",
        priority="High",
        due_date=AS_OF - timedelta(days=30),
    )
    portfolio = make_portfolio(
        projects=[project_a, project_b],
        risks=[crit_risk],
        resources=[med_resource],
        actions=[high_action],
    )
    alerts = generate_portfolio_early_warnings(portfolio, AS_OF)
    keys = [(-SEVERITY_ORDER[a.severity], a.project_id, a.alert_type, a.alert_id) for a in alerts]
    assert keys == sorted(keys)
    # Highest severity first.
    assert alerts[0].severity == "Critical"


def test_source_ids_reference_real_records():
    portfolio = load_portfolio()
    known_ids = (
        portfolio.project_ids
        | {m.milestone_id for m in portfolio.milestones}
        | {t.task_id for t in portfolio.tasks}
        | {r.risk_id for r in portfolio.risks}
        | {d.dependency_id for d in portfolio.dependencies}
        | {r.resource_id for r in portfolio.resources}
        | {a.action_id for a in portfolio.actions}
        | {r.requirement_id for r in portfolio.requirements}
        | {t.test_case_id for t in portfolio.test_cases}
        | {link.trace_link_id for link in portfolio.trace_links}
    )
    alerts = generate_portfolio_early_warnings(portfolio, AS_OF)
    for alert in alerts:
        assert alert.source_ids == sorted(set(alert.source_ids))
        assert set(alert.source_ids) <= known_ids


def test_project_scoping_and_portfolio_aggregation():
    """Per-project alerts must partition the portfolio exactly, with nothing lost or duplicated."""
    portfolio = load_portfolio()

    combined_ids: set[str] = set()
    for project_id in portfolio.project_ids:
        alerts = generate_early_warnings(project_id, portfolio, AS_OF)
        assert all(a.project_id == project_id for a in alerts)
        combined_ids |= {a.alert_id for a in alerts}

    portfolio_ids = {a.alert_id for a in generate_portfolio_early_warnings(portfolio, AS_OF)}
    assert combined_ids == portfolio_ids


def test_engine_does_not_mutate_portfolio():
    portfolio = load_portfolio()
    before = copy.deepcopy(portfolio)
    generate_portfolio_early_warnings(portfolio, AS_OF)
    assert [r.model_dump() for r in portfolio.risks] == [r.model_dump() for r in before.risks]
    assert [m.model_dump() for m in portfolio.milestones] == [
        m.model_dump() for m in before.milestones
    ]
    assert [a.model_dump() for a in portfolio.actions] == [a.model_dump() for a in before.actions]


def test_unknown_project_raises():
    with pytest.raises(DataValidationError) as exc:
        generate_early_warnings("P-NONE", load_portfolio(), AS_OF)
    assert "P-NONE" in str(exc.value)


def test_real_portfolio_known_alerts():
    portfolio = load_portfolio()
    p002 = generate_early_warnings("P-002", portfolio, AS_OF)
    p007 = generate_early_warnings("P-007", portfolio, AS_OF)

    # P-002 has an Open impact-5 unowned risk R-2001 -> Critical unowned-risk alert.
    unowned_002 = _alerts_of_type(p002, ALERT_UNOWNED_RISK)
    assert any(a.severity == "Critical" and "R-2001" in a.source_ids for a in unowned_002)

    # P-007 status is 51 days stale as of 2026-08-25 -> High stale-status alert.
    stale_007 = _alerts_of_type(p007, ALERT_STALE_STATUS)
    assert len(stale_007) == 1 and stale_007[0].severity == "High"

    # P-002 status is fresh (5 days) -> no stale alert.
    assert _alerts_of_type(p002, ALERT_STALE_STATUS) == []


def test_multiple_simultaneous_conditions(
    make_project, make_risk, make_action, make_resource, make_portfolio
):
    project = make_project(status_update_date=AS_OF - timedelta(days=30))
    risk = make_risk(probability=5, impact=5, mitigation_owner=None, status="Open")
    action = make_action(priority="Critical", due_date=AS_OF - timedelta(days=10))
    resource = make_resource(allocated_hours=130, capacity_hours=100)
    alerts = generate_early_warnings(
        TEST_PROJECT_ID,
        make_portfolio(projects=[project], risks=[risk], actions=[action], resources=[resource]),
        AS_OF,
    )
    types = {a.alert_type for a in alerts}
    assert {
        ALERT_UNOWNED_RISK,
        ALERT_OVERDUE_ACTION,
        ALERT_STALE_STATUS,
        "resource_over_allocation",
    } <= types
