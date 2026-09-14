"""Change Impact page (presentation only).

Renders the deterministic ``ChangeImpactResult`` for a selected change request, plus the
underlying records each affected ID refers to. The page performs no traversal, estimation or
risk assignment of its own; all of that lives in ``src/change_impact_engine.py``.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src import ui_formatting as ui
from src.change_impact_engine import calculate_change_impact, list_change_requests_for_project
from src.validators import DataValidationError

logger = logging.getLogger(__name__)
AS_OF = ui.ANALYSIS_DATE


@st.cache_data(show_spinner=False)
def _impact(_portfolio, as_of, change_request_id):
    """Call the change-impact engine, returning either the result or a safe message."""
    try:
        return calculate_change_impact(change_request_id, _portfolio, as_of), None
    except DataValidationError as exc:
        logger.exception("Change impact analysis failed for %s", change_request_id)
        return None, "; ".join(exc.issues)


st.header("Change Impact Analysis")
st.caption(
    f"Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1). "
    "All data is synthetic. No AI-generated content appears on this page."
)
st.write(
    "This page shows deterministic, evidence-based impact analysis for a selected change request. "
    "Schedule-impact figures are a coarse Version 1 heuristic, not a validated forecasting "
    "method, as documented in docs/change-impact-methodology.md."
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

change_requests = list_change_requests_for_project(selected_project, portfolio)
if not change_requests:
    st.info(f"No change requests are recorded for {selected_project}.")
    st.stop()

by_id = {c.change_request_id: c for c in change_requests}
options = list(by_id)
# Reset a stale selection carried over from another project.
if st.session_state.get("selected_change_request") not in options:
    st.session_state["selected_change_request"] = options[0]

selected_cr_id = st.selectbox(
    "Select a change request",
    options,
    key="selected_change_request",
    format_func=lambda cid: f"{cid} - {ui.truncate(by_id[cid].change_description, 60)}",
)
change_request = by_id[selected_cr_id]

# ------------------------------------------------------------------ change request summary
st.subheader("Change request")
st.dataframe(
    pd.DataFrame(
        [
            {
                "Change request": change_request.change_request_id,
                "Requirement": change_request.requirement_id,
                "Description": change_request.change_description,
                "Reason": change_request.reason,
                "Priority": change_request.priority,
                "Status": change_request.status,
                "Requested by": change_request.requested_by or "Unassigned",
                "Requested date": ui.format_date(change_request.requested_date),
            }
        ]
    ),
    hide_index=True,
    width="stretch",
)

result, impact_error = _impact(portfolio, AS_OF, selected_cr_id)
if result is None:
    st.error(
        "Impact analysis could not be completed for this change request. Please select another "
        f"change request. Detail: {impact_error}"
    )
    st.stop()

# ------------------------------------------------------------------ impact result
st.subheader("Impact result")
metrics = st.columns(2)
metrics[0].metric(
    "Estimated schedule impact",
    ui.format_days(result.estimated_schedule_impact_days),
    help="Version 1 heuristic estimate from the documented lookup table; not a forecast.",
)
metrics[1].metric(
    "Change risk level",
    "Not assessed" if result.evidence_status == "Insufficient evidence" else result.risk_level,
    help="Derived from affected milestone criticality, change priority and impact breadth.",
)
st.caption("Schedule impact is a coarse Version 1 heuristic estimate, not a validated forecast.")
if result.evidence_status == "Insufficient evidence":
    st.warning("Insufficient evidence to assess: nothing downstream is traced to this requirement.")

st.markdown(result.deterministic_explanation)

affected = {
    "Tasks": result.affected_task_ids,
    "Test cases": result.affected_test_case_ids,
    "Dependencies": result.affected_dependency_ids,
    "Milestones": result.affected_milestone_ids,
}
st.dataframe(
    pd.DataFrame(
        [
            {"Artefact type": label, "Count": len(ids), "IDs": ui.format_source_ids(ids)}
            for label, ids in affected.items()
        ]
    ),
    hide_index=True,
    width="stretch",
)

if not any(affected.values()):
    st.info(
        "No downstream artefacts were found for this change request. See the limitations below."
    )

st.markdown("**Assumptions and limitations** (context, not findings)")
for item in result.assumptions_or_limitations:
    st.markdown(f"- {item}")

# ------------------------------------------------------------------ affected artefact details
st.subheader("Affected artefact details")
st.caption("Each affected ID resolved back to its underlying record for verification.")

tasks = {t.task_id: t for t in portfolio.tasks if t.project_id == selected_project}
test_cases = {t.test_case_id: t for t in portfolio.test_cases if t.project_id == selected_project}
dependencies = {
    d.dependency_id: d for d in portfolio.dependencies if d.project_id == selected_project
}
milestones = {m.milestone_id: m for m in portfolio.milestones if m.project_id == selected_project}

task_rows = [
    {
        "Task": tasks[tid].task_id,
        "Name": tasks[tid].task_name,
        "Owner": tasks[tid].owner or "Unassigned",
        "Status": tasks[tid].status,
        "Milestone": tasks[tid].milestone_id,
        "Forecast end": ui.format_date(tasks[tid].forecast_end_date),
    }
    for tid in result.affected_task_ids
    if tid in tasks
]
test_rows = [
    {
        "Test case": test_cases[tid].test_case_id,
        "Name": test_cases[tid].test_case_name,
        "Status": test_cases[tid].status,
        "Owner": test_cases[tid].owner or "Unassigned",
        "Has verification evidence": test_cases[tid].has_verification_evidence,
    }
    for tid in result.affected_test_case_ids
    if tid in test_cases
]
dependency_rows = [
    {
        "Dependency": dependencies[did].dependency_id,
        "Name": dependencies[did].dependency_name,
        "Predecessor": f"{dependencies[did].predecessor_type} {dependencies[did].predecessor_id}",
        "Successor": f"{dependencies[did].successor_type} {dependencies[did].successor_id}",
        "Status": dependencies[did].status,
        "Delay days": dependencies[did].delay_days,
        "Criticality": dependencies[did].criticality,
    }
    for did in result.affected_dependency_ids
    if did in dependencies
]
milestone_rows = [
    {
        "Milestone": milestones[mid].milestone_id,
        "Name": milestones[mid].milestone_name,
        "Criticality": milestones[mid].criticality,
        "Status": milestones[mid].status,
        "Baseline": ui.format_date(milestones[mid].baseline_date),
        "Forecast": ui.format_date(milestones[mid].forecast_date),
    }
    for mid in result.affected_milestone_ids
    if mid in milestones
]

for label, rows in (
    ("Tasks", task_rows),
    ("Test cases", test_rows),
    ("Dependencies", dependency_rows),
    ("Milestones", milestone_rows),
):
    with st.expander(f"{label} ({len(rows)})"):
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.markdown(f"No affected {label.lower()} were identified for this change request.")

st.caption(
    "See Requirements Traceability for the underlying requirement-to-test relationship, and "
    "Project Intelligence for this project's overall Health and Confidence context."
)
st.page_link("pages/3_Requirements_Traceability.py", label="Requirements Traceability")
st.page_link("pages/2_Project_Intelligence.py", label="Project Intelligence")
