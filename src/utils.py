"""Small, pure helper functions shared across deterministic engines.

Kept dependency-free (standard library only) so they are trivially testable.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from src.config import CONFIDENCE_BANDS, HEALTH_BANDS


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp ``value`` into the inclusive range [low, high]."""
    return max(low, min(high, value))


def reference_timestamp(as_of_date: date) -> datetime:
    """Return midnight UTC on ``as_of_date`` as the deterministic calculation timestamp.

    This represents the calculation reference time, not a live wall-clock execution time,
    so repeated runs with the same ``as_of_date`` produce identical results.
    """
    return datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=UTC)


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide safely, returning ``default`` when the denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def days_between(start: date, end: date) -> int:
    """Return signed whole-day difference ``end - start``."""
    return (end - start).days


def is_stale(last_updated: date, as_of: date, stale_days: int) -> bool:
    """Return True when ``last_updated`` is older than ``stale_days`` before ``as_of``."""
    return days_between(last_updated, as_of) > stale_days


def band_for_score(score: float, bands: dict[str, float]) -> str:
    """Map a 0–100 score to a band label using lower-inclusive bounds."""
    for label, lower_bound in sorted(bands.items(), key=lambda item: item[1], reverse=True):
        if score >= lower_bound:
            return label
    # Fallback to the lowest band if none matched (e.g. negative score).
    return min(bands.items(), key=lambda item: item[1])[0]


def health_band(score: float) -> str:
    """Return the Health band (Green/Amber/Red) for a 0–100 score."""
    return band_for_score(score, HEALTH_BANDS)


def confidence_band(score: float) -> str:
    """Return the Confidence band (High/Medium/Low) for a 0–100 score."""
    return band_for_score(score, CONFIDENCE_BANDS)
