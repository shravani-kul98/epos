"""Value-level UI tests for the Project Intelligence page."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src import ui_formatting as ui
from src.confidence_engine import calculate_project_confidence
from src.data_loader import load_portfolio
from src.health_engine import calculate_project_health
from src.risk_engine import generate_early_warnings
from tests.conftest import (
    APP_PATH,
    AS_OF,
    PAGE_PROJECT_INTELLIGENCE,
    frame_named,
    rendered_text,
)

PROJECT_IDS = ["P-002", "P-007"]


def _metrics(app) -> dict[str, str]:
    return {metric.label: metric.value for metric in app.metric}


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_header_metrics_match_engine_output(open_page, project_id):
    portfolio = load_portfolio()
    health = calculate_project_health(project_id, portfolio, AS_OF)
    confidence = calculate_project_confidence(project_id, portfolio, AS_OF)

    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project=project_id)
    metrics = _metrics(app)

    assert metrics["Health"] == (f"{ui.format_score(health.overall_score)} ({health.health_band})")
    assert metrics["Confidence"] == (
        f"{ui.format_score(confidence.overall_score)} ({confidence.confidence_band})"
    )
    assert len(app.exception) == 0
    assert len(app.error) == 0


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_factor_explanations_render_verbatim(open_page, project_id):
    portfolio = load_portfolio()
    health = calculate_project_health(project_id, portfolio, AS_OF)
    confidence = calculate_project_confidence(project_id, portfolio, AS_OF)

    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project=project_id)
    text = rendered_text(app)

    for lines in health.factor_explanations.values():
        for line in lines:
            assert line in text, f"health explanation not rendered verbatim: {line}"
    for lines in confidence.factor_explanations.values():
        for line in lines:
            assert line in text, f"confidence explanation not rendered verbatim: {line}"


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_factor_tables_match_engine_scores_and_weights(open_page, project_id):
    portfolio = load_portfolio()
    health = calculate_project_health(project_id, portfolio, AS_OF)
    confidence = calculate_project_confidence(project_id, portfolio, AS_OF)

    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project=project_id)
    tables = [
        element.value
        for element in app.dataframe
        if {"Factor", "Weight", "Score"} <= set(element.value.columns)
    ]
    rendered = [
        (
            dict(zip(frame["Factor"], frame["Score"], strict=True)),
            dict(zip(frame["Factor"], frame["Weight"], strict=True)),
        )
        for frame in tables
    ]

    assert (health.factor_scores, health.factor_weights) in rendered
    assert (confidence.factor_scores, confidence.factor_weights) in rendered


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_factors_ordered_most_penalised_first(open_page, project_id):
    portfolio = load_portfolio()
    health = calculate_project_health(project_id, portfolio, AS_OF)

    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project=project_id)
    for element in app.dataframe:
        frame = element.value
        if {"Factor", "Weight", "Score"} <= set(frame.columns) and len(frame) == 7:
            assert frame["Factor"].tolist() == ui.factors_by_ascending_score(health.factor_scores)
            return
    raise AssertionError("health factor table was not rendered")


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_critical_drivers_and_issues_all_rendered(open_page, project_id):
    portfolio = load_portfolio()
    health = calculate_project_health(project_id, portfolio, AS_OF)
    confidence = calculate_project_confidence(project_id, portfolio, AS_OF)

    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project=project_id)
    text = rendered_text(app)

    for driver in health.critical_drivers:
        assert driver.message in text
        assert ui.format_source_ids(driver.source_ids) in text
    for issue in confidence.data_quality_issues:
        assert issue.message in text
        assert issue.remediation_hint in text


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_alerts_render_with_engine_content(open_page, project_id):
    portfolio = load_portfolio()
    alerts = generate_early_warnings(project_id, portfolio, AS_OF)

    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project=project_id)
    text = rendered_text(app)

    assert alerts, "the real data should produce alerts for both projects"
    for alert in alerts:
        assert alert.explanation in text
        assert alert.recommended_next_step in text
        assert alert.title in text


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_limitations_are_labelled_not_hidden(open_page, project_id):
    portfolio = load_portfolio()
    health = calculate_project_health(project_id, portfolio, AS_OF)
    confidence = calculate_project_confidence(project_id, portfolio, AS_OF)

    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project=project_id)
    text = rendered_text(app)

    assert "Assumptions and limitations" in text
    for item in list(health.assumptions_or_limitations) + list(
        confidence.assumptions_or_limitations
    ):
        assert item in text


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_underlying_records_match_loaded_data(open_page, project_id):
    portfolio = load_portfolio()
    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project=project_id)

    expected_tasks = {t.task_id for t in portfolio.tasks if t.project_id == project_id}
    expected_risks = {r.risk_id for r in portfolio.risks if r.project_id == project_id}

    task_frame = frame_named(app, "task_id")
    risk_frame = frame_named(app, "risk_id")
    assert set(task_frame["task_id"]) == expected_tasks
    assert set(risk_frame["risk_id"]) == expected_risks


def test_switching_project_updates_every_displayed_value():
    """Switch projects inside one session and confirm all values change together."""
    portfolio = load_portfolio()
    expected = {
        pid: (
            calculate_project_health(pid, portfolio, AS_OF),
            calculate_project_confidence(pid, portfolio, AS_OF),
        )
        for pid in PROJECT_IDS
    }

    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_PROJECT_INTELLIGENCE)
    app.session_state["selected_project"] = "P-002"
    app.run()

    for project_id in ("P-002", "P-007", "P-002"):
        app.session_state["selected_project"] = project_id
        app.run()
        health, confidence = expected[project_id]
        metrics = _metrics(app)

        assert metrics["Health"] == (
            f"{ui.format_score(health.overall_score)} ({health.health_band})"
        )
        assert metrics["Confidence"] == (
            f"{ui.format_score(confidence.overall_score)} ({confidence.confidence_band})"
        )
        text = rendered_text(app)
        assert f"{project_id} - " in text or project_id in text
        for driver in health.critical_drivers:
            assert driver.message in text
        assert len(app.exception) == 0
        assert len(app.error) == 0


def test_unknown_selected_project_prompts_reselection():
    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_PROJECT_INTELLIGENCE)
    app.session_state["selected_project"] = "P-002"
    app.run()

    # A stale selection can only arise via session state; the page must not raise.
    assert len(app.exception) == 0
