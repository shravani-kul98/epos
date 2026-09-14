"""Project Intelligence detail page (presentation only).

Shows one project's deterministic evidence: why it sits in its Health band, whether that status can
be trusted (Confidence), its early-warning alerts, and the underlying records. Every value is
rendered exactly as the engines produced it; this page adds no scoring, banding or alert logic.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src import ui_formatting as ui
from src.confidence_engine import calculate_project_confidence
from src.health_engine import calculate_project_health
from src.risk_engine import generate_early_warnings

logger = logging.getLogger(__name__)
AS_OF = ui.ANALYSIS_DATE


@st.cache_data(show_spinner=False)
def _analyze(_portfolio, as_of, project_id):
    """Run the three engines for one project, isolating each so one failure is not fatal."""

    def safe(label, call):
        try:
            return call(), None
        except Exception:  # noqa: BLE001 - converted into a scoped, visible error message
            logger.exception("%s analysis failed for %s", label, project_id)
            return None, f"{label} analysis could not be completed for {project_id}."

    health, health_error = safe(
        "Health", lambda: calculate_project_health(project_id, _portfolio, as_of)
    )
    confidence, confidence_error = safe(
        "Confidence", lambda: calculate_project_confidence(project_id, _portfolio, as_of)
    )
    alerts, alerts_error = safe(
        "Alert", lambda: generate_early_warnings(project_id, _portfolio, as_of)
    )
    return {
        "health": health,
        "health_error": health_error,
        "confidence": confidence,
        "confidence_error": confidence_error,
        "alerts": alerts,
        "alerts_error": alerts_error,
    }


def _factor_table(factor_scores, factor_weights):
    order = ui.factors_by_ascending_score(factor_scores)
    return pd.DataFrame(
        {
            "Factor": order,
            "Weight": [factor_weights.get(name) for name in order],
            "Score": [factor_scores[name] for name in order],
        }
    )


def _render_explanations(factor_explanations):
    for factor in factor_explanations:
        for line in factor_explanations[factor]:
            st.markdown(f"- {factor}: {line}")


def _render_severity_groups(items, render_item):
    grouped = ui.group_by_severity(items)
    for severity in ui.SEVERITIES:
        group = grouped[severity]
        if not group:
            continue
        st.markdown(f"**{severity}**")
        for item in group:
            render_item(item)


def _render_limitations(limitations):
    if limitations:
        st.markdown("**Assumptions and limitations** (context, not findings)")
        for item in limitations:
            st.markdown(f"- {item}")


st.header("Project Intelligence")
st.caption(
    f"Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1). "
    "All data is synthetic. No AI-generated content appears on this page."
)
st.page_link("pages/1_Portfolio_Dashboard.py", label="Back to Portfolio Dashboard")

portfolio = st.session_state.get("portfolio")
if st.session_state.get("load_error") or portfolio is None:
    st.error(
        "Portfolio data could not be loaded. Check the local CSV data in the data folder. "
        "Diagnostic detail has been written to the local logs."
    )
    st.stop()

project_ids = sorted(portfolio.project_ids)
names = {p.project_id: p.project_name for p in portfolio.projects}
selected = st.selectbox(
    "Select a project",
    project_ids,
    key="selected_project",
    format_func=lambda pid: f"{pid} - {names.get(pid, '')}",
)

project = portfolio.get_project(selected)
if project is None:
    st.warning("The selected project is no longer available. Please choose another project.")
    st.stop()

analysis = _analyze(portfolio, AS_OF, selected)
health = analysis["health"]
confidence = analysis["confidence"]
alerts = analysis["alerts"]

# ------------------------------------------------------------------ project header
st.subheader(f"{project.project_id} - {project.project_name}")
header = st.columns(2)
if health is not None:
    header[0].metric(
        "Health",
        f"{ui.format_score(health.overall_score)} ({health.health_band})",
        help="Delivery performance across schedule, milestones, tasks, risk, dependencies, "
        "resources and actions.",
    )
else:
    header[0].error(analysis["health_error"])
if confidence is not None:
    header[1].metric(
        "Confidence",
        f"{ui.format_score(confidence.overall_score)} ({confidence.confidence_band})",
        help="How trustworthy the underlying data is: freshness, completeness, ownership and "
        "source availability.",
    )
else:
    header[1].error(analysis["confidence_error"])

if health is not None and confidence is not None:
    st.markdown(
        f"Delivery Health is **{health.health_band}** and Data Confidence is "
        f"**{confidence.confidence_band}**."
    )

# ------------------------------------------------------- Health evidence panel
st.subheader("Why is this project in this Health band")
if health is None:
    st.error(analysis["health_error"])
else:
    st.caption("Factors ordered with the most penalised first. Weights sum to 1.0.")
    st.dataframe(
        _factor_table(health.factor_scores, health.factor_weights),
        hide_index=True,
        width="stretch",
    )
    st.markdown("**Why this Health status?**")
    _render_explanations(health.factor_explanations)

    st.markdown("**Critical drivers**")
    if health.critical_drivers:
        _render_severity_groups(
            health.critical_drivers,
            lambda d: st.markdown(
                f"- {d.factor_name}: {d.message} "
                f"(evidence: {ui.format_source_ids(d.source_ids)}; {d.score_impact_description})"
            ),
        )
    else:
        st.markdown("- No critical drivers were identified.")
    _render_limitations(health.assumptions_or_limitations)

# ------------------------------------------------------- Confidence evidence panel
st.subheader("Can this status be trusted")
if confidence is None:
    st.error(analysis["confidence_error"])
else:
    with st.container(border=True):
        st.caption("Data-reliability evidence, distinct from delivery health above.")
        st.dataframe(
            _factor_table(confidence.factor_scores, confidence.factor_weights),
            hide_index=True,
            width="stretch",
        )
        st.markdown("**Why this Confidence status?**")
        _render_explanations(confidence.factor_explanations)

        st.markdown("**Data quality issues**")
        if confidence.data_quality_issues:
            _render_severity_groups(
                confidence.data_quality_issues,
                lambda i: st.markdown(
                    f"- {i.issue_type}: {i.message} "
                    f"(evidence: {ui.format_source_ids(i.source_ids)}; remediation: "
                    f"{i.remediation_hint})"
                ),
            )
        else:
            st.markdown("- No data quality issues were identified.")
        _render_limitations(confidence.assumptions_or_limitations)

# ------------------------------------------------------------------ alerts panel
st.subheader("Early-warning alerts for this project")
if alerts is None:
    st.error(analysis["alerts_error"])
elif not alerts:
    st.info(
        f"No early-warning conditions were detected for {selected} as of {ui.format_date(AS_OF)}."
    )
else:
    for alert in alerts:
        st.markdown(
            f"**{alert.severity} - {alert.title}** ({alert.alert_type})\n\n"
            f"{alert.explanation}\n\n"
            f"Evidence: {ui.format_source_ids(alert.source_ids)}\n\n"
            f"Recommended next step: {alert.recommended_next_step}"
        )
        st.divider()

# ------------------------------------------------------------------ underlying records
st.subheader("Underlying records")
st.caption(
    "A direct read of this project's loaded data, to cross-check any evidence ID shown above."
)


def _records_frame(records):
    return pd.DataFrame([r.model_dump() for r in records])


record_groups = [
    ("Milestones", [m for m in portfolio.milestones if m.project_id == selected]),
    ("Tasks", [t for t in portfolio.tasks if t.project_id == selected]),
    ("Risks", [r for r in portfolio.risks if r.project_id == selected]),
    ("Dependencies", [d for d in portfolio.dependencies if d.project_id == selected]),
    ("Actions", [a for a in portfolio.actions if a.project_id == selected]),
    ("Resources", [r for r in portfolio.resources if r.project_id == selected]),
]
for label, records in record_groups:
    with st.expander(f"{label} ({len(records)})"):
        if records:
            st.dataframe(_records_frame(records), hide_index=True, width="stretch")
        else:
            st.markdown(f"No {label.lower()} are recorded for this project.")
