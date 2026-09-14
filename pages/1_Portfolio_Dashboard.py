"""Portfolio Dashboard page (presentation only).

Renders portfolio-wide KPIs, a Health-versus-Confidence overview, the most severe alerts and
per-project evidence. Every value shown comes directly from the deterministic engines; this page
adds no scoring, banding or alert logic of its own.
"""

from __future__ import annotations

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from src import ui_formatting as ui
from src.confidence_engine import calculate_project_confidence
from src.health_engine import calculate_project_health
from src.risk_engine import generate_early_warnings, generate_portfolio_early_warnings

logger = logging.getLogger(__name__)
AS_OF = ui.ANALYSIS_DATE


@st.cache_data(show_spinner=False)
def _compute(_portfolio, as_of):
    """Run the three engines per project plus the portfolio-level alert ordering (cached)."""

    def analyze(project_id: str):
        return {
            "health": calculate_project_health(project_id, _portfolio, as_of),
            "confidence": calculate_project_confidence(project_id, _portfolio, as_of),
            "alerts": generate_early_warnings(project_id, _portfolio, as_of),
        }

    results, failures = ui.gather_project_analysis(sorted(_portfolio.project_ids), analyze)
    portfolio_alerts = generate_portfolio_early_warnings(_portfolio, as_of)
    return results, failures, portfolio_alerts


st.header("Portfolio Dashboard")
st.caption(
    f"Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1). "
    "All data is synthetic. No AI-generated content appears on this page."
)
st.write(
    "EPOS Lite consolidates selected, validated engineering project signals into one "
    "explainable management view."
)

portfolio = st.session_state.get("portfolio")
if st.session_state.get("load_error") or portfolio is None:
    st.error(
        "Portfolio data could not be loaded. Check the local CSV data in the data folder. "
        "Diagnostic detail has been written to the local logs."
    )
    st.stop()

results, failures, portfolio_alerts = _compute(portfolio, AS_OF)
health_results = [r["health"] for r in results.values()]
confidence_results = [r["confidence"] for r in results.values()]

health_counts = ui.count_health_bands(health_results)
confidence_counts = ui.count_confidence_bands(confidence_results)
severity_counts = ui.count_alert_severities(portfolio_alerts)

if failures:
    st.warning(
        "Some projects could not be analysed and are omitted from the detail below: "
        + ", ".join(failures)
    )

# ------------------------------------------------------------------ KPI summary row
st.subheader("Portfolio KPIs")
st.caption(
    "Health measures delivery performance; Confidence measures how trustworthy the underlying "
    "data is. Alerts are specific, evidence-based conditions ranked by severity."
)
row1 = st.columns(4)
row1[0].metric("Total projects", len(portfolio.project_ids))
row1[1].metric("Green Health", health_counts["Green"], help="Health score 80-100.")
row1[2].metric("Amber Health", health_counts["Amber"], help="Health score 60-79.9.")
row1[3].metric("Red Health", health_counts["Red"], help="Health score below 60.")

row2 = st.columns(4)
row2[0].metric("High Confidence", confidence_counts["High"], help="Confidence score 80-100.")
row2[1].metric("Medium Confidence", confidence_counts["Medium"], help="Confidence score 60-79.9.")
row2[2].metric("Low Confidence", confidence_counts["Low"], help="Confidence score below 60.")
row2[3].metric(
    "Critical and High alerts",
    severity_counts["Critical"] + severity_counts["High"],
    help="Count of the most severe portfolio alerts requiring attention.",
)

# ------------------------------------------------------- Health versus Confidence overview
st.subheader("Health versus Confidence")
st.caption("Each project's delivery health against the trustworthiness of its data.")

overview_rows = []
for project_id in sorted(results):
    project = portfolio.get_project(project_id)
    health = results[project_id]["health"]
    confidence = results[project_id]["confidence"]
    counts = ui.count_alert_severities(results[project_id]["alerts"])
    overview_rows.append(
        {
            "Project": project_id,
            "Name": project.project_name if project else "",
            "Health": health.overall_score,
            "Health band": health.health_band,
            "Confidence": confidence.overall_score,
            "Confidence band": confidence.confidence_band,
            "Critical": counts["Critical"],
            "High": counts["High"],
            "Medium": counts["Medium"],
            "Low": counts["Low"],
        }
    )
overview = pd.DataFrame(overview_rows)
st.dataframe(overview, hide_index=True, width="stretch")

if not overview.empty:
    scatter = px.scatter(
        overview,
        x="Health",
        y="Confidence",
        text="Project",
        color="Health band",
        color_discrete_map=ui.HEALTH_BAND_COLORS,
        range_x=[0, 100],
        range_y=[0, 100],
        title="Health score versus Confidence score by project",
    )
    scatter.update_traces(textposition="top center", marker={"size": 14})
    st.plotly_chart(scatter, width="stretch")

# ------------------------------------------------------------------ exceptions panel
st.subheader("Portfolio exceptions")
st.caption(
    "The most severe alerts across the portfolio, ordered by severity, then project, then type."
)
if portfolio_alerts:
    alert_rows = [
        {
            "Severity": alert.severity,
            "Project": alert.project_id,
            "Title": alert.title,
            "Explanation": alert.explanation,
            "Recommended next step": alert.recommended_next_step,
        }
        for alert in portfolio_alerts
    ]
    total_alerts = len(alert_rows)
    default_visible = min(10, total_alerts)
    visible = st.slider(
        "Alerts to display",
        min_value=1,
        max_value=total_alerts,
        value=default_visible,
        help="Increase to show more; no alerts are hidden without indication.",
    )
    st.caption(f"Showing {visible} of {total_alerts} alerts.")
    st.dataframe(pd.DataFrame(alert_rows).head(visible), hide_index=True, width="stretch")
else:
    st.info("No early-warning alerts were generated for the portfolio.")

# ------------------------------------------------------------------ per-project detail
st.subheader("Per-project detail")
st.caption("The exact evidence produced by the engines, shown without reinterpretation.")
for project_id in sorted(results):
    project = portfolio.get_project(project_id)
    health = results[project_id]["health"]
    confidence = results[project_id]["confidence"]
    name = project.project_name if project else ""
    with st.expander(f"{project_id} - {name}"):
        st.markdown(
            f"**Health:** {ui.format_score(health.overall_score)} ({health.health_band}) "
            f"| **Confidence:** {ui.format_score(confidence.overall_score)} "
            f"({confidence.confidence_band})"
        )

        st.markdown("**Health factor scores**")
        st.dataframe(
            pd.DataFrame(
                {
                    "Factor": list(health.factor_scores),
                    "Score": list(health.factor_scores.values()),
                }
            ),
            hide_index=True,
            width="stretch",
        )
        st.markdown("**Why this Health status?**")
        for factor, lines in health.factor_explanations.items():
            for line in lines:
                st.markdown(f"- {factor}: {line}")

        st.markdown("**Confidence factor scores**")
        st.dataframe(
            pd.DataFrame(
                {
                    "Factor": list(confidence.factor_scores),
                    "Score": list(confidence.factor_scores.values()),
                }
            ),
            hide_index=True,
            width="stretch",
        )
        st.markdown("**Why this Confidence status?**")
        for factor, lines in confidence.factor_explanations.items():
            for line in lines:
                st.markdown(f"- {factor}: {line}")

        if confidence.data_quality_issues:
            st.markdown("**Data quality issues**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Severity": issue.severity,
                            "Type": issue.issue_type,
                            "Message": issue.message,
                            "Source IDs": ui.format_source_ids(issue.source_ids),
                            "Remediation": issue.remediation_hint,
                        }
                        for issue in confidence.data_quality_issues
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

        limitations = list(health.assumptions_or_limitations) + list(
            confidence.assumptions_or_limitations
        )
        if limitations:
            st.markdown("**Assumptions and limitations**")
            for item in limitations:
                st.markdown(f"- {item}")

# ------------------------------------------------------------------ methodology disclosure
with st.expander("Data and methodology"):
    st.markdown(
        "- All data shown is synthetic.\n"
        f"- Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1).\n"
        "- Full scoring methodology is documented in docs/scoring-methodology.md.\n"
        "- No GPT-4o or AI-generated content appears anywhere on this page; every value is "
        "produced by the deterministic engines."
    )
