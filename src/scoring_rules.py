"""Single source of truth for Phase 3 scoring configuration and controlled vocabulary.

This module holds all Version 1 penalty values, thresholds, canonical status vocabulary,
freshness bands, severity ordering and validation logic for the Health, Confidence and
Early-Warning engines. Weights and band cut-offs that already exist in ``config.py`` are
re-exported here (never duplicated) so engines have one import location.

Nothing in this module performs engine calculations; it provides configuration data and
pure vocabulary helpers only. It deliberately does not import ``schemas`` to stay free of
circular dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Final

from src.config import (
    CONFIDENCE_BANDS,
    CONFIDENCE_WEIGHTS,
    HEALTH_BANDS,
    HEALTH_WEIGHTS,
)

__all__ = [
    "CONFIDENCE_BANDS",
    "CONFIDENCE_WEIGHTS",
    "HEALTH_BANDS",
    "HEALTH_WEIGHTS",
    "ScoringConfigError",
    "StatusDomain",
    "normalize_status",
    "is_known_status",
    "is_active_risk_status",
    "is_terminal_schedule_status",
    "classify_freshness",
    "validate_scoring_config",
]


class ScoringConfigError(Exception):
    """Raised when the scoring configuration is internally inconsistent."""


# --------------------------------------------------------------------------- factors
HEALTH_FACTORS: Final[tuple[str, ...]] = (
    "schedule_performance",
    "milestone_readiness",
    "task_execution",
    "risk_exposure",
    "dependency_status",
    "resource_capacity",
    "action_closure",
)
CONFIDENCE_FACTORS: Final[tuple[str, ...]] = (
    "data_freshness",
    "data_completeness",
    "ownership_coverage",
    "source_reliability",
)

CRITICALITY_LEVELS: Final[tuple[str, ...]] = ("Low", "Medium", "High", "Critical")

# Severity sort weight: higher is more severe (used for stable alert ordering).
SEVERITY_ORDER: Final[dict[str, int]] = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


# --------------------------------------------------------------- canonical status vocab
class StatusDomain(StrEnum):
    """Controlled-vocabulary domains for status/priority normalisation."""

    SCHEDULE = "schedule"  # project / milestone / task delivery status
    RISK = "risk"
    MITIGATION = "mitigation"
    ACTION = "action"
    DEPENDENCY = "dependency"
    REQUIREMENT = "requirement"
    TEST_CASE = "test_case"
    PRIORITY = "priority"  # criticality / priority


CANONICAL_STATUSES: Final[dict[StatusDomain, tuple[str, ...]]] = {
    StatusDomain.SCHEDULE: (
        "Not Started",
        "In Progress",
        "On Track",
        "At Risk",
        "Delayed",
        "Blocked",
        "Complete",
        "Closed",
        "Cancelled",
    ),
    StatusDomain.RISK: ("Open", "Mitigating", "Closed", "Accepted"),
    StatusDomain.MITIGATION: ("Not Started", "In Progress", "Complete", "Not Required"),
    StatusDomain.ACTION: ("Open", "In Progress", "Blocked", "Complete", "Closed", "Cancelled"),
    StatusDomain.DEPENDENCY: (
        "On Track",
        "At Risk",
        "Delayed",
        "Blocked",
        "Complete",
        "Closed",
        "Resolved",
    ),
    StatusDomain.REQUIREMENT: ("Draft", "Approved", "Changed", "Superseded", "Retired"),
    StatusDomain.TEST_CASE: ("Not Run", "Passed", "Failed"),
    StatusDomain.PRIORITY: CRITICALITY_LEVELS,
}

# Accepted upstream aliases, keyed by normalised (lower-case, single-spaced) form.
STATUS_ALIASES: Final[dict[StatusDomain, dict[str, str]]] = {
    StatusDomain.SCHEDULE: {"completed": "Complete", "done": "Complete", "wip": "In Progress"},
    StatusDomain.RISK: {"in mitigation": "Mitigating"},
    StatusDomain.MITIGATION: {"completed": "Complete", "n/a": "Not Required"},
    StatusDomain.ACTION: {"completed": "Complete"},
    StatusDomain.DEPENDENCY: {"resolved": "Resolved", "completed": "Complete"},
    StatusDomain.REQUIREMENT: {"approved.": "Approved"},
    StatusDomain.TEST_CASE: {"not run": "Not Run", "pass": "Passed", "fail": "Failed"},
    StatusDomain.PRIORITY: {"crit": "Critical", "med": "Medium"},
}

# Canonical terminal / active status groupings for consistent engine checks.
TERMINAL_SCHEDULE_STATUSES: Final[frozenset[str]] = frozenset({"Complete", "Closed", "Cancelled"})
TERMINAL_ACTION_STATUSES: Final[frozenset[str]] = frozenset({"Complete", "Closed", "Cancelled"})
TERMINAL_RISK_STATUSES: Final[frozenset[str]] = frozenset({"Closed"})
# Risks that no longer carry scored exposure. Anything else, including an unrecognised status,
# is treated as live so a typo can never hide exposure from the engines.
INACTIVE_RISK_STATUSES: Final[frozenset[str]] = frozenset({"Closed", "Accepted"})
TERMINAL_DEPENDENCY_STATUSES: Final[frozenset[str]] = frozenset({"Complete", "Closed", "Resolved"})
ACTIVE_REQUIREMENT_STATUSES: Final[frozenset[str]] = frozenset({"Approved", "Changed"})


def _normalize_key(raw: str) -> str:
    """Lower-case and collapse internal/edge whitespace for tolerant matching."""
    return " ".join(raw.strip().split()).lower()


def normalize_status(raw: str | None, domain: StatusDomain) -> str | None:
    """Return the canonical status for ``raw`` in ``domain``, or None if unrecognised."""
    if raw is None:
        return None
    key = _normalize_key(raw)
    if not key:
        return None
    for canonical in CANONICAL_STATUSES[domain]:
        if key == canonical.lower():
            return canonical
    return STATUS_ALIASES[domain].get(key)


def is_known_status(raw: str | None, domain: StatusDomain) -> bool:
    """True when ``raw`` maps to a canonical value in ``domain``."""
    return normalize_status(raw, domain) is not None


def is_terminal_schedule_status(raw: str | None) -> bool:
    """True when a project/milestone/task status is Complete, Closed or Cancelled."""
    return normalize_status(raw, StatusDomain.SCHEDULE) in TERMINAL_SCHEDULE_STATUSES


def is_active_risk_status(raw: str | None) -> bool:
    """True unless a risk is recorded as Closed or Accepted (fail-safe for unknown values)."""
    return normalize_status(raw, StatusDomain.RISK) not in INACTIVE_RISK_STATUSES


# ----------------------------------------------------------------- attention
# One definition of "needs attention", shared by every dashboard and by Ask EPOS.
ATTENTION_HEALTH_BANDS: Final[frozenset[str]] = frozenset({"Amber", "Red"})
# High warnings are common on healthy projects; counting them flagged the whole portfolio.
ATTENTION_ALERT_SEVERITIES: Final[frozenset[str]] = frozenset({"Critical"})
ATTENTION_CRITERIA: Final[str] = (
    "Health is Amber or Red, or a Critical early warning is present. "
    "Confidence is reported separately."
)


def needs_attention(health_band: str, alert_severities: Iterable[str]) -> bool:
    """True when a project's calculated band or its open warnings call for intervention."""
    return health_band in ATTENTION_HEALTH_BANDS or any(
        severity in ATTENTION_ALERT_SEVERITIES for severity in alert_severities
    )


# ----------------------------------------------------------------- health thresholds
# Schedule performance: (max calendar-day slip inclusive, score). Slips beyond the last
# threshold use SCHEDULE_SLIP_BEYOND_SCORE. Missing dates use the fallback.
SCHEDULE_SLIP_THRESHOLDS: Final[tuple[tuple[int, int], ...]] = (
    (0, 100),
    (5, 85),
    (10, 70),
    (20, 50),
    (120, 25),
    (240, 12),
)
SCHEDULE_SLIP_BEYOND_SCORE: Final[int] = 5
SCHEDULE_MISSING_FALLBACK: Final[int] = 50

MILESTONE_SLIP_PENALTY: Final[dict[str, int]] = {"Low": 5, "Medium": 10, "High": 18, "Critical": 25}
MILESTONE_STATUS_PENALTY: Final[dict[str, int]] = {"At Risk": 8, "Delayed": 15, "Blocked": 20}
MILESTONE_NONE_FALLBACK: Final[int] = 50

TASK_BLOCKED_PENALTY: Final[int] = 8
TASK_BLOCKED_HIGH_CRIT_PENALTY: Final[int] = 15
TASK_OVERDUE_PENALTY: Final[int] = 6
TASK_OVERDUE_HIGH_CRIT_EXTRA: Final[int] = 6
TASK_LOW_COMPLETION_PENALTY: Final[int] = 5
TASK_LOW_COMPLETION_THRESHOLD: Final[int] = 50
TASK_NONE_FALLBACK: Final[int] = 50

# Risk exposure bands: (min_exposure, max_exposure, open_penalty, no_owner_extra, not_started_extra).
RISK_EXPOSURE_BANDS: Final[tuple[tuple[int, int, int, int, int], ...]] = (
    (20, 25, 20, 10, 5),
    (12, 19, 10, 5, 0),
    (6, 11, 4, 0, 0),
    (1, 5, 0, 0, 0),
)

DEPENDENCY_DELAY_PENALTY: Final[dict[str, int]] = {
    "Low": 5,
    "Medium": 10,
    "High": 15,
    "Critical": 20,
}
DEPENDENCY_BLOCKED_EXTRA: Final[int] = 10
DEPENDENCY_AT_RISK_EXTRA: Final[int] = 5
# A dependency already reported Delayed is at least as serious as one only At Risk, so moving from
# At Risk to Delayed can never raise the factor.
DEPENDENCY_DELAYED_EXTRA: Final[int] = 8
# Additional penalty by delay length: (max delay days inclusive, extra). Beyond the last -> beyond.
DEPENDENCY_LONG_DELAY_EXTRAS: Final[tuple[tuple[int, int], ...]] = ((60, 0), (90, 5), (180, 10))
DEPENDENCY_LONG_DELAY_BEYOND_EXTRA: Final[int] = 15
DEPENDENCY_NONE_FALLBACK: Final[int] = 70

# Resource utilisation: (max utilisation percent inclusive, penalty); beyond -> beyond penalty.
RESOURCE_UTIL_THRESHOLDS: Final[tuple[tuple[int, int], ...]] = (
    (90, 0),
    (100, 3),
    (110, 10),
    (125, 18),
)
RESOURCE_UTIL_BEYOND_PENALTY: Final[int] = 25
RESOURCE_NONE_FALLBACK: Final[int] = 70

ACTION_OVERDUE_PENALTY: Final[dict[str, int]] = {"Low": 2, "Medium": 4, "High": 7, "Critical": 10}
ACTION_NO_OWNER_EXTRA: Final[int] = 5
ACTION_NONE_FALLBACK: Final[int] = 70

FACTOR_BASE_SCORE: Final[int] = 100


# ------------------------------------------------------------- confidence thresholds
# Freshness bands measured in calendar days relative to as_of_date.
FRESHNESS_FRESH_MAX_DAYS: Final[int] = 7
FRESHNESS_STALE_MAX_DAYS: Final[int] = 14
FRESHNESS_SIGNIFICANT_MAX_DAYS: Final[int] = 21

FRESHNESS_FRESH: Final[str] = "fresh"
FRESHNESS_STALE: Final[str] = "stale"
FRESHNESS_SIGNIFICANTLY_STALE: Final[str] = "significantly_stale"
FRESHNESS_CRITICALLY_STALE: Final[str] = "critically_stale"

PROJECT_STATUS_STALE_PENALTY: Final[int] = 10  # 8-14 days
PROJECT_STATUS_SIGNIFICANT_PENALTY: Final[int] = 20  # 15-21 days
PROJECT_STATUS_CRITICAL_PENALTY: Final[int] = 35  # >21 days
PROJECT_STATUS_MISSING_PENALTY: Final[int] = 40

STALE_RECORD_AGE_DAYS: Final[int] = 7  # a record is stale if older than this
# Stale-record percentage penalty: (max percent inclusive, penalty); beyond -> beyond penalty.
STALE_RECORD_PENALTY_THRESHOLDS: Final[tuple[tuple[float, int], ...]] = (
    (10.0, 0),
    (25.0, 10),
    (50.0, 25),
)
STALE_RECORD_BEYOND_PENALTY: Final[int] = 40

# Completeness: (max missing-field percent inclusive, score); beyond -> beyond score.
COMPLETENESS_SCORE_THRESHOLDS: Final[tuple[tuple[float, int], ...]] = (
    (5.0, 100),
    (15.0, 80),
    (30.0, 60),
    (50.0, 35),
)
COMPLETENESS_BEYOND_SCORE: Final[int] = 10
# A project missing a core record type has its completeness capped: (record type, cap).
RECORD_COVERAGE_COMPLETENESS_CAPS: Final[dict[str, int]] = {
    "tasks": 20,
    "milestones": 20,
    "risks": 60,
}

# Required decision-support fields per entity, applied only to active records.
REQUIRED_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "project": ("baseline_end_date", "forecast_end_date", "status_update_date"),
    "milestone": ("baseline_date", "forecast_date", "status", "criticality", "owner"),
    "task": (
        "owner",
        "status",
        "planned_end_date",
        "forecast_end_date",
        "completion_percent",
        "last_updated_date",
    ),
    "risk": ("probability", "impact", "status", "due_date", "mitigation_status"),
    "action": ("due_date", "status", "priority"),
    "requirement": ("priority", "status", "owner", "last_updated_date"),
    "test_case": ("status", "owner", "last_updated_date"),
}

OWNERSHIP_TASK_PENALTY: Final[int] = 5
OWNERSHIP_TASK_CAP: Final[int] = 25
OWNERSHIP_RISK_PENALTY: Final[int] = 10
OWNERSHIP_RISK_CAP: Final[int] = 35
OWNERSHIP_ACTION_PENALTY: Final[int] = 8
OWNERSHIP_ACTION_CAP: Final[int] = 25
OWNERSHIP_REQUIREMENT_PENALTY: Final[int] = 5
OWNERSHIP_REQUIREMENT_CAP: Final[int] = 15
OWNERSHIP_CHANGE_REQUEST_PENALTY: Final[int] = 5
OWNERSHIP_CHANGE_REQUEST_CAP: Final[int] = 10

SOURCE_RELIABILITY_ALL_OK: Final[int] = 100
SOURCE_RELIABILITY_OPTIONAL_MISSING: Final[int] = 70
SOURCE_RELIABILITY_CRITICAL_MISSING: Final[int] = 40
CRITICAL_TABLES: Final[tuple[str, ...]] = ("projects", "milestones", "tasks", "risks")
OPTIONAL_TABLES: Final[tuple[str, ...]] = (
    "dependencies",
    "actions",
    "resources",
    "requirements",
    "test_cases",
    "trace_links",
    "change_requests",
)
SOURCE_AVAILABILITY_LABEL: Final[str] = "Prototype data-source availability assessment."


# --------------------------------------------------------------- alert thresholds
ALERT_UNOWNED_RISK_EXPOSURE_MIN: Final[int] = 20
ALERT_MILESTONE_SLIP_LARGE_DAYS: Final[int] = 10
ALERT_DEPENDENCY_LARGE_DELAY_DAYS: Final[int] = 10
ALERT_ACTION_OVERDUE_LARGE_DAYS: Final[int] = 7
ALERT_STALE_STATUS_TRIGGER_DAYS: Final[int] = 14  # older than this (or missing) raises an alert
ALERT_STALE_STATUS_SIGNIFICANT_DAYS: Final[int] = 21  # >21 escalates to High
ALERT_RESOURCE_UTIL_CRITICAL: Final[int] = 125
ALERT_RESOURCE_UTIL_HIGH: Final[int] = 110
ALERT_RESOURCE_UTIL_MEDIUM: Final[int] = 100


# ------------------------------------------------------------- change impact rules
# Requirement-sourced trace link types and the target entity each resolves to. These are the
# only requirement-sourced link types present in the Version 1 data model.
CHANGE_IMPACT_LINK_TARGETS: Final[dict[str, str]] = {
    "implemented_by": "Task",
    "verified_by": "TestCase",
    "delivered_in": "Milestone",
}

# Coarse Version 1 estimate in calendar days, keyed by
# (highest affected milestone criticality, change request priority).
CHANGE_IMPACT_SCHEDULE_DAYS: Final[dict[tuple[str, str], int]] = {
    ("Critical", "Critical"): 20,
    ("Critical", "High"): 15,
    ("Critical", "Medium"): 10,
    ("Critical", "Low"): 5,
    ("High", "Critical"): 15,
    ("High", "High"): 10,
    ("High", "Medium"): 7,
    ("High", "Low"): 3,
    ("Medium", "Critical"): 10,
    ("Medium", "High"): 7,
    ("Medium", "Medium"): 5,
    ("Medium", "Low"): 2,
    ("Low", "Critical"): 5,
    ("Low", "High"): 3,
    ("Low", "Medium"): 2,
    ("Low", "Low"): 1,
}
CHANGE_IMPACT_NO_MILESTONE_DAYS: Final[int] = 0
# Number of affected artefacts at which breadth alone raises the change risk level.
CHANGE_IMPACT_BREADTH_THRESHOLD: Final[int] = 5

# ----------------------------------------------------------------- scenario rules
# Bounds for a simulated dependency delay; values outside these are rejected, not clamped.
SCENARIO_MIN_DELAY_DAYS: Final[int] = 1
SCENARIO_MAX_DELAY_DAYS: Final[int] = 365
# A dependency that gains simulated delay is treated as Delayed unless already Blocked.
SCENARIO_DELAYED_STATUS: Final[str] = "Delayed"

# Version 2 adds schedule propagation. Persisted results record which version produced them, so a
# stored scenario is never silently compared against a result calculated by different rules.
SCENARIO_CALCULATION_VERSION: Final[str] = "2.0"


class ScenarioInterventionType(StrEnum):
    """A change a scenario may apply. Each maps to authoritative recorded data."""

    DEPENDENCY_DELAY = "dependency_delay"
    TASK_DELAY = "task_delay"
    MILESTONE_DELAY = "milestone_delay"
    RISK_PROBABILITY = "risk_probability"
    RISK_IMPACT = "risk_impact"
    RESOURCE_CAPACITY = "resource_capacity"


SCENARIO_INTERVENTION_UNITS: Final[dict[ScenarioInterventionType, str]] = {
    ScenarioInterventionType.DEPENDENCY_DELAY: "calendar days",
    ScenarioInterventionType.TASK_DELAY: "calendar days",
    ScenarioInterventionType.MILESTONE_DELAY: "calendar days",
    ScenarioInterventionType.RISK_PROBABILITY: "probability points (1-5)",
    ScenarioInterventionType.RISK_IMPACT: "impact points (1-5)",
    ScenarioInterventionType.RESOURCE_CAPACITY: "capacity hours per week",
}

# Inclusive bounds per intervention, in that intervention's unit. Risk bounds mirror the recorded
# 1-5 scale; capacity is bounded to a working week rather than an invented ceiling.
SCENARIO_INTERVENTION_BOUNDS: Final[dict[ScenarioInterventionType, tuple[int, int]]] = {
    ScenarioInterventionType.DEPENDENCY_DELAY: (SCENARIO_MIN_DELAY_DAYS, SCENARIO_MAX_DELAY_DAYS),
    ScenarioInterventionType.TASK_DELAY: (SCENARIO_MIN_DELAY_DAYS, SCENARIO_MAX_DELAY_DAYS),
    ScenarioInterventionType.MILESTONE_DELAY: (SCENARIO_MIN_DELAY_DAYS, SCENARIO_MAX_DELAY_DAYS),
    ScenarioInterventionType.RISK_PROBABILITY: (1, 5),
    ScenarioInterventionType.RISK_IMPACT: (1, 5),
    ScenarioInterventionType.RESOURCE_CAPACITY: (0, 168),
}

# The delay ladder used for sensitivity analysis. Fixed so repeated runs are comparable.
SCENARIO_SENSITIVITY_DELAY_DAYS: Final[tuple[int, ...]] = (1, 5, 10, 30, 90, 180, 365)


def classify_freshness(age_days: int) -> str:
    """Classify a record age in calendar days into a freshness band."""
    if age_days <= FRESHNESS_FRESH_MAX_DAYS:
        return FRESHNESS_FRESH
    if age_days <= FRESHNESS_STALE_MAX_DAYS:
        return FRESHNESS_STALE
    if age_days <= FRESHNESS_SIGNIFICANT_MAX_DAYS:
        return FRESHNESS_SIGNIFICANTLY_STALE
    return FRESHNESS_CRITICALLY_STALE


def validate_scoring_config() -> None:
    """Validate that weight families sum to 1.0 and factor keys are consistent.

    Raises:
        ScoringConfigError: if any weight family is inconsistent.
    """
    for name, weights, expected in (
        ("health", HEALTH_WEIGHTS, HEALTH_FACTORS),
        ("confidence", CONFIDENCE_WEIGHTS, CONFIDENCE_FACTORS),
    ):
        total = round(sum(weights.values()), 6)
        if total != 1.0:
            raise ScoringConfigError(f"{name} weights sum to {total}, expected 1.0")
        if set(weights) != set(expected):
            raise ScoringConfigError(
                f"{name} weight keys {sorted(weights)} do not match factors {sorted(expected)}"
            )

    for label, penalties in (
        ("milestone slip", MILESTONE_SLIP_PENALTY),
        ("dependency delay", DEPENDENCY_DELAY_PENALTY),
        ("action overdue", ACTION_OVERDUE_PENALTY),
    ):
        if set(penalties) != set(CRITICALITY_LEVELS):
            raise ScoringConfigError(f"{label} penalties must cover {CRITICALITY_LEVELS}")

    expected_impact_keys = {
        (criticality, priority)
        for criticality in CRITICALITY_LEVELS
        for priority in CRITICALITY_LEVELS
    }
    if set(CHANGE_IMPACT_SCHEDULE_DAYS) != expected_impact_keys:
        raise ScoringConfigError(
            "change impact schedule table must cover every "
            "(milestone criticality, change priority) combination"
        )


# Fail fast at import if the configuration is inconsistent.
validate_scoring_config()
