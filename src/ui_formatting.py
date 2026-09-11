"""Presentation helpers shared by the Streamlit pages and the API's narrative text.

This module contains no business logic and no scoring/alert logic. It only formats and tallies
values that the deterministic engines have already produced, and defines the display palette.
Keeping it engine-free means it is pure Python and unit-testable without Streamlit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TypeVar

from src import scoring_rules as sr
from src.schemas import ConfidenceResult, EarlyWarningAlert, HealthResult

# Fixed Version 1 analysis reference date (shown in the UI, not the real current date).
ANALYSIS_DATE: date = date(2026, 8, 25)

_NEUTRAL = "#616161"

# Muted, control-tower palette. Health/Confidence share the same semantic green/amber/red.
HEALTH_BAND_COLORS: dict[str, str] = {"Green": "#2E7D32", "Amber": "#ED6C02", "Red": "#C62828"}
CONFIDENCE_BAND_COLORS: dict[str, str] = {"High": "#2E7D32", "Medium": "#ED6C02", "Low": "#C62828"}
SEVERITY_COLORS: dict[str, str] = {
    "Critical": "#B71C1C",
    "High": "#E65100",
    "Medium": "#F9A825",
    "Low": "#616161",
}

HEALTH_BANDS: tuple[str, ...] = ("Green", "Amber", "Red")
CONFIDENCE_BANDS: tuple[str, ...] = ("High", "Medium", "Low")
SEVERITIES: tuple[str, ...] = ("Critical", "High", "Medium", "Low")

# Descriptive labels for the observed state of a requirement's verified_by test link. These
# describe the loaded records only; the verification verdict itself comes from the Risk engine.
TRACE_VERIFIED = "Verified"
TRACE_NOT_RUN = "Test not run"
TRACE_NOT_VERIFIED = "Not verified"
TRACE_NO_LINK = "No linked test case"

TRACE_STATUSES: tuple[str, ...] = (TRACE_VERIFIED, TRACE_NOT_RUN, TRACE_NOT_VERIFIED, TRACE_NO_LINK)

# Reuses the existing palette; no new colour scheme is introduced.
TRACE_STATUS_COLORS: dict[str, str] = {
    TRACE_VERIFIED: HEALTH_BAND_COLORS["Green"],
    TRACE_NOT_RUN: SEVERITY_COLORS["Medium"],
    TRACE_NOT_VERIFIED: SEVERITY_COLORS["High"],
    TRACE_NO_LINK: SEVERITY_COLORS["Critical"],
}

T = TypeVar("T")


def format_score(value: float) -> str:
    """Format a 0-100 score to one decimal place.

    Halves round away from zero, matching JavaScript's `toFixed`, so one score never reads as
    59.2 in a report and 59.3 in the browser. Python's own `format` would round 59.25 to even.
    """
    return str(Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def format_signed_score(value: float) -> str:
    """Format a score movement with an explicit direction, using the same rounding rule."""
    rounded = format_score(value)
    return f"+{rounded}" if value > 0 else rounded


def format_percent(value: float) -> str:
    """Format a percentage value to one decimal place with a percent sign."""
    return f"{value:.1f}%"


def format_date(value: date | None) -> str:
    """Format a date as YYYY-MM-DD, or a clear placeholder when absent."""
    return value.isoformat() if value is not None else "Not set"


def health_band_color(band: str) -> str:
    """Return the display colour for a Health band."""
    return HEALTH_BAND_COLORS.get(band, _NEUTRAL)


def confidence_band_color(band: str) -> str:
    """Return the display colour for a Confidence band."""
    return CONFIDENCE_BAND_COLORS.get(band, _NEUTRAL)


def severity_color(severity: str) -> str:
    """Return the display colour for an alert severity."""
    return SEVERITY_COLORS.get(severity, _NEUTRAL)


def count_health_bands(results: Iterable[HealthResult]) -> dict[str, int]:
    """Tally Health results by their already-computed band."""
    counts = dict.fromkeys(HEALTH_BANDS, 0)
    for result in results:
        counts[result.health_band] = counts.get(result.health_band, 0) + 1
    return counts


def count_confidence_bands(results: Iterable[ConfidenceResult]) -> dict[str, int]:
    """Tally Confidence results by their already-computed band."""
    counts = dict.fromkeys(CONFIDENCE_BANDS, 0)
    for result in results:
        counts[result.confidence_band] = counts.get(result.confidence_band, 0) + 1
    return counts


def count_alert_severities(alerts: Iterable[EarlyWarningAlert]) -> dict[str, int]:
    """Tally alerts by their already-assigned severity."""
    counts = dict.fromkeys(SEVERITIES, 0)
    for alert in alerts:
        counts[alert.severity] = counts.get(alert.severity, 0) + 1
    return counts


def group_by_severity(items: Iterable[T]) -> dict[str, list[T]]:
    """Group objects that expose a ``severity`` attribute into Critical..Low buckets."""
    grouped: dict[str, list[T]] = {severity: [] for severity in SEVERITIES}
    for item in items:
        grouped[item.severity].append(item)  # type: ignore[attr-defined]
    return grouped


def factors_by_ascending_score(factor_scores: dict[str, float]) -> list[str]:
    """Return factor names ordered by ascending score (most penalised first), tie-broken by name."""
    return [name for name, _ in sorted(factor_scores.items(), key=lambda kv: (kv[1], kv[0]))]


def format_source_ids(source_ids: Iterable[str]) -> str:
    """Render a list of source IDs for display, or a clear placeholder when empty."""
    joined = ", ".join(source_ids)
    return joined if joined else "none"


def trace_status(linked_tests: Iterable[tuple[str, bool]]) -> str:
    """Describe the observed state of a requirement's linked test cases.

    ``linked_tests`` holds ``(test_status, has_verification_evidence)`` pairs read straight from
    the loaded records. This is a display label for what the data shows, not a verification
    verdict; the verdict is the Risk engine's alert.
    """
    pairs = [
        (sr.normalize_status(status, sr.StatusDomain.TEST_CASE), has_evidence)
        for status, has_evidence in linked_tests
    ]
    if not pairs:
        return TRACE_NO_LINK
    if any(status == "Passed" and has_evidence for status, has_evidence in pairs):
        return TRACE_VERIFIED
    if any(status == "Not Run" for status, _ in pairs):
        return TRACE_NOT_RUN
    return TRACE_NOT_VERIFIED


def trace_status_color(status: str) -> str:
    """Return the display colour for a trace status label."""
    return TRACE_STATUS_COLORS.get(status, _NEUTRAL)


def truncate(text: str, limit: int = 80) -> str:
    """Shorten long free text for table display, marking that it was cut."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_days(value: int) -> str:
    """Render a whole-day count with its unit, singular or plural."""
    return f"{value} calendar day" if value == 1 else f"{value} calendar days"


def format_score_delta(delta: float) -> str:
    """Render a baseline-to-scenario score change with an explicit sign."""
    if delta == 0:
        return "no change"
    return f"{delta:+.1f}"


def gather_project_analysis(
    project_ids: Iterable[str], analyze: Callable[[str], T]
) -> tuple[dict[str, T], list[str]]:
    """Run ``analyze`` per project, skipping (and recording) any that fail.

    Returns the successful results keyed by project id and a list of failed project ids, so a
    single project's error never prevents the rest of the dashboard from rendering.
    """
    results: dict[str, T] = {}
    failures: list[str] = []
    for project_id in project_ids:
        try:
            results[project_id] = analyze(project_id)
        except Exception:  # noqa: BLE001 - converted into a recorded, visible failure
            failures.append(project_id)
    return results, failures
