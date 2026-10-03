"""Value-level UI tests for the Change Impact page."""

from __future__ import annotations

import pytest

from src import ui_formatting as ui
from src.change_impact_engine import calculate_change_impact, list_change_requests_for_project
from src.data_loader import load_portfolio
from tests.conftest import AS_OF, PAGE_CHANGE_IMPACT, frame_named, rendered_text

CASES = [("P-002", "CR-018"), ("P-007", "CR-042")]


def _metrics(app) -> dict[str, str]:
    return {metric.label: metric.value for metric in app.metric}


@pytest.mark.parametrize(("project_id", "change_request_id"), CASES)
def test_impact_metrics_match_engine(open_page, project_id, change_request_id):
    portfolio = load_portfolio()
    result = calculate_change_impact(change_request_id, portfolio, AS_OF)

    app = open_page(
        PAGE_CHANGE_IMPACT,
        selected_project=project_id,
        selected_change_request=change_request_id,
    )
    metrics = _metrics(app)

    assert metrics["Estimated schedule impact"] == ui.format_days(
        result.estimated_schedule_impact_days
    )
    assert metrics["Change risk level"] == result.risk_level
    assert len(app.exception) == 0
    assert len(app.error) == 0


def test_cr_042_exact_documented_values(open_page):
    app = open_page(PAGE_CHANGE_IMPACT, selected_project="P-007", selected_change_request="CR-042")
    metrics = _metrics(app)
    assert metrics["Estimated schedule impact"] == "15 calendar days"
    assert metrics["Change risk level"] == "Critical"


@pytest.mark.parametrize(("project_id", "change_request_id"), CASES)
def test_explanation_and_limitations_render_verbatim(open_page, project_id, change_request_id):
    portfolio = load_portfolio()
    result = calculate_change_impact(change_request_id, portfolio, AS_OF)

    app = open_page(
        PAGE_CHANGE_IMPACT,
        selected_project=project_id,
        selected_change_request=change_request_id,
    )
    text = rendered_text(app)

    assert result.deterministic_explanation in text
    for item in result.assumptions_or_limitations:
        assert item in text


@pytest.mark.parametrize(("project_id", "change_request_id"), CASES)
def test_affected_id_summary_matches_engine(open_page, project_id, change_request_id):
    portfolio = load_portfolio()
    result = calculate_change_impact(change_request_id, portfolio, AS_OF)

    app = open_page(
        PAGE_CHANGE_IMPACT,
        selected_project=project_id,
        selected_change_request=change_request_id,
    )
    frame = frame_named(app, "Artefact type", "Count", "IDs")
    rows = dict(zip(frame["Artefact type"], frame["IDs"], strict=True))
    counts = dict(zip(frame["Artefact type"], frame["Count"], strict=True))

    assert rows["Tasks"] == ui.format_source_ids(result.affected_task_ids)
    assert rows["Test cases"] == ui.format_source_ids(result.affected_test_case_ids)
    assert rows["Dependencies"] == ui.format_source_ids(result.affected_dependency_ids)
    assert rows["Milestones"] == ui.format_source_ids(result.affected_milestone_ids)
    assert counts["Tasks"] == len(result.affected_task_ids)
    assert counts["Milestones"] == len(result.affected_milestone_ids)


@pytest.mark.parametrize(("project_id", "change_request_id"), CASES)
def test_every_affected_id_resolves_to_a_rendered_record(open_page, project_id, change_request_id):
    """Each ID the engine returns must have its underlying record shown for verification."""
    portfolio = load_portfolio()
    result = calculate_change_impact(change_request_id, portfolio, AS_OF)

    app = open_page(
        PAGE_CHANGE_IMPACT,
        selected_project=project_id,
        selected_change_request=change_request_id,
    )

    def rendered_ids(column: str) -> set[str]:
        for element in app.dataframe:
            frame = element.value
            if column in frame.columns:
                return set(frame[column].tolist())
        return set()

    assert set(result.affected_task_ids) <= rendered_ids("Task")
    assert set(result.affected_milestone_ids) <= rendered_ids("Milestone")
    assert set(result.affected_dependency_ids) <= rendered_ids("Dependency")
    if result.affected_test_case_ids:
        assert set(result.affected_test_case_ids) <= rendered_ids("Test case")


@pytest.mark.parametrize(("project_id", "change_request_id"), CASES)
def test_change_request_summary_matches_loaded_record(open_page, project_id, change_request_id):
    portfolio = load_portfolio()
    change_request = next(
        c for c in portfolio.change_requests if c.change_request_id == change_request_id
    )

    app = open_page(
        PAGE_CHANGE_IMPACT,
        selected_project=project_id,
        selected_change_request=change_request_id,
    )
    frame = frame_named(app, "Change request", "Requirement", "Description")
    row = frame.iloc[0]

    assert row["Change request"] == change_request.change_request_id
    assert row["Requirement"] == change_request.requirement_id
    assert row["Description"] == change_request.change_description
    assert row["Reason"] == change_request.reason
    assert row["Priority"] == change_request.priority
    assert row["Status"] == change_request.status
    assert row["Requested date"] == ui.format_date(change_request.requested_date)


@pytest.mark.parametrize("project_id", ["P-002", "P-007"])
def test_selector_lists_exactly_the_projects_change_requests(open_page, project_id):
    portfolio = load_portfolio()
    expected = [
        c.change_request_id for c in list_change_requests_for_project(project_id, portfolio)
    ]

    app = open_page(PAGE_CHANGE_IMPACT, selected_project=project_id)
    # Options render through format_func, so compare the identifier prefix of each label.
    labels = list(app.selectbox[1].options)
    assert len(labels) == len(expected)
    for label, change_request_id in zip(labels, expected, strict=True):
        assert label.startswith(f"{change_request_id} - ")


def test_heuristic_caveat_is_visible_next_to_the_metric(open_page):
    app = open_page(PAGE_CHANGE_IMPACT, selected_project="P-007", selected_change_request="CR-042")
    text = rendered_text(app)
    assert "coarse Version 1 heuristic" in text
    assert "not a validated forecast" in text
