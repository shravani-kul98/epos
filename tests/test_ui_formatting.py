"""Pure-Python tests for the UI formatting and aggregation helpers (no Streamlit required)."""

from __future__ import annotations

from datetime import date

import pytest

from src import ui_formatting as ui


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, "0.0"), (50.7, "50.7"), (51.94, "51.9"), (100.0, "100.0")],
)
def test_format_score(value, expected):
    assert ui.format_score(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(59.25, "59.3"), (0.25, "0.3"), (51.95, "52.0"), (58.55, "58.5")],
)
def test_format_score_rounds_halves_away_from_zero(value, expected):
    """A score exactly on a half must not read differently here and in the browser.

    JavaScript `toFixed(1)` renders 59.25 as "59.3"; Python's own `format` would say "59.2".
    """
    assert ui.format_score(value) == expected


@pytest.mark.parametrize(("value", "expected"), [(1.25, "+1.3"), (-1.25, "-1.3"), (0.0, "0.0")])
def test_format_signed_score(value, expected):
    assert ui.format_signed_score(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, "0.0%"), (82.0, "82.0%"), (99.99, "100.0%")],
)
def test_format_percent(value, expected):
    assert ui.format_percent(value) == expected


def test_format_date():
    assert ui.format_date(date(2026, 8, 25)) == "2026-08-25"
    assert ui.format_date(None) == "Not set"


@pytest.mark.parametrize("band", list(ui.HEALTH_BANDS))
def test_health_band_color_valid(band):
    assert ui.health_band_color(band) == ui.HEALTH_BAND_COLORS[band]


@pytest.mark.parametrize("band", list(ui.CONFIDENCE_BANDS))
def test_confidence_band_color_valid(band):
    assert ui.confidence_band_color(band) == ui.CONFIDENCE_BAND_COLORS[band]


@pytest.mark.parametrize("severity", list(ui.SEVERITIES))
def test_severity_color_valid(severity):
    assert ui.severity_color(severity) == ui.SEVERITY_COLORS[severity]


def test_band_and_severity_color_fallback():
    assert ui.health_band_color("Unknown") == ui._NEUTRAL
    assert ui.confidence_band_color("Unknown") == ui._NEUTRAL
    assert ui.severity_color("Unknown") == ui._NEUTRAL


class _Health:
    def __init__(self, band):
        self.health_band = band


class _Confidence:
    def __init__(self, band):
        self.confidence_band = band


class _Alert:
    def __init__(self, severity):
        self.severity = severity


def test_count_health_bands():
    counts = ui.count_health_bands([_Health("Red"), _Health("Red"), _Health("Green")])
    assert counts == {"Green": 1, "Amber": 0, "Red": 2}


def test_count_confidence_bands():
    counts = ui.count_confidence_bands([_Confidence("High"), _Confidence("Medium")])
    assert counts == {"High": 1, "Medium": 1, "Low": 0}


def test_count_alert_severities():
    counts = ui.count_alert_severities([_Alert("Critical"), _Alert("Critical"), _Alert("High")])
    assert counts == {"Critical": 2, "High": 1, "Medium": 0, "Low": 0}


def test_gather_project_analysis_skips_failures():
    def analyze(project_id: str) -> str:
        if project_id == "BAD":
            raise ValueError("boom")
        return f"ok-{project_id}"

    results, failures = ui.gather_project_analysis(["P-1", "BAD", "P-2"], analyze)
    assert results == {"P-1": "ok-P-1", "P-2": "ok-P-2"}
    assert failures == ["BAD"]


def test_gather_project_analysis_all_success():
    results, failures = ui.gather_project_analysis(["P-1"], lambda pid: pid.lower())
    assert results == {"P-1": "p-1"}
    assert failures == []


def test_group_by_severity_orders_and_buckets():
    items = [_Alert("Low"), _Alert("Critical"), _Alert("High"), _Alert("Critical")]
    grouped = ui.group_by_severity(items)
    assert list(grouped) == ["Critical", "High", "Medium", "Low"]
    assert len(grouped["Critical"]) == 2
    assert len(grouped["High"]) == 1
    assert grouped["Medium"] == []
    assert len(grouped["Low"]) == 1


def test_factors_by_ascending_score():
    scores = {"a": 80.0, "b": 25.0, "c": 25.0, "d": 100.0}
    # Ascending score, ties broken by name.
    assert ui.factors_by_ascending_score(scores) == ["b", "c", "a", "d"]


def test_format_source_ids():
    assert ui.format_source_ids(["R-1", "M-2"]) == "R-1, M-2"
    assert ui.format_source_ids([]) == "none"


@pytest.mark.parametrize(
    ("linked", "expected"),
    [
        ([], ui.TRACE_NO_LINK),
        ([("Passed", True)], ui.TRACE_VERIFIED),
        ([("Passed", False)], ui.TRACE_NOT_VERIFIED),
        ([("Not Run", False)], ui.TRACE_NOT_RUN),
        ([("Failed", False)], ui.TRACE_NOT_VERIFIED),
        ([("Failed", True)], ui.TRACE_NOT_VERIFIED),
        ([("Not Run", False), ("Passed", True)], ui.TRACE_VERIFIED),
        ([("Failed", False), ("Not Run", False)], ui.TRACE_NOT_RUN),
    ],
)
def test_trace_status(linked, expected):
    assert ui.trace_status(linked) == expected


@pytest.mark.parametrize("status", list(ui.TRACE_STATUSES))
def test_trace_status_color_valid(status):
    assert ui.trace_status_color(status) == ui.TRACE_STATUS_COLORS[status]


def test_trace_status_color_fallback():
    assert ui.trace_status_color("Unknown") == ui._NEUTRAL


def test_truncate():
    assert ui.truncate("short text", 20) == "short text"
    assert ui.truncate("x" * 20, 10) == "xxxxxxx..."
    assert len(ui.truncate("x" * 200, 80)) == 80


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0 calendar days"),
        (1, "1 calendar day"),
        (2, "2 calendar days"),
        (20, "20 calendar days"),
    ],
)
def test_format_days(value, expected):
    assert ui.format_days(value) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [(0.0, "no change"), (-2.0, "-2.0"), (1.5, "+1.5"), (-0.5, "-0.5")],
)
def test_format_score_delta(delta, expected):
    assert ui.format_score_delta(delta) == expected
