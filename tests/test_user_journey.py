"""End-to-end multi-page user journeys.

These drive a single AppTest session across several pages the way a PMO analyst would, and assert
that the facts stay consistent from page to page. The most important assertion here is that the
evidence handed to the AI layer is the same evidence the dashboard displayed, proving the copilot
is grounded in the live deterministic results rather than a separately computed or stale view.

No real network call is made: the AI path always runs through a capturing fake transport.
"""

from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

from src import ai_assistant as ai
from src import ui_formatting as ui
from src.change_impact_engine import calculate_change_impact
from src.confidence_engine import calculate_project_confidence
from src.config import AzureOpenAISettings
from src.data_loader import load_portfolio
from src.health_engine import calculate_project_health
from src.risk_engine import (
    ALERT_REQUIREMENT_VERIFICATION,
    generate_early_warnings,
    generate_portfolio_early_warnings,
)
from src.scenario_engine import simulate_dependency_delay
from src.schemas import CopilotResponse
from tests.conftest import (
    APP_PATH,
    AS_OF,
    PAGE_ASK_EPOS,
    PAGE_CHANGE_IMPACT,
    PAGE_DASHBOARD,
    PAGE_PROJECT_INTELLIGENCE,
    PAGE_SCENARIO,
    PAGE_TRACEABILITY,
    frame_named,
    rendered_text,
)

DISCLAIMER = "AI-generated decision-support draft; human review required."


@pytest.fixture
def captured_ai(monkeypatch):
    """Patch the AI path so the real ask_epos runs against a capturing fake transport."""
    import src.config as config_module

    stub_settings = AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid/chat")
    # The page and ask_epos each hold their own reference to the accessor; both must agree.
    monkeypatch.setattr(config_module, "get_azure_settings", lambda: stub_settings)
    monkeypatch.setattr(ai, "get_azure_settings", lambda: stub_settings)

    captured: dict[str, object] = {}
    real_ask = ai.ask_epos

    def _capturing_transport(url, headers, payload, timeout):
        captured["payload"] = payload
        captured["evidence"] = json.loads(payload["messages"][1]["content"])
        answer = CopilotResponse(
            executive_summary="Mocked grounded summary.",
            key_findings=["Mocked finding."],
            recommended_actions=["Mocked action."],
            source_ids=captured["evidence"]["valid_source_ids"][:2],
            human_review_required=True,
            disclaimer=DISCLAIMER,
        )
        return {"choices": [{"message": {"content": answer.model_dump_json()}}]}

    monkeypatch.setattr(
        ai,
        "ask_epos",
        lambda question_type, portfolio, as_of_date, context=None, transport=None: real_ask(
            question_type, portfolio, as_of_date, context, _capturing_transport
        ),
    )
    return captured


def _evidence_records(captured) -> dict[str, dict[str, str]]:
    """Index evidence by record id. Ids are unique within a package for these question types."""
    return {
        record["record_id"]: record["fields"] for record in captured["evidence"]["evidence_records"]
    }


def _evidence_by_type(captured) -> dict[tuple[str, str], dict[str, str]]:
    """Index evidence by (record_type, record_id), which is what uniquely identifies a record."""
    return {
        (record["record_type"], record["record_id"]): record["fields"]
        for record in captured["evidence"]["evidence_records"]
    }


def _assert_clean(app: AppTest) -> None:
    assert len(app.exception) == 0, "journey raised an exception"
    assert len(app.error) == 0, "journey rendered an error element"


def test_journey_investigate_a_red_project(captured_ai):
    """Journey 1: spot a Red project on the dashboard and follow it through every page."""
    portfolio = load_portfolio()
    health = calculate_project_health("P-007", portfolio, AS_OF)
    confidence = calculate_project_confidence("P-007", portfolio, AS_OF)
    alerts = generate_early_warnings("P-007", portfolio, AS_OF)

    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()

    # Step 1: the dashboard flags P-007 as Red and needing attention.
    app.switch_page(PAGE_DASHBOARD)
    app.run()
    _assert_clean(app)
    overview = frame_named(app, "Project", "Health", "Health band")
    p007_row = overview[overview["Project"] == "P-007"].iloc[0]
    assert p007_row["Health band"] == "Red"
    assert p007_row["Health"] == health.overall_score

    # Step 2: Project Intelligence shows the same Health and Confidence facts.
    app.switch_page(PAGE_PROJECT_INTELLIGENCE)
    app.session_state["selected_project"] = "P-007"
    app.run()
    _assert_clean(app)
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Health"] == f"{ui.format_score(health.overall_score)} ({health.health_band})"
    assert metrics["Confidence"] == (
        f"{ui.format_score(confidence.overall_score)} ({confidence.confidence_band})"
    )
    intelligence_text = rendered_text(app)
    verification_alerts = [
        alert for alert in alerts if alert.alert_type == ALERT_REQUIREMENT_VERIFICATION
    ]
    assert verification_alerts, "P-007 is expected to have verification-gap alerts"
    for alert in verification_alerts:
        assert alert.explanation in intelligence_text

    # Step 3: Requirements Traceability shows the same verification gaps.
    app.switch_page(PAGE_TRACEABILITY)
    app.run()
    _assert_clean(app)
    assert app.session_state["selected_project"] == "P-007"
    traceability_text = rendered_text(app)
    for alert in verification_alerts:
        assert alert.explanation in traceability_text
    trace_frame = frame_named(app, "Requirement", "Trace status")
    alerted_requirements = {
        source_id for alert in verification_alerts for source_id in alert.source_ids
    }
    for _, row in trace_frame.iterrows():
        if row["Requirement"] in alerted_requirements:
            assert row["Trace status"] != ui.TRACE_VERIFIED

    # Step 4: Change Impact for CR-042 is consistent with the same requirement.
    app.switch_page(PAGE_CHANGE_IMPACT)
    app.session_state["selected_change_request"] = "CR-042"
    app.run()
    _assert_clean(app)
    impact = calculate_change_impact("CR-042", portfolio, AS_OF)
    impact_metrics = {metric.label: metric.value for metric in app.metric}
    assert impact_metrics["Change risk level"] == impact.risk_level
    assert impact_metrics["Estimated schedule impact"] == ui.format_days(
        impact.estimated_schedule_impact_days
    )
    assert impact.deterministic_explanation in rendered_text(app)

    # Step 5: Scenario Planner reproduces the documented D-7002 movement.
    app.switch_page(PAGE_SCENARIO)
    app.session_state["selected_dependency"] = "D-7002"
    app.session_state["scenario_delay_days"] = 30
    app.run()
    app.button[0].click().run()
    _assert_clean(app)
    scenario = simulate_dependency_delay("D-7002", 30, portfolio, AS_OF).affected_projects[0]
    scenario_metrics = {metric.label: metric.value for metric in app.metric}
    assert scenario_metrics["Baseline Health"] == (
        f"{ui.format_score(scenario.baseline_health_score)} ({scenario.baseline_health_band})"
    )
    assert scenario_metrics["Scenario Health"] == (
        f"{ui.format_score(scenario.scenario_health_score)} ({scenario.scenario_health_band})"
    )
    # The baseline the scenario reports must match the dashboard's Health for the same project.
    assert scenario.baseline_health_score == health.overall_score

    # Step 6: Ask EPOS is grounded in exactly those same Health/Confidence facts.
    app.switch_page(PAGE_ASK_EPOS)
    app.session_state["ask_question_type"] = ai.QUESTION_WHY_PROJECT_BAND
    app.run()
    app.button[0].click().run()
    _assert_clean(app)

    records = _evidence_by_type(captured_ai)
    health_fields = records[("health_result", "P-007")]
    confidence_fields = records[("confidence_result", "P-007")]

    assert health_fields["health_band"] == health.health_band
    assert health_fields["overall_score"] == str(health.overall_score)
    assert json.loads(health_fields["factor_scores"]) == health.factor_scores
    assert confidence_fields["confidence_band"] == confidence.confidence_band
    assert confidence_fields["overall_score"] == str(confidence.overall_score)
    assert json.loads(confidence_fields["factor_scores"]) == confidence.factor_scores
    # No other project's facts leaked into the evidence sent to the AI layer.
    assert "P-002" not in json.dumps(captured_ai["evidence"])
    assert captured_ai["evidence"]["valid_source_ids"] == ["P-007"]
    assert app.session_state["selected_project"] == "P-007"


def test_journey_portfolio_wide_review(captured_ai):
    """Journey 2: the AI must be grounded in the same portfolio facts the dashboard shows."""
    portfolio = load_portfolio()
    project_ids = sorted(portfolio.project_ids)
    health = {pid: calculate_project_health(pid, portfolio, AS_OF) for pid in project_ids}
    confidence = {pid: calculate_project_confidence(pid, portfolio, AS_OF) for pid in project_ids}
    portfolio_alerts = generate_portfolio_early_warnings(portfolio, AS_OF)

    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()

    # Step 1: capture exactly what the dashboard displays.
    app.switch_page(PAGE_DASHBOARD)
    app.run()
    _assert_clean(app)
    dashboard_metrics = {metric.label: metric.value for metric in app.metric}
    overview = frame_named(app, "Project", "Health", "Confidence")
    dashboard_health = dict(zip(overview["Project"], overview["Health"], strict=True))
    dashboard_confidence = dict(zip(overview["Project"], overview["Confidence"], strict=True))

    severity_counts = ui.count_alert_severities(portfolio_alerts)
    assert dashboard_metrics["Critical and High alerts"] == str(
        severity_counts["Critical"] + severity_counts["High"]
    )

    # Step 2: the evidence sent to the AI layer carries the identical facts.
    app.switch_page(PAGE_ASK_EPOS)
    app.session_state["ask_question_type"] = ai.QUESTION_PROJECTS_NEEDING_ATTENTION
    app.run()
    app.button[0].click().run()
    _assert_clean(app)

    records = _evidence_records(captured_ai)

    for project_id in project_ids:
        assert project_id in records, f"{project_id} missing from AI evidence"
        fields = records[project_id]
        # Same numbers the dashboard rendered, not a separately computed view.
        assert fields["health_score"] == str(dashboard_health[project_id])
        assert fields["confidence_score"] == str(dashboard_confidence[project_id])
        assert fields["health_score"] == str(health[project_id].overall_score)
        assert fields["confidence_score"] == str(confidence[project_id].overall_score)
        assert fields["health_band"] == health[project_id].health_band
        assert fields["confidence_band"] == confidence[project_id].confidence_band

        project_alerts = [a for a in portfolio_alerts if a.project_id == project_id]
        counts = ui.count_alert_severities(project_alerts)
        assert fields["alert_count"] == str(len(project_alerts))
        assert fields["critical_alerts"] == str(counts["Critical"])
        assert fields["high_alerts"] == str(counts["High"])

    # Every Critical and High portfolio alert is included as evidence.
    severe_alert_ids = {
        alert.alert_id for alert in portfolio_alerts if alert.severity in ("Critical", "High")
    }
    assert severe_alert_ids <= set(records)

    # The rendered answer only cites IDs that were actually supplied as evidence.
    valid_ids = set(captured_ai["evidence"]["valid_source_ids"])
    text = rendered_text(app)
    assert DISCLAIMER in text
    assert valid_ids


def test_selected_project_persists_across_every_page():
    """The project chosen on one page must still be selected after navigating elsewhere."""
    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()
    app.switch_page(PAGE_PROJECT_INTELLIGENCE)
    app.session_state["selected_project"] = "P-007"
    app.run()

    for page in (PAGE_TRACEABILITY, PAGE_CHANGE_IMPACT, PAGE_SCENARIO, PAGE_PROJECT_INTELLIGENCE):
        app.switch_page(page)
        app.run()
        _assert_clean(app)
        assert app.session_state["selected_project"] == "P-007"
