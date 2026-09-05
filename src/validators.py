"""Deterministic validation of raw CSV data: columns, duplicate IDs and referential integrity.

These checks run before any analytics so that engines can assume clean, typed input.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

import pandas as pd


class DataValidationError(Exception):
    """Raised when CSV input fails a structural or referential-integrity check."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def ensure_update_dates_not_future(
    record_dates: list[tuple[str, date | None]], as_of_date: date
) -> None:
    """Reject record update dates that occur after the calculation reference date."""
    issues = [
        f"{record_id}: update date {updated.isoformat()} is after as_of_date "
        f"{as_of_date.isoformat()}"
        for record_id, updated in record_dates
        if updated is not None and updated > as_of_date
    ]
    if issues:
        raise DataValidationError(issues)


def check_required_columns(
    df: pd.DataFrame, required_columns: list[str], source_name: str
) -> list[str]:
    """Return an issue for every required column missing from ``df``."""
    present = set(df.columns)
    return [
        f"{source_name}: missing required column '{column}'"
        for column in required_columns
        if column not in present
    ]


def find_duplicate_ids(df: pd.DataFrame, id_column: str, source_name: str) -> list[str]:
    """Return an issue for every duplicated primary-key value in ``id_column``."""
    if id_column not in df.columns:
        return [f"{source_name}: cannot check duplicates, missing id column '{id_column}'"]
    counts = Counter(df[id_column].astype(str))
    return [
        f"{source_name}: duplicate id '{value}' appears {count} times"
        for value, count in counts.items()
        if count > 1
    ]


def validate_referential_integrity(
    child_ids: list[str],
    parent_ids: set[str],
    source_name: str,
    reference_name: str,
) -> list[str]:
    """Return an issue for every child reference that has no matching parent id."""
    return [
        f"{source_name}: '{child_id}' references unknown {reference_name}"
        for child_id in child_ids
        if child_id not in parent_ids
    ]
