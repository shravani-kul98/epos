"""Value-level UI tests for the Requirements Traceability page."""

from __future__ import annotations

import pytest

from src import ui_formatting as ui
from src.data_loader import load_portfolio
from src.risk_engine import ALERT_REQUIREMENT_VERIFICATION, generate_early_warnings
from tests.conftest import AS_OF, PAGE_TRACEABILITY, frame_named, rendered_text

PROJECT_IDS = ["P-002", "P-007"]


def _rule8_alerts(portfolio, project_id):
    return [
        alert
        for alert in generate_early_warnings(project_id, portfolio, AS_OF)
        if alert.alert_type == ALERT_REQUIREMENT_VERIFICATION
    ]


def _expected_trace_status(portfolio, project_id, requirement_id) -> str:
    test_cases = {t.test_case_id: t for t in portfolio.test_cases if t.project_id == project_id}
    linked = [
        test_cases[link.target_id]
        for link in portfolio.trace_links
        if link.project_id == project_id
        and link.link_type == "verified_by"
        and link.source_type == "Requirement"
        and link.source_id == requirement_id
        and link.target_type == "TestCase"
        and link.target_id in test_cases
    ]
    return ui.trace_status((tc.status, tc.has_verification_evidence) for tc in linked)


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_requirements_table_matches_loaded_data(open_page, project_id):
    portfolio = load_portfolio()
    expected = {r.requirement_id for r in portfolio.requirements if r.project_id == project_id}

    app = open_page(PAGE_TRACEABILITY, selected_project=project_id)
    frame = frame_named(app, "Requirement", "Trace status")

    assert set(frame["Requirement"]) == expected
    assert len(app.exception) == 0
    assert len(app.error) == 0


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_trace_status_column_matches_raw_data(open_page, project_id):
    portfolio = load_portfolio()
    app = open_page(PAGE_TRACEABILITY, selected_project=project_id)
    frame = frame_named(app, "Requirement", "Trace status")

    for _, row in frame.iterrows():
        assert row["Trace status"] == _expected_trace_status(
            portfolio, project_id, row["Requirement"]
        )


def test_known_verified_requirement_shows_verified(open_page):
    # REQ-2001 is verified by TC-2001, which is Passed with evidence EVID-2001.
    app = open_page(PAGE_TRACEABILITY, selected_project="P-002")
    frame = frame_named(app, "Requirement", "Trace status")
    row = frame[frame["Requirement"] == "REQ-2001"].iloc[0]
    assert row["Trace status"] == ui.TRACE_VERIFIED
    assert "TC-2001" in row["Linked test cases"]


def test_known_gap_requirement_shows_not_verified(open_page):
    # REQ-7002 is verified by TC-7002, which is Failed with no evidence.
    app = open_page(PAGE_TRACEABILITY, selected_project="P-007")
    frame = frame_named(app, "Requirement", "Trace status")
    row = frame[frame["Requirement"] == "REQ-7002"].iloc[0]
    assert row["Trace status"] == ui.TRACE_NOT_VERIFIED
    assert "TC-7002" in row["Linked test cases"]


def test_requirement_with_no_link_is_labelled(open_page):
    portfolio = load_portfolio()
    app = open_page(PAGE_TRACEABILITY, selected_project="P-002")
    frame = frame_named(app, "Requirement", "Trace status")

    unlinked = [
        row["Requirement"] for _, row in frame.iterrows() if row["Trace status"] == ui.TRACE_NO_LINK
    ]
    for requirement_id in unlinked:
        assert _expected_trace_status(portfolio, "P-002", requirement_id) == ui.TRACE_NO_LINK
        row = frame[frame["Requirement"] == requirement_id].iloc[0]
        assert row["Test status"] == "No linked test case"


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_verification_alerts_match_rule8_exactly(open_page, project_id):
    portfolio = load_portfolio()
    alerts = _rule8_alerts(portfolio, project_id)

    app = open_page(PAGE_TRACEABILITY, selected_project=project_id)
    text = rendered_text(app)

    if not alerts:
        assert "No verification-gap alerts were detected" in text
    for alert in alerts:
        assert alert.explanation in text
        assert alert.recommended_next_step in text
        assert alert.severity in text


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_ui_level_consistency_between_trace_status_and_alerts(open_page, project_id):
    """A requirement shown as Verified must never also carry a Rule 8 alert on the page."""
    portfolio = load_portfolio()
    alerted = {
        source_id
        for alert in _rule8_alerts(portfolio, project_id)
        for source_id in alert.source_ids
    }

    app = open_page(PAGE_TRACEABILITY, selected_project=project_id)
    frame = frame_named(app, "Requirement", "Trace status")

    for _, row in frame.iterrows():
        if row["Trace status"] == ui.TRACE_VERIFIED:
            assert row["Requirement"] not in alerted
        if row["Requirement"] in alerted:
            assert row["Trace status"] != ui.TRACE_VERIFIED


@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_reference_tables_match_loaded_data(open_page, project_id):
    portfolio = load_portfolio()
    app = open_page(PAGE_TRACEABILITY, selected_project=project_id)

    expected_tests = {t.test_case_id for t in portfolio.test_cases if t.project_id == project_id}
    expected_links = {t.trace_link_id for t in portfolio.trace_links if t.project_id == project_id}

    assert set(frame_named(app, "Test case", "Status")["Test case"]) == expected_tests
    assert set(frame_named(app, "Trace link", "Link type")["Trace link"]) == expected_links


def test_limitations_disclosure_present(open_page):
    app = open_page(PAGE_TRACEABILITY, selected_project="P-007")
    text = rendered_text(app)
    assert "not a full traceability graph" in text
    assert "verified_by" in text
