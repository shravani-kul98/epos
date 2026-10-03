"""Value-level UI tests for the Scenario Planner page.

Simulations are driven the way a user drives them: select a dependency, enter a delay, click run.
"""

from __future__ import annotations

import copy

import pytest

from src import scoring_rules as sr
from src import ui_formatting as ui
from src.data_loader import load_portfolio
from src.scenario_engine import simulate_dependency_delay
from tests.conftest import AS_OF, PAGE_SCENARIO, frame_named, rendered_text

CASES = [("P-002", "D-2002"), ("P-007", "D-7002")]
DELAY = 30


def _metrics(app) -> dict[str, str]:
    return {metric.label: metric.value for metric in app.metric}


def _run_simulation(open_page, project_id, dependency_id, delay=DELAY):
    app = open_page(
        PAGE_SCENARIO,
        selected_project=project_id,
        selected_dependency=dependency_id,
        scenario_delay_days=delay,
    )
    app.button[0].click().run()
    return app


@pytest.mark.parametrize(("project_id", "dependency_id"), CASES)
def test_simulation_metrics_match_engine(open_page, project_id, dependency_id):
    portfolio = load_portfolio()
    result = simulate_dependency_delay(dependency_id, DELAY, portfolio, AS_OF)
    comparison = result.affected_projects[0]

    app = _run_simulation(open_page, project_id, dependency_id)
    metrics = _metrics(app)

    assert metrics["Baseline Health"] == (
        f"{ui.format_score(comparison.baseline_health_score)} "
        f"({comparison.baseline_health_band})"
    )
    assert metrics["Scenario Health"] == (
        f"{ui.format_score(comparison.scenario_health_score)} "
        f"({comparison.scenario_health_band})"
    )
    assert metrics["Baseline Confidence"] == (
        f"{ui.format_score(comparison.baseline_confidence_score)} "
        f"({comparison.baseline_confidence_band})"
    )
    assert metrics["Scenario Confidence"] == (
        f"{ui.format_score(comparison.scenario_confidence_score)} "
        f"({comparison.scenario_confidence_band})"
    )
    assert len(app.exception) == 0
    assert len(app.error) == 0


def test_d7002_produces_the_documented_health_movement(open_page):
    """D-7002 is the scenario with a real, documented effect: 51.15 -> 48.35, 9 -> 11 alerts."""
    app = _run_simulation(open_page, "P-007", "D-7002")
    metrics = _metrics(app)

    assert metrics["Baseline Health"] == "51.1 (Red)"
    assert metrics["Scenario Health"] == "48.4 (Red)"

    frame = frame_named(app, "Severity", "Baseline", "Scenario")
    assert frame["Baseline"].sum() == 9
    assert frame["Scenario"].sum() == 11
    assert frame[frame["Severity"] == "Critical"]["Change"].iloc[0] == 2


def test_d2002_produces_its_own_distinct_values(open_page):
    app = _run_simulation(open_page, "P-002", "D-2002")
    metrics = _metrics(app)

    assert metrics["Baseline Health"] == "49.9 (Red)"
    assert metrics["Scenario Health"] == "49.4 (Red)"

    frame = frame_named(app, "Severity", "Baseline", "Scenario")
    # A task-to-task dependency has no linked milestone, so no new alert is raised.
    assert frame["Baseline"].sum() == frame["Scenario"].sum() == 7


@pytest.mark.parametrize(("project_id", "dependency_id"), CASES)
def test_alert_delta_table_matches_engine(open_page, project_id, dependency_id):
    portfolio = load_portfolio()
    comparison = simulate_dependency_delay(
        dependency_id, DELAY, portfolio, AS_OF
    ).affected_projects[0]

    app = _run_simulation(open_page, project_id, dependency_id)
    frame = frame_named(app, "Severity", "Baseline", "Scenario", "Change")

    for _, row in frame.iterrows():
        severity = row["Severity"]
        assert row["Baseline"] == comparison.baseline_alert_counts[severity]
        assert row["Scenario"] == comparison.scenario_alert_counts[severity]
        assert row["Change"] == (
            comparison.scenario_alert_counts[severity] - comparison.baseline_alert_counts[severity]
        )


@pytest.mark.parametrize(("project_id", "dependency_id"), CASES)
def test_explanation_and_limitations_render_verbatim(open_page, project_id, dependency_id):
    portfolio = load_portfolio()
    result = simulate_dependency_delay(dependency_id, DELAY, portfolio, AS_OF)

    app = _run_simulation(open_page, project_id, dependency_id)
    text = rendered_text(app)

    assert result.deterministic_explanation in text
    for item in result.assumptions_or_limitations:
        assert item in text


def test_simulation_does_not_alter_baseline_statement_is_present(open_page):
    app = open_page(PAGE_SCENARIO, selected_project="P-007")
    text = rendered_text(app)
    assert "does not alter the Portfolio Dashboard" in text
    assert "No baseline data is ever modified" in text


def test_already_delayed_dependency_reports_no_change(open_page):
    """D-2001 is already late, and 30 more days crosses no threshold; the page must say so."""
    app = _run_simulation(open_page, "P-002", "D-2001")
    metrics = _metrics(app)
    text = rendered_text(app)

    assert metrics["Baseline Health"] == metrics["Scenario Health"]
    assert "crosses no scoring threshold" in text


def test_delay_input_bounds_match_engine_validation(open_page):
    app = open_page(PAGE_SCENARIO, selected_project="P-007")
    delay_input = app.number_input[0]
    assert delay_input.min == sr.SCENARIO_MIN_DELAY_DAYS
    assert delay_input.max == sr.SCENARIO_MAX_DELAY_DAYS


def test_running_a_scenario_does_not_mutate_the_loaded_portfolio(open_page):
    """The page must leave the session's portfolio object untouched after a run."""
    app = _run_simulation(open_page, "P-007", "D-7002")
    session_portfolio = app.session_state["portfolio"]
    reference = load_portfolio()

    for attr in ("dependencies", "milestones", "tasks", "risks", "projects"):
        after = [record.model_dump() for record in getattr(session_portfolio, attr)]
        expected = [record.model_dump() for record in getattr(reference, attr)]
        assert after == expected


def test_dependency_selector_lists_only_this_projects_dependencies(open_page):
    portfolio = load_portfolio()
    expected = sorted(d.dependency_id for d in portfolio.dependencies if d.project_id == "P-007")

    app = open_page(PAGE_SCENARIO, selected_project="P-007")
    labels = list(app.selectbox[1].options)
    assert len(labels) == len(expected)
    for label, dependency_id in zip(labels, expected, strict=True):
        assert label.startswith(f"{dependency_id} - ")


def test_scenario_state_is_independent_of_baseline_pages(open_page):
    """A scenario run must not leak modified values into a freshly computed baseline."""
    before = copy.deepcopy(load_portfolio())
    _run_simulation(open_page, "P-007", "D-7002")
    after = load_portfolio()
    assert [d.model_dump() for d in after.dependencies] == [
        d.model_dump() for d in before.dependencies
    ]
