"""Ask EPOS page (presentation only).

Renders a source-grounded AI draft for one of the supported questions. All facts come from the
deterministic engines via the evidence package; the AI layer only explains them. Every AI section
is visually separated from deterministic content and carries the human-review disclaimer.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src import ai_assistant as ai
from src import ui_formatting as ui
from src.change_impact_engine import list_change_requests_for_project
from src.config import get_azure_settings
from src.validators import DataValidationError

logger = logging.getLogger(__name__)
AS_OF = ui.ANALYSIS_DATE

st.header("Ask EPOS")
st.caption(
    f"Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1). "
    "All data is synthetic."
)
st.write(
    "Ask EPOS is a source-grounded assistant. It answers only the supported questions below, "
    "using structured evidence produced by the deterministic Health, Confidence, Risk and Change "
    "Impact engines. Every answer cites the source record IDs behind it and requires human review."
)

portfolio = st.session_state.get("portfolio")
if st.session_state.get("load_error") or portfolio is None:
    st.error(
        "Portfolio data could not be loaded. Check the local CSV data in the data folder. "
        "Diagnostic detail has been written to the local logs."
    )
    st.stop()

ai_available = get_azure_settings().is_configured
if not ai_available:
    st.warning(
        "AI capability is unavailable because Azure OpenAI configuration is missing. "
        "The deterministic evidence below is still shown, and every dashboard page "
        "(Portfolio Dashboard, Project Intelligence, Requirements Traceability, Change Impact, "
        "Scenario Planner) remains fully available."
    )

question_type = st.selectbox(
    "Select a question",
    list(ai.QUESTION_TYPES),
    key="ask_question_type",
    format_func=lambda key: ai.QUESTION_TYPES[key],
)

context: dict[str, str] = {}
required_key = ai.QUESTION_CONTEXT_KEYS.get(question_type)

if required_key == "project_id":
    project_ids = sorted(portfolio.project_ids)
    names = {p.project_id: p.project_name for p in portfolio.projects}
    context["project_id"] = st.selectbox(
        "Select a project",
        project_ids,
        key="selected_project",
        format_func=lambda pid: f"{pid} - {names.get(pid, '')}",
    )
elif required_key == "change_request_id":
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
    if st.session_state.get("selected_change_request") not in options:
        st.session_state["selected_change_request"] = options[0]
    context["change_request_id"] = st.selectbox(
        "Select a change request",
        options,
        key="selected_change_request",
        format_func=lambda cid: f"{cid} - {ui.truncate(by_id[cid].change_description, 60)}",
    )

try:
    evidence = ai.build_evidence_package(question_type, portfolio, AS_OF, context)
except DataValidationError as exc:
    logger.exception("Evidence package could not be built for %s", question_type)
    st.error(
        f"The evidence for this question could not be assembled. Detail: {'; '.join(exc.issues)}"
    )
    st.stop()

# ------------------------------------------------------------------ deterministic evidence
st.subheader("Deterministic evidence")
st.caption(
    "Calculated by the engines. This is exactly what would be sent to the AI layer, and it is "
    "shown whether or not AI is available."
)
if evidence.records:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Type": record.record_type,
                    "ID": record.record_id,
                    "Details": ui.truncate(
                        "; ".join(f"{k}={v}" for k, v in record.fields.items()), 160
                    ),
                }
                for record in evidence.records
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(f"Evidence source IDs: {ui.format_source_ids(evidence.source_ids)}")
else:
    st.info("No evidence records were found for this question at the analysis reference date.")

# ------------------------------------------------------------------ AI draft
if st.button("Ask", type="primary", disabled=not ai_available):
    st.session_state["ask_request"] = {"question_type": question_type, "context": context}

request = st.session_state.get("ask_request")
if request is None or request["question_type"] != question_type:
    st.info("Choose a question and select Ask to generate an AI draft from the evidence above.")
    st.stop()

response = ai.ask_epos(question_type, portfolio, AS_OF, request["context"])

st.subheader("AI-generated draft")
with st.container(border=True):
    st.caption("AI-generated section. Content below is drafted by GPT-4o from the evidence above.")

    if response.status == "unavailable":
        st.warning(response.executive_summary)
    elif response.status == "error":
        st.error(
            "The AI request could not be completed (the service was unreachable or timed out). "
            "The deterministic evidence above is unaffected."
        )
    elif response.status == "invalid_response":
        st.error(
            "The AI response did not match the required structure and was rejected. "
            "No unvalidated AI content is shown."
        )
    else:
        st.markdown("**Executive summary**")
        st.markdown(response.executive_summary)

        if response.key_findings:
            st.markdown("**Key findings**")
            for finding in response.key_findings:
                st.markdown(f"- {finding}")

        if response.recommended_actions:
            st.markdown("**Recommended actions**")
            for action in response.recommended_actions:
                st.markdown(f"- {action}")

        st.markdown(f"**Source IDs**: {ui.format_source_ids(response.source_ids)}")

    if response.warnings:
        st.warning("Grounding checks: " + " ".join(response.warnings))

    st.info(response.disclaimer)

st.caption(
    "AI output explains already-calculated facts. It never calculates scores, changes data, or "
    "takes any action."
)
