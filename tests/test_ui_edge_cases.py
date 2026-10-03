"""Edge-case and robustness tests driven through the real pages.

A synthetic portfolio is injected into session state before the page runs. The shell only loads
real data when session state is empty, so an injected portfolio survives the page run and the page
renders entirely from it.
"""

from __future__ import annotations

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from src import ui_formatting as ui
from src.risk_engine import ALERT_REQUIREMENT_VERIFICATION, generate_early_warnings
from tests.conftest import (
    APP_PATH,
    PAGE_ASK_EPOS,
    PAGE_CHANGE_IMPACT,
    PAGE_DASHBOARD,
    PAGE_PROJECT_INTELLIGENCE,
    PAGE_SCENARIO,
    PAGE_TRACEABILITY,
    frame_named,
    rendered_text,
)

AS_OF = ui.ANALYSIS_DATE
TEST_PROJECT_ID = "P-TEST"

# The Portfolio Dashboard and Project Intelligence caches key on the reference date and not on
# portfolio contents (see docs/pending-decisions.md), so each injected-portfolio scenario uses its
# own distinct reference date to guarantee a distinct cache entry.
EMPTY_AS_OF = date(2026, 9, 1)
MANY_ALERTS_AS_OF = date(2026, 9, 2)


@pytest.fixture
def inject_portfolio(monkeypatch):
    """Open a page against an injected synthetic portfolio at a chosen reference date.

    The portfolio is injected before the first run so the very first render already uses it; the
    shell only loads real data when session state is empty.
    """

    def _open(page_path: str, portfolio, as_of: date = AS_OF, **session_state) -> AppTest:
        monkeypatch.setattr(ui, "ANALYSIS_DATE", as_of)
        app = AppTest.from_file(APP_PATH, default_timeout=120)
        app.session_state["portfolio"] = portfolio
        app.session_state["load_error"] = None
        for key, value in session_state.items():
            app.session_state[key] = value
        app.run()
        if page_path != PAGE_DASHBOARD:
            app.switch_page(page_path)
            app.run()
        return app

    return _open


# ------------------------------------------------------- 1. empty project (max fallbacks)
@pytest.fixture
def empty_project_portfolio(make_portfolio, make_project):
    """A project with no milestones, tasks, risks, dependencies, resources or actions."""
    # Status is recent relative to EMPTY_AS_OF so no stale-status alert is raised.
    return make_portfolio(projects=[make_project(status_update_date=date(2026, 8, 28))])


def test_project_intelligence_handles_a_completely_empty_project(
    inject_portfolio, empty_project_portfolio
):
    app = inject_portfolio(
        PAGE_PROJECT_INTELLIGENCE,
        empty_project_portfolio,
        EMPTY_AS_OF,
        selected_project=TEST_PROJECT_ID,
    )
    text = rendered_text(app)

    assert len(app.exception) == 0
    assert len(app.error) == 0
    # Documented fallback limitations are shown rather than a blank or broken section.
    assert "No milestones are available" in text
    assert "No tasks are available" in text
    assert "No dependency data is available" in text
    assert "No resource data is available" in text
    assert "No action data is available" in text
    assert "Assumptions and limitations" in text


def test_dashboard_handles_a_completely_empty_project(inject_portfolio, empty_project_portfolio):
    app = inject_portfolio(PAGE_DASHBOARD, empty_project_portfolio, EMPTY_AS_OF)
    text = rendered_text(app)

    assert len(app.exception) == 0
    assert len(app.error) == 0
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Total projects"] == "1"
    assert "No milestones are available" in text

    overview = frame_named(app, "Project", "Health", "Confidence")
    assert overview["Project"].tolist() == [TEST_PROJECT_ID]
    assert 0.0 <= overview["Health"].iloc[0] <= 100.0


def test_dashboard_handles_a_project_with_no_alerts(inject_portfolio, empty_project_portfolio):
    """An empty project raises no alerts, so the exceptions panel must say so explicitly."""
    app = inject_portfolio(PAGE_DASHBOARD, empty_project_portfolio, EMPTY_AS_OF)
    text = rendered_text(app)
    assert "No early-warning alerts were generated" in text
    assert len(app.exception) == 0


# ------------------------------------------------------- 2. no change requests
def test_change_impact_handles_a_project_with_no_change_requests(
    inject_portfolio, make_portfolio, make_project, make_requirement
):
    portfolio = make_portfolio(
        projects=[make_project()], requirements=[make_requirement()], change_requests=[]
    )
    app = inject_portfolio(PAGE_CHANGE_IMPACT, portfolio, selected_project=TEST_PROJECT_ID)
    text = rendered_text(app)

    assert len(app.exception) == 0
    assert len(app.error) == 0
    assert f"No change requests are recorded for {TEST_PROJECT_ID}" in text
    # The page stops cleanly rather than rendering an empty impact panel.
    assert not any(sub.value == "Impact result" for sub in app.subheader)


# ------------------------------------------------------- 3. no dependencies
def test_scenario_planner_handles_a_project_with_no_dependencies(
    inject_portfolio, make_portfolio, make_project, make_milestone, make_task
):
    portfolio = make_portfolio(
        projects=[make_project()],
        milestones=[make_milestone()],
        tasks=[make_task()],
        dependencies=[],
    )
    app = inject_portfolio(PAGE_SCENARIO, portfolio, selected_project=TEST_PROJECT_ID)
    text = rendered_text(app)

    assert len(app.exception) == 0
    assert len(app.error) == 0
    assert f"No dependencies are recorded for {TEST_PROJECT_ID}" in text
    assert not any(sub.value == "Baseline versus scenario" for sub in app.subheader)


def test_scenario_planner_handles_dependencies_belonging_only_to_another_project(
    inject_portfolio, make_portfolio, make_project, make_dependency
):
    portfolio = make_portfolio(
        projects=[make_project()],
        dependencies=[make_dependency(dependency_id="D-OTHER", project_id="P-OTHER")],
    )
    app = inject_portfolio(PAGE_SCENARIO, portfolio, selected_project=TEST_PROJECT_ID)
    assert len(app.exception) == 0
    assert f"No dependencies are recorded for {TEST_PROJECT_ID}" in rendered_text(app)


# ------------------------------------------------------- 4. dangling verified_by link
@pytest.fixture
def dangling_link_portfolio(make_portfolio, make_project, make_requirement, make_trace_link):
    """A verified_by link whose target test case does not exist in the loaded data."""
    return make_portfolio(
        projects=[make_project()],
        requirements=[make_requirement(requirement_id="REQ-DANGLE", priority="Critical")],
        test_cases=[],
        trace_links=[
            make_trace_link(
                trace_link_id="TL-DANGLE",
                source_id="REQ-DANGLE",
                target_type="TestCase",
                target_id="TC-MISSING",
                link_type="verified_by",
            )
        ],
    )


def test_dangling_verified_by_link_is_handled_identically_by_page_and_rule8(
    inject_portfolio, dangling_link_portfolio
):
    # Engine side: Rule 8 treats an unresolvable link as no verification path.
    alerts = [
        alert
        for alert in generate_early_warnings(TEST_PROJECT_ID, dangling_link_portfolio, AS_OF)
        if alert.alert_type == ALERT_REQUIREMENT_VERIFICATION
    ]
    assert len(alerts) == 1
    assert alerts[0].severity == "Critical"
    assert alerts[0].source_ids == ["REQ-DANGLE"]

    # UI side: the page reaches the same conclusion and does not crash.
    app = inject_portfolio(
        PAGE_TRACEABILITY, dangling_link_portfolio, selected_project=TEST_PROJECT_ID
    )
    assert len(app.exception) == 0
    assert len(app.error) == 0

    frame = frame_named(app, "Requirement", "Trace status")
    row = frame[frame["Requirement"] == "REQ-DANGLE"].iloc[0]
    assert row["Trace status"] == ui.TRACE_NO_LINK
    assert row["Test status"] == "No linked test case"

    text = rendered_text(app)
    assert alerts[0].explanation in text
    # The dangling link is still shown in the raw reference table for transparency.
    links = frame_named(app, "Trace link", "Target")
    assert "TC-MISSING" in links["Target"].tolist()


def test_dangling_link_does_not_break_project_intelligence(
    inject_portfolio, dangling_link_portfolio
):
    app = inject_portfolio(
        PAGE_PROJECT_INTELLIGENCE,
        dangling_link_portfolio,
        date(2026, 9, 3),
        selected_project=TEST_PROJECT_ID,
    )
    assert len(app.exception) == 0
    assert len(app.error) == 0


# ------------------------------------------------------- 5. very many alerts
@pytest.fixture
def many_alerts_portfolio(make_portfolio, make_project, make_milestone, make_risk, make_resource):
    """A project engineered to raise well over twenty alerts."""
    milestones = [
        make_milestone(
            milestone_id=f"M-{index}",
            criticality="Critical",
            baseline_date=date(2026, 1, 1),
            forecast_date=date(2026, 6, 1),
            status="Delayed",
        )
        for index in range(10)
    ]
    risks = [
        make_risk(risk_id=f"R-{index}", probability=5, impact=5, mitigation_owner=None)
        for index in range(10)
    ]
    resources = [
        make_resource(resource_id=f"RES-{index}", allocated_hours=200, capacity_hours=100)
        for index in range(10)
    ]
    return make_portfolio(
        projects=[make_project(status_update_date=date(2026, 1, 1))],
        milestones=milestones,
        risks=risks,
        resources=resources,
    )


def test_exceptions_panel_handles_many_alerts(inject_portfolio, many_alerts_portfolio):
    alerts = generate_early_warnings(TEST_PROJECT_ID, many_alerts_portfolio, MANY_ALERTS_AS_OF)
    assert len(alerts) >= 20, "fixture should generate a large alert volume"

    app = inject_portfolio(PAGE_DASHBOARD, many_alerts_portfolio, MANY_ALERTS_AS_OF)
    assert len(app.exception) == 0
    assert len(app.error) == 0

    text = rendered_text(app)
    frame = frame_named(app, "Severity", "Project", "Title")

    # Nothing is hidden silently: the panel states how many of how many are shown.
    assert f"of {len(alerts)} alerts" in text
    assert len(frame) == 10, "the default view shows the first ten"

    slider = app.slider[0]
    assert slider.max == len(alerts)

    # Raising the control reveals every alert, in the engine's stable order.
    app.slider[0].set_value(len(alerts)).run()
    full = frame_named(app, "Severity", "Project", "Title")
    assert len(full) == len(alerts)
    assert full["Title"].tolist() == [alert.title for alert in alerts]


def test_many_alerts_are_ordered_by_severity_on_the_page(inject_portfolio, many_alerts_portfolio):
    app = inject_portfolio(PAGE_DASHBOARD, many_alerts_portfolio, MANY_ALERTS_AS_OF)
    frame = frame_named(app, "Severity", "Project", "Title")
    rank = {name: index for index, name in enumerate(ui.SEVERITIES)}
    shown = frame["Severity"].tolist()
    assert shown == sorted(shown, key=lambda severity: rank[severity])


# ------------------------------------------------------- additional robustness
def test_ask_epos_handles_a_project_with_no_evidence(
    inject_portfolio, empty_project_portfolio, monkeypatch
):
    """A question with no matching evidence must state that plainly, not render an empty table."""
    import src.config as config_module
    from src.config import AzureOpenAISettings

    monkeypatch.setattr(
        config_module,
        "get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )

    from src import ai_assistant as ai

    app = inject_portfolio(
        PAGE_ASK_EPOS,
        empty_project_portfolio,
        EMPTY_AS_OF,
        ask_question_type=ai.QUESTION_RISKS_WITHOUT_OWNER,
    )
    assert len(app.exception) == 0
    assert "No evidence records were found" in rendered_text(app)


def test_pages_report_a_load_error_without_a_stack_trace():
    """When the shell records a load error, every page shows a professional message."""
    for page in (
        PAGE_DASHBOARD,
        PAGE_PROJECT_INTELLIGENCE,
        PAGE_TRACEABILITY,
        PAGE_CHANGE_IMPACT,
        PAGE_SCENARIO,
        PAGE_ASK_EPOS,
    ):
        app = AppTest.from_file(APP_PATH, default_timeout=120)
        app.run()
        app.switch_page(page)
        app.session_state["portfolio"] = None
        app.session_state["load_error"] = "simulated load failure"
        app.run()

        assert len(app.exception) == 0, f"{page} raised instead of reporting the load error"
        assert any(
            "Portfolio data could not be loaded" in element.value for element in app.error
        ), f"{page} did not show the load-error message"
