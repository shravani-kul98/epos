"""Value-level UI tests for the Portfolio Dashboard page.

Expected values are computed from the engines inside each test, never hardcoded, so these stay
correct if the synthetic data changes.
"""

from __future__ import annotations

from src import ui_formatting as ui
from src.confidence_engine import calculate_project_confidence
from src.data_loader import load_portfolio
from src.health_engine import calculate_project_health
from src.risk_engine import generate_portfolio_early_warnings
from tests.conftest import AS_OF, PAGE_DASHBOARD, frame_named, rendered_text


def _expected():
    portfolio = load_portfolio()
    project_ids = sorted(portfolio.project_ids)
    health = {pid: calculate_project_health(pid, portfolio, AS_OF) for pid in project_ids}
    confidence = {pid: calculate_project_confidence(pid, portfolio, AS_OF) for pid in project_ids}
    alerts = generate_portfolio_early_warnings(portfolio, AS_OF)
    return portfolio, project_ids, health, confidence, alerts


def _metrics(app) -> dict[str, str]:
    return {metric.label: metric.value for metric in app.metric}


def test_kpi_metrics_match_engine_output(open_page):
    portfolio, project_ids, health, confidence, alerts = _expected()
    app = open_page(PAGE_DASHBOARD)
    metrics = _metrics(app)

    health_counts = ui.count_health_bands(health.values())
    confidence_counts = ui.count_confidence_bands(confidence.values())
    severity_counts = ui.count_alert_severities(alerts)

    assert metrics["Total projects"] == str(len(project_ids))
    assert metrics["Green Health"] == str(health_counts["Green"])
    assert metrics["Amber Health"] == str(health_counts["Amber"])
    assert metrics["Red Health"] == str(health_counts["Red"])
    assert metrics["High Confidence"] == str(confidence_counts["High"])
    assert metrics["Medium Confidence"] == str(confidence_counts["Medium"])
    assert metrics["Low Confidence"] == str(confidence_counts["Low"])
    assert metrics["Critical and High alerts"] == str(
        severity_counts["Critical"] + severity_counts["High"]
    )


def test_overview_table_matches_engine_scores(open_page):
    portfolio, project_ids, health, confidence, _ = _expected()
    app = open_page(PAGE_DASHBOARD)
    frame = frame_named(app, "Project", "Health", "Confidence")

    assert sorted(frame["Project"].tolist()) == project_ids
    for _, row in frame.iterrows():
        project_id = row["Project"]
        assert row["Health"] == health[project_id].overall_score
        assert row["Health band"] == health[project_id].health_band
        assert row["Confidence"] == confidence[project_id].overall_score
        assert row["Confidence band"] == confidence[project_id].confidence_band
        project = portfolio.get_project(project_id)
        assert row["Name"] == project.project_name


def test_overview_table_alert_counts_match_per_project(open_page):
    portfolio, project_ids, _, _, alerts = _expected()
    app = open_page(PAGE_DASHBOARD)
    frame = frame_named(app, "Project", "Critical", "High")

    for project_id in project_ids:
        project_alerts = [a for a in alerts if a.project_id == project_id]
        counts = ui.count_alert_severities(project_alerts)
        row = frame[frame["Project"] == project_id].iloc[0]
        for severity in ("Critical", "High", "Medium", "Low"):
            assert row[severity] == counts[severity]


def test_exceptions_panel_count_and_severity_order(open_page):
    _, _, _, _, alerts = _expected()
    app = open_page(PAGE_DASHBOARD)
    frame = frame_named(app, "Severity", "Project", "Title")

    # The panel shows the first N of the engine's stable ordering, and says so explicitly.
    assert len(frame) <= len(alerts)
    assert f"of {len(alerts)} alerts" in rendered_text(app)

    shown = frame["Severity"].tolist()
    rank = {name: index for index, name in enumerate(ui.SEVERITIES)}
    assert shown == sorted(shown, key=lambda severity: rank[severity])

    # The displayed rows are exactly the leading slice of the engine's ordering.
    expected_leading = [alert.severity for alert in alerts][: len(frame)]
    assert shown == expected_leading
    assert frame["Title"].tolist() == [a.title for a in alerts][: len(frame)]


def test_exceptions_panel_shows_every_alert_when_slider_raised(open_page):
    _, _, _, _, alerts = _expected()
    app = open_page(PAGE_DASHBOARD)
    app.slider[0].set_value(len(alerts)).run()

    frame = frame_named(app, "Severity", "Project", "Title")
    assert len(frame) == len(alerts)
    assert frame["Title"].tolist() == [alert.title for alert in alerts]


def test_per_project_expanders_render_engine_explanations(open_page):
    _, project_ids, health, confidence, _ = _expected()
    app = open_page(PAGE_DASHBOARD)
    text = rendered_text(app)

    # Data-quality issues render as tables; explanations render as markdown.
    issue_messages: set[str] = set()
    for element in app.dataframe:
        frame = element.value
        if "Message" in frame.columns:
            issue_messages |= set(frame["Message"].tolist())

    for project_id in project_ids:
        for lines in health[project_id].factor_explanations.values():
            for line in lines:
                assert line in text
        for issue in confidence[project_id].data_quality_issues:
            assert issue.message in issue_messages


def test_per_project_factor_scores_match_engine(open_page):
    _, project_ids, health, confidence, _ = _expected()
    app = open_page(PAGE_DASHBOARD)

    rendered_tables = [
        dict(zip(element.value["Factor"], element.value["Score"], strict=True))
        for element in app.dataframe
        if {"Factor", "Score"} <= set(element.value.columns)
    ]

    # Each project contributes one health table and one confidence table, rendered verbatim.
    for project_id in project_ids:
        assert health[project_id].factor_scores in rendered_tables
        assert confidence[project_id].factor_scores in rendered_tables


def test_methodology_disclosure_present(open_page):
    app = open_page(PAGE_DASHBOARD)
    text = rendered_text(app)
    assert "All data" in text and "synthetic" in text
    assert "docs/scoring-methodology.md" in text
    assert "No GPT-4o or AI-generated content appears anywhere on this page" in text


def test_no_errors_rendered(open_page):
    app = open_page(PAGE_DASHBOARD)
    assert len(app.exception) == 0
    assert len(app.error) == 0
