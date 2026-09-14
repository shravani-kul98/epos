"""Requirements Traceability page (presentation only).

Shows the single requirement-to-test-case relationship that exists in the Version 1 data model
(``trace_links`` with ``link_type = verified_by``) plus the verification-gap alerts the Risk engine
already produces. This page contains no verification rule of its own; it reads loaded records and
cross-references the engine's existing alerts.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src import ui_formatting as ui
from src.risk_engine import ALERT_REQUIREMENT_VERIFICATION, generate_early_warnings

logger = logging.getLogger(__name__)
AS_OF = ui.ANALYSIS_DATE

# The exact relationship Rule 8 uses; kept as constants so the page and engine stay aligned.
VERIFIED_BY = "verified_by"
SOURCE_TYPE_REQUIREMENT = "Requirement"
TARGET_TYPE_TEST_CASE = "TestCase"

st.header("Requirements Traceability")
st.caption(
    f"Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1). "
    "All data is synthetic. No AI-generated content appears on this page."
)
st.write(
    "This page shows the existing requirement-to-test-case relationship and the known "
    "verification gaps. This is Version 1 traceability covering that single relationship only; "
    "fuller requirement-to-task-to-test-to-milestone-to-release traceability is a future "
    "enhancement recorded in docs/roadmap.md."
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

requirements = [r for r in portfolio.requirements if r.project_id == selected]
test_cases = [t for t in portfolio.test_cases if t.project_id == selected]
trace_links = [t for t in portfolio.trace_links if t.project_id == selected]
test_case_by_id = {t.test_case_id: t for t in test_cases}

# ------------------------------------------------------------------ requirements table
st.subheader("Requirements and trace status")
if not requirements:
    st.info(f"No requirements are recorded for {selected}.")
else:
    rows = []
    for requirement in requirements:
        linked = [
            test_case_by_id[link.target_id]
            for link in trace_links
            if link.link_type == VERIFIED_BY
            and link.source_type == SOURCE_TYPE_REQUIREMENT
            and link.source_id == requirement.requirement_id
            and link.target_type == TARGET_TYPE_TEST_CASE
            and link.target_id in test_case_by_id
        ]
        status = ui.trace_status((tc.status, tc.has_verification_evidence) for tc in linked)
        rows.append(
            {
                "Requirement": requirement.requirement_id,
                "Text": ui.truncate(requirement.requirement_text),
                "Type": requirement.requirement_type,
                "Priority": requirement.priority,
                "Status": requirement.status,
                "Owner": requirement.owner or "Unassigned",
                "Linked test cases": ui.format_source_ids(t.test_case_id for t in linked),
                "Test status": (
                    ", ".join(t.status for t in linked) if linked else "No linked test case"
                ),
                "Verification evidence": (
                    ", ".join(t.verification_evidence or "none" for t in linked)
                    if linked
                    else "none"
                ),
                "Trace status": status,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(
        "Trace status describes the linked records: Verified (linked test passed with evidence), "
        "Test not run, Not verified, or No linked test case. The verification verdict itself is "
        "the Risk engine alert shown below."
    )

    with st.expander("Full requirement text"):
        for requirement in requirements:
            st.markdown(f"- **{requirement.requirement_id}**: {requirement.requirement_text}")

# ------------------------------------------------------------------ verification-gap alerts
st.subheader("Verification-gap alerts for this project")
try:
    alerts = [
        alert
        for alert in generate_early_warnings(selected, portfolio, AS_OF)
        if alert.alert_type == ALERT_REQUIREMENT_VERIFICATION
    ]
except Exception:  # noqa: BLE001 - converted into a scoped, visible error message
    logger.exception("Alert analysis failed for %s", selected)
    alerts = None
    st.error(f"Alert analysis could not be completed for {selected}.")

if alerts is not None:
    if not alerts:
        st.info(
            f"No verification-gap alerts were detected for {selected} as of "
            f"{ui.format_date(AS_OF)}."
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

# ------------------------------------------------------------------ reference tables
st.subheader("Test cases")
if test_cases:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Test case": t.test_case_id,
                    "Name": t.test_case_name,
                    "Status": t.status,
                    "Owner": t.owner or "Unassigned",
                    "Has verification evidence": t.has_verification_evidence,
                    "Last updated": ui.format_date(t.last_updated_date),
                }
                for t in test_cases
            ]
        ),
        hide_index=True,
        width="stretch",
    )
else:
    st.info(f"No test cases are recorded for {selected}.")

st.subheader("Trace links")
if trace_links:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Trace link": link.trace_link_id,
                    "Source type": link.source_type,
                    "Source": link.source_id,
                    "Target type": link.target_type,
                    "Target": link.target_id,
                    "Link type": link.link_type,
                }
                for link in trace_links
            ]
        ),
        hide_index=True,
        width="stretch",
    )
else:
    st.info(f"No trace links are recorded for {selected}.")

# ------------------------------------------------------------------ limitations
with st.expander("Traceability limitations"):
    st.markdown(
        "- This page implements only the single requirement-to-test-case relationship that exists "
        "in the Version 1 data model (`trace_links` with `link_type = verified_by`).\n"
        "- It is not a full traceability graph across requirement, task, test, milestone and "
        "release.\n"
        "- Fuller traceability is a documented future enhancement, consistent with the same "
        "limitation already recorded for Risk Rule 8 in docs/scoring-methodology.md."
    )
