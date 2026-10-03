"""Tests for the deterministic change-impact engine."""

from __future__ import annotations

import copy
from datetime import date

import pytest

from src import scoring_rules as sr
from src.change_impact_engine import (
    calculate_change_impact,
    list_change_requests_for_project,
)
from src.data_loader import load_portfolio
from src.utils import reference_timestamp
from src.validators import DataValidationError

TEST_PROJECT_ID = "P-TEST"
AS_OF = date(2026, 8, 25)


@pytest.fixture
def chain_portfolio(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_dependency,
    make_requirement,
    make_test_case,
    make_trace_link,
    make_change_request,
):
    """REQ1 -> T1 (implemented_by) + TC1 (verified_by); T1 -> T2 via D1; T1/T2 on M1."""
    return make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone(milestone_id="M1", criticality="Critical")],
        tasks=[
            make_task(task_id="T1", milestone_id="M1"),
            make_task(task_id="T2", milestone_id="M1"),
        ],
        dependencies=[
            make_dependency(
                dependency_id="D1",
                predecessor_type="Task",
                predecessor_id="T1",
                successor_type="Task",
                successor_id="T2",
            )
        ],
        requirements=[make_requirement(requirement_id="REQ1", priority="High")],
        test_cases=[make_test_case(test_case_id="TC1")],
        trace_links=[
            make_trace_link(
                trace_link_id="TL1",
                source_id="REQ1",
                target_type="Task",
                target_id="T1",
                link_type="implemented_by",
            ),
            make_trace_link(
                trace_link_id="TL2",
                source_id="REQ1",
                target_type="TestCase",
                target_id="TC1",
                link_type="verified_by",
            ),
        ],
        change_requests=[
            make_change_request(change_request_id="CR1", requirement_id="REQ1", priority="High")
        ],
    )


def test_multi_artefact_chain(chain_portfolio):
    result = calculate_change_impact("CR1", chain_portfolio, AS_OF)
    assert result.requirement_id == "REQ1"
    assert result.affected_task_ids == ["T1", "T2"]
    assert result.affected_test_case_ids == ["TC1"]
    assert result.affected_dependency_ids == ["D1"]
    assert result.affected_milestone_ids == ["M1"]
    assert result.source_ids == ["CR1", "D1", "M1", "REQ1", "T1", "T2", "TC1", "TL1", "TL2"]
    assert "REQ1" in result.deterministic_explanation
    # Critical milestone with a High-priority change.
    assert result.estimated_schedule_impact_days == 15
    assert result.risk_level == "Critical"


def test_dependency_path_adds_task_not_directly_traced(chain_portfolio):
    result = calculate_change_impact("CR1", chain_portfolio, AS_OF)
    # T2 is reachable only through dependency D1, never through a trace link.
    assert "T2" in result.affected_task_ids


def test_dependency_scope_is_invariant_to_row_order(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_dependency,
    make_requirement,
    make_trace_link,
    make_change_request,
):
    first_hop = make_dependency(
        dependency_id="D1",
        predecessor_type="Task",
        predecessor_id="T1",
        successor_type="Task",
        successor_id="T2",
    )
    second_hop = make_dependency(
        dependency_id="D2",
        predecessor_type="Task",
        predecessor_id="T2",
        successor_type="Milestone",
        successor_id="M2",
    )

    def portfolio_with(dependencies):
        return make_portfolio(
            projects=[make_project()],
            milestones=[
                make_milestone(milestone_id="M1"),
                make_milestone(milestone_id="M2"),
            ],
            tasks=[
                make_task(task_id="T1", milestone_id="M1"),
                make_task(task_id="T2", milestone_id="M1"),
            ],
            dependencies=dependencies,
            requirements=[make_requirement(requirement_id="REQ1")],
            trace_links=[
                make_trace_link(
                    source_id="REQ1",
                    target_type="Task",
                    target_id="T1",
                    link_type="implemented_by",
                )
            ],
            change_requests=[make_change_request(change_request_id="CR1", requirement_id="REQ1")],
        )

    forward = calculate_change_impact("CR1", portfolio_with([first_hop, second_hop]), AS_OF)
    reverse = calculate_change_impact("CR1", portfolio_with([second_hop, first_hop]), AS_OF)

    assert forward == reverse
    assert forward.affected_dependency_ids == ["D1"]
    assert forward.affected_milestone_ids == ["M1"]


def test_dependency_path_adds_milestone(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_dependency,
    make_requirement,
    make_trace_link,
    make_change_request,
):
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[
            make_milestone(milestone_id="M1", criticality="Low"),
            make_milestone(milestone_id="M-DEP", criticality="High"),
        ],
        tasks=[make_task(task_id="T1", milestone_id="M1")],
        dependencies=[
            make_dependency(
                dependency_id="D1",
                predecessor_type="Task",
                predecessor_id="T1",
                successor_type="Milestone",
                successor_id="M-DEP",
            )
        ],
        requirements=[make_requirement(requirement_id="REQ1")],
        trace_links=[
            make_trace_link(
                source_id="REQ1", target_type="Task", target_id="T1", link_type="implemented_by"
            )
        ],
        change_requests=[make_change_request(change_request_id="CR1", requirement_id="REQ1")],
    )
    result = calculate_change_impact("CR1", portfolio, AS_OF)
    assert result.affected_milestone_ids == ["M-DEP", "M1"]


def test_delivered_in_link_adds_milestone(
    make_portfolio,
    make_project,
    make_milestone,
    make_requirement,
    make_trace_link,
    make_change_request,
):
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone(milestone_id="M1", criticality="Medium")],
        requirements=[make_requirement(requirement_id="REQ1")],
        trace_links=[
            make_trace_link(
                source_id="REQ1", target_type="Milestone", target_id="M1", link_type="delivered_in"
            )
        ],
        change_requests=[make_change_request(change_request_id="CR1", requirement_id="REQ1")],
    )
    result = calculate_change_impact("CR1", portfolio, AS_OF)
    assert result.affected_milestone_ids == ["M1"]


def test_no_trace_links_is_valid_empty_result(
    make_portfolio, make_project, make_requirement, make_change_request
):
    portfolio = make_portfolio(
        projects=[make_project()],
        requirements=[make_requirement(requirement_id="REQ1")],
        change_requests=[make_change_request(change_request_id="CR1", requirement_id="REQ1")],
    )
    result = calculate_change_impact("CR1", portfolio, AS_OF)
    assert result.affected_task_ids == []
    assert result.affected_test_case_ids == []
    assert result.affected_dependency_ids == []
    assert result.affected_milestone_ids == []
    assert result.estimated_schedule_impact_days == 0
    assert result.risk_level == "Low"
    assert result.evidence_status == "Insufficient evidence"
    assert "no downstream artefacts were found" in result.deterministic_explanation
    assert "cannot be assessed" in result.deterministic_explanation
    assert any("incomplete trace-link data" in limit for limit in result.assumptions_or_limitations)


def test_a_traced_change_is_assessed(chain_portfolio):
    result = calculate_change_impact("CR1", chain_portfolio, AS_OF)

    assert result.evidence_status == "Assessed"


def test_unknown_change_request_raises(chain_portfolio):
    with pytest.raises(DataValidationError) as exc:
        calculate_change_impact("CR-NONE", chain_portfolio, AS_OF)
    assert "CR-NONE" in str(exc.value)


def test_unknown_requirement_raises(
    make_portfolio, make_project, make_requirement, make_change_request
):
    portfolio = make_portfolio(
        projects=[make_project()],
        requirements=[make_requirement(requirement_id="REQ1")],
        change_requests=[make_change_request(change_request_id="CR1", requirement_id="REQ-GONE")],
    )
    with pytest.raises(DataValidationError) as exc:
        calculate_change_impact("CR1", portfolio, AS_OF)
    assert "REQ-GONE" in str(exc.value)


@pytest.mark.parametrize(
    ("criticality", "priority", "expected_days"),
    sorted((c, p, d) for (c, p), d in sr.CHANGE_IMPACT_SCHEDULE_DAYS.items()),
)
def test_schedule_impact_lookup_table(
    make_portfolio,
    make_project,
    make_milestone,
    make_requirement,
    make_trace_link,
    make_change_request,
    criticality,
    priority,
    expected_days,
):
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone(milestone_id="M1", criticality=criticality)],
        requirements=[make_requirement(requirement_id="REQ1")],
        trace_links=[
            make_trace_link(
                source_id="REQ1", target_type="Milestone", target_id="M1", link_type="delivered_in"
            )
        ],
        change_requests=[
            make_change_request(change_request_id="CR1", requirement_id="REQ1", priority=priority)
        ],
    )
    result = calculate_change_impact("CR1", portfolio, AS_OF)
    assert result.estimated_schedule_impact_days == expected_days


@pytest.mark.parametrize(
    ("criticality", "priority", "expected_risk"),
    [
        ("Critical", "Critical", "Critical"),
        ("Critical", "High", "Critical"),
        ("Critical", "Medium", "High"),
        ("High", "Critical", "High"),
        ("High", "Low", "High"),
        ("Medium", "Medium", "Medium"),
        ("Low", "Low", "Medium"),
    ],
)
def test_risk_level_rule(
    make_portfolio,
    make_project,
    make_milestone,
    make_requirement,
    make_trace_link,
    make_change_request,
    criticality,
    priority,
    expected_risk,
):
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone(milestone_id="M1", criticality=criticality)],
        requirements=[make_requirement(requirement_id="REQ1")],
        trace_links=[
            make_trace_link(
                source_id="REQ1", target_type="Milestone", target_id="M1", link_type="delivered_in"
            )
        ],
        change_requests=[
            make_change_request(change_request_id="CR1", requirement_id="REQ1", priority=priority)
        ],
    )
    result = calculate_change_impact("CR1", portfolio, AS_OF)
    assert result.risk_level == expected_risk


def test_risk_level_breadth_threshold(
    make_portfolio,
    make_project,
    make_milestone,
    make_task,
    make_requirement,
    make_test_case,
    make_trace_link,
    make_change_request,
):
    # Low-criticality milestone, Low priority, but many affected artefacts.
    tasks = [make_task(task_id=f"T{i}", milestone_id="M1") for i in range(3)]
    links = [
        make_trace_link(
            trace_link_id=f"TL-T{i}",
            source_id="REQ1",
            target_type="Task",
            target_id=f"T{i}",
            link_type="implemented_by",
        )
        for i in range(3)
    ]
    links.append(
        make_trace_link(
            trace_link_id="TL-TC",
            source_id="REQ1",
            target_type="TestCase",
            target_id="TC1",
            link_type="verified_by",
        )
    )
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone(milestone_id="M1", criticality="Low")],
        tasks=tasks,
        requirements=[make_requirement(requirement_id="REQ1")],
        test_cases=[make_test_case(test_case_id="TC1")],
        trace_links=links,
        change_requests=[
            make_change_request(change_request_id="CR1", requirement_id="REQ1", priority="Low")
        ],
    )
    result = calculate_change_impact("CR1", portfolio, AS_OF)
    # 3 tasks + 1 test + 1 milestone = 5 artefacts.
    assert result.risk_level == "High"


def test_determinism(chain_portfolio):
    first = calculate_change_impact("CR1", chain_portfolio, AS_OF)
    second = calculate_change_impact("CR1", chain_portfolio, AS_OF)
    assert first.model_dump() == second.model_dump()
    assert first.calculated_at == reference_timestamp(AS_OF)


def test_no_mutation():
    portfolio = load_portfolio()
    snapshot = copy.deepcopy(portfolio)
    calculate_change_impact("CR-042", portfolio, AS_OF)
    for attr in (
        "requirements",
        "tasks",
        "milestones",
        "dependencies",
        "trace_links",
        "test_cases",
        "change_requests",
    ):
        after = [r.model_dump() for r in getattr(portfolio, attr)]
        before = [r.model_dump() for r in getattr(snapshot, attr)]
        assert after == before


def test_real_data_cr_042():
    portfolio = load_portfolio()
    result = calculate_change_impact("CR-042", portfolio, AS_OF)
    assert result.requirement_id == "REQ-7001"
    assert result.affected_task_ids == ["T-7001", "T-7002"]
    assert result.affected_test_case_ids == ["TC-7003"]
    assert result.affected_dependency_ids == ["D-7001"]
    assert result.affected_milestone_ids == ["M-702"]
    assert result.risk_level == "Critical"
    assert result.estimated_schedule_impact_days == 15


def test_real_data_source_ids_are_real_and_project_scoped():
    portfolio = load_portfolio()
    result = calculate_change_impact("CR-042", portfolio, AS_OF)
    known = (
        {c.change_request_id for c in portfolio.change_requests if c.project_id == "P-007"}
        | {r.requirement_id for r in portfolio.requirements if r.project_id == "P-007"}
        | {t.task_id for t in portfolio.tasks if t.project_id == "P-007"}
        | {t.test_case_id for t in portfolio.test_cases if t.project_id == "P-007"}
        | {m.milestone_id for m in portfolio.milestones if m.project_id == "P-007"}
        | {d.dependency_id for d in portfolio.dependencies if d.project_id == "P-007"}
        | {link.trace_link_id for link in portfolio.trace_links if link.project_id == "P-007"}
    )
    assert set(result.source_ids) <= known
    assert result.source_ids == sorted(set(result.source_ids))


def test_list_change_requests_for_project():
    portfolio = load_portfolio()
    assert [c.change_request_id for c in list_change_requests_for_project("P-007", portfolio)] == [
        "CR-042"
    ]
    assert [c.change_request_id for c in list_change_requests_for_project("P-002", portfolio)] == [
        "CR-018"
    ]
