"""Scenario Planner page (presentation only).

Runs the deterministic scenario engine for a selected dependency and renders the baseline versus
scenario comparison. The page performs no simulation logic of its own and never modifies baseline
data; the engine works on a temporary in-memory copy.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src import scoring_rules as sr
from src import ui_formatting as ui
from src.scenario_engine import simulate_dependency_delay
from src.validators import DataValidationError

logger = logging.getLogger(__name__)
AS_OF = ui.ANALYSIS_DATE

st.header("Scenario Planner")
st.caption(
    f"Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1). "
    "All data is synthetic. No AI-generated content appears on this page."
)
st.write(
    "This is a what-if simulator. Results are evidence-based recalculations produced by the real "
    "Health, Confidence and Risk engines running against a temporary in-memory copy of the data. "
    "No baseline data is ever modified. Version 1 simulates a single dependency delay at a time."
)
st.warning(
    "Scenario results are simulated. Running a scenario does not alter the Portfolio Dashboard, "
    "Project Intelligence, or any other page's data."
)

portfolio = st.session_state.get("portfolio")
if st.session_state.get("load_error") or portfolio is None:
    st.error(
        "Portfolio data could not be loaded. Check the local CSV data in the data folder. "
        "Diagnostic detail has been written to the local logs."
    )
    st.stop()

project_ids = sorted(portfolio.project_ids)
names = {p.project_id: p.project_name for p in portfolio.projects}
selected_project = st.selectbox(
    "Select a project",
    project_ids,
    key="selected_project",
    format_func=lambda pid: f"{pid} - {names.get(pid, '')}",
)

dependencies = sorted(
    (d for d in portfolio.dependencies if d.project_id == selected_project),
    key=lambda d: d.dependency_id,
)
if not dependencies:
    st.info(f"No dependencies are recorded for {selected_project}.")
    st.stop()

by_id = {d.dependency_id: d for d in dependencies}
options = list(by_id)
# Reset a stale selection carried over from another project.
if st.session_state.get("selected_dependency") not in options:
    st.session_state["selected_dependency"] = options[0]

selected_dependency = st.selectbox(
    "Select a dependency to delay",
    options,
    key="selected_dependency",
    format_func=lambda did: (
        f"{did} - {by_id[did].dependency_name} ({by_id[did].criticality}, "
        f"{by_id[did].status}, {by_id[did].delay_days}d)"
    ),
)

additional_delay_days = st.number_input(
    "Additional delay (calendar days)",
    min_value=sr.SCENARIO_MIN_DELAY_DAYS,
    max_value=sr.SCENARIO_MAX_DELAY_DAYS,
    value=30,
    step=1,
    key="scenario_delay_days",
    help=(
        f"Between {sr.SCENARIO_MIN_DELAY_DAYS} and {sr.SCENARIO_MAX_DELAY_DAYS} days, matching "
        "the engine's validation bounds."
    ),
)

if st.button("Run scenario", type="primary"):
    st.session_state["scenario_request"] = {
        "dependency_id": selected_dependency,
        "days": int(additional_delay_days),
    }

request = st.session_state.get("scenario_request")
if request is None or request["dependency_id"] not in by_id:
    st.info("Select a dependency and a delay, then choose Run scenario.")
    st.stop()

try:
    result = simulate_dependency_delay(request["dependency_id"], request["days"], portfolio, AS_OF)
except DataValidationError as exc:
    logger.exception("Scenario simulation failed for %s", request["dependency_id"])
    st.error(
        "The scenario could not be simulated. Please check the dependency and delay value. "
        f"Detail: {'; '.join(exc.issues)}"
    )
    st.stop()

comparison = result.affected_projects[0]

# ------------------------------------------------------------------ comparison
st.subheader("Baseline versus scenario")
st.caption(
    f"Dependency {result.dependency_id} delay raised from "
    f"{ui.format_days(result.baseline_delay_days)} to "
    f"{ui.format_days(result.scenario_delay_days)}."
)

health_columns = st.columns(2)
health_columns[0].metric(
    "Baseline Health",
    f"{ui.format_score(comparison.baseline_health_score)} ({comparison.baseline_health_band})",
)
health_columns[1].metric(
    "Scenario Health",
    f"{ui.format_score(comparison.scenario_health_score)} ({comparison.scenario_health_band})",
    delta=ui.format_score_delta(comparison.health_score_delta),
)

confidence_columns = st.columns(2)
confidence_columns[0].metric(
    "Baseline Confidence",
    f"{ui.format_score(comparison.baseline_confidence_score)} "
    f"({comparison.baseline_confidence_band})",
)
confidence_columns[1].metric(
    "Scenario Confidence",
    f"{ui.format_score(comparison.scenario_confidence_score)} "
    f"({comparison.scenario_confidence_band})",
    delta=ui.format_score_delta(comparison.confidence_score_delta),
)

st.markdown("**Alerts by severity**")
st.dataframe(
    pd.DataFrame(
        [
            {
                "Severity": severity,
                "Baseline": comparison.baseline_alert_counts.get(severity, 0),
                "Scenario": comparison.scenario_alert_counts.get(severity, 0),
                "Change": (
                    comparison.scenario_alert_counts.get(severity, 0)
                    - comparison.baseline_alert_counts.get(severity, 0)
                ),
            }
            for severity in ui.SEVERITIES
        ]
    ),
    hide_index=True,
    width="stretch",
)
st.markdown(f"New alerts: {ui.format_source_ids(comparison.new_alert_ids)}")
st.markdown(f"Resolved alerts: {ui.format_source_ids(comparison.resolved_alert_ids)}")

st.markdown(result.deterministic_explanation)

st.markdown("**Assumptions and limitations** (context, not findings)")
for item in result.assumptions_or_limitations:
    st.markdown(f"- {item}")

st.caption("See Project Intelligence for this project's full baseline context.")
st.page_link("pages/2_Project_Intelligence.py", label="Project Intelligence")
