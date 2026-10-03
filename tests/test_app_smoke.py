"""Application shell and navigation smoke checks.

Deep, value-level coverage for each page lives in the per-page ``test_ui_*.py`` modules. This file
only proves the shell boots, every page is registered and reachable, and no page raises.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import (
    APP_PATH,
    PAGE_ASK_EPOS,
    PAGE_CHANGE_IMPACT,
    PAGE_DASHBOARD,
    PAGE_PROJECT_INTELLIGENCE,
    PAGE_SCENARIO,
    PAGE_TRACEABILITY,
)

ALL_PAGES = [
    (PAGE_DASHBOARD, "Portfolio Dashboard"),
    (PAGE_PROJECT_INTELLIGENCE, "Project Intelligence"),
    (PAGE_TRACEABILITY, "Requirements Traceability"),
    (PAGE_CHANGE_IMPACT, "Change Impact Analysis"),
    (PAGE_SCENARIO, "Scenario Planner"),
    (PAGE_ASK_EPOS, "Ask EPOS"),
]


def test_app_shell_runs_without_exception():
    app = AppTest.from_file(APP_PATH, default_timeout=120).run()
    assert len(app.exception) == 0
    assert len(app.error) == 0
    assert any(header.value == "Portfolio Dashboard" for header in app.header)


def test_shell_loads_the_portfolio_into_session_state():
    app = AppTest.from_file(APP_PATH, default_timeout=120).run()
    assert app.session_state["load_error"] is None
    assert app.session_state["portfolio"] is not None
    assert {"P-002", "P-007"} <= app.session_state["portfolio"].project_ids


@pytest.mark.parametrize(("page_path", "expected_header"), ALL_PAGES)
def test_every_page_is_reachable_and_renders(open_page, page_path, expected_header):
    app = open_page(page_path)
    assert len(app.exception) == 0
    assert len(app.error) == 0
    assert any(header.value == expected_header for header in app.header)


def test_all_six_pages_are_registered_and_navigable_in_one_session():
    app = AppTest.from_file(APP_PATH, default_timeout=120).run()
    for page_path, expected_header in ALL_PAGES:
        app.switch_page(page_path)
        app.run()
        assert any(header.value == expected_header for header in app.header)
        assert len(app.exception) == 0
