"""EPOS Lite - Streamlit application shell.

Presentation only: this entry point loads the portfolio once per session and defines the
navigation. All business logic stays in ``src/``. Only the Portfolio Dashboard page exists in
this step; five further pages slot into the navigation list in later phases.
"""

from __future__ import annotations

import logging

import streamlit as st

from src.data_loader import load_portfolio
from src.validators import DataValidationError

logger = logging.getLogger(__name__)

st.set_page_config(page_title="EPOS Lite", page_icon=":material/insights:", layout="wide")


@st.cache_data(show_spinner=False)
def _load_portfolio_cached():
    """Load the validated portfolio once and cache it for the session."""
    return load_portfolio()


def _ensure_portfolio_loaded() -> None:
    """Populate session state with the portfolio or a load error, exactly once."""
    if st.session_state.get("portfolio") is not None or st.session_state.get("load_error"):
        return
    try:
        st.session_state["portfolio"] = _load_portfolio_cached()
        st.session_state["load_error"] = None
    except DataValidationError as exc:
        logger.exception("Failed to load portfolio data")
        st.session_state["portfolio"] = None
        st.session_state["load_error"] = "; ".join(exc.issues)


_ensure_portfolio_loaded()

# All six Version 1 pages are registered.
pages = [
    st.Page(
        "pages/1_Portfolio_Dashboard.py",
        title="Portfolio Dashboard",
        icon=":material/dashboard:",
        default=True,
    ),
    st.Page(
        "pages/2_Project_Intelligence.py",
        title="Project Intelligence",
        icon=":material/insights:",
    ),
    st.Page(
        "pages/3_Requirements_Traceability.py",
        title="Requirements Traceability",
        icon=":material/account_tree:",
    ),
    st.Page(
        "pages/4_Change_Impact.py",
        title="Change Impact",
        icon=":material/change_circle:",
    ),
    st.Page(
        "pages/5_Scenario_Planner.py",
        title="Scenario Planner",
        icon=":material/science:",
    ),
    st.Page(
        "pages/6_Ask_EPOS.py",
        title="Ask EPOS",
        icon=":material/forum:",
    ),
]

st.navigation(pages).run()
