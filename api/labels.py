"""Human-facing labels for internal engine vocabulary.

The engines use snake_case factor keys and alert types. Those are implementation details and must
never reach the product surface. This module is the single translation point.
"""

from __future__ import annotations

import re
from typing import Final

from src.risk_engine import (
    ALERT_BLOCKED_TASK,
    ALERT_MILESTONE_DEPENDENCY,
    ALERT_MILESTONE_SLIP,
    ALERT_OVERDUE_ACTION,
    ALERT_REQUIREMENT_VERIFICATION,
    ALERT_RESOURCE_OVERALLOCATION,
    ALERT_STALE_STATUS,
    ALERT_UNOWNED_RISK,
)
from src.scoring_rules import CONFIDENCE_FACTORS, HEALTH_FACTORS

HEALTH_FACTOR_LABELS: Final[dict[str, str]] = {
    "schedule_performance": "Schedule Health",
    "milestone_readiness": "Milestone Readiness",
    "task_execution": "Task Delivery",
    "risk_exposure": "Risk Management",
    "dependency_status": "Dependency Health",
    "resource_capacity": "Team Capacity",
    "action_closure": "Action Follow-Through",
}

HEALTH_FACTOR_DESCRIPTIONS: Final[dict[str, str]] = {
    "schedule_performance": "How far the forecast completion date has moved from the baseline.",
    "milestone_readiness": "Whether milestones are being met on their committed dates.",
    "task_execution": "Progress against plan across the project's tasks, including blockers.",
    "risk_exposure": "The weight of open risks, scored by probability and impact.",
    "dependency_status": "Delay carried by cross-team and cross-project dependencies.",
    "resource_capacity": "Whether assigned people are allocated beyond their weekly capacity.",
    "action_closure": "How promptly agreed actions are being closed out.",
}

CONFIDENCE_FACTOR_LABELS: Final[dict[str, str]] = {
    "data_freshness": "Reporting Freshness",
    "data_completeness": "Information Completeness",
    "ownership_coverage": "Accountability Coverage",
    "source_reliability": "Data Availability",
}

CONFIDENCE_FACTOR_DESCRIPTIONS: Final[dict[str, str]] = {
    "data_freshness": "How recently the underlying records were updated.",
    "data_completeness": "Whether required fields such as dates and baselines are populated.",
    "ownership_coverage": "Whether risks, tasks and actions have a named owner.",
    "source_reliability": "The assessed dependability of the systems this data came from.",
}

ALERT_TYPE_LABELS: Final[dict[str, str]] = {
    ALERT_UNOWNED_RISK: "Risk without a mitigation owner",
    ALERT_MILESTONE_SLIP: "Milestone forecast to slip",
    ALERT_MILESTONE_DEPENDENCY: "Milestone blocked by a dependency",
    ALERT_BLOCKED_TASK: "Blocked task",
    ALERT_OVERDUE_ACTION: "Overdue action",
    ALERT_RESOURCE_OVERALLOCATION: "Resource over capacity",
    ALERT_STALE_STATUS: "Status not recently updated",
    ALERT_REQUIREMENT_VERIFICATION: "Requirement without verification",
}


def health_factor_label(factor_key: str) -> str:
    """Return the display label for a health factor key."""
    return HEALTH_FACTOR_LABELS.get(factor_key, _fallback_label(factor_key))


def confidence_factor_label(factor_key: str) -> str:
    """Return the display label for a confidence factor key."""
    return CONFIDENCE_FACTOR_LABELS.get(factor_key, _fallback_label(factor_key))


def alert_type_label(alert_type: str) -> str:
    """Return the display label for an early-warning alert type."""
    return ALERT_TYPE_LABELS.get(alert_type, _fallback_label(alert_type))


def _fallback_label(key: str) -> str:
    """Title-case an unmapped key so no raw snake_case ever reaches the UI."""
    return key.replace("_", " ").strip().title()


# Engine messages are written for engineers and can embed raw record field names such as
# ``mitigation_owner``. Those are rewritten here rather than in the engines, which stay unchanged.
_SNAKE_CASE_TOKEN: Final[re.Pattern[str]] = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")

# Engine prose also carries internal build vocabulary and factor names written as separate words,
# which the snake_case rule cannot see. Rewriting them here keeps the engines untouched.
_BUILD_VOCABULARY: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\s*\(Version\s*\d+\)", re.IGNORECASE), ""),
    (re.compile(r"\bcoarse Version\s*\d+\b", re.IGNORECASE), "coarse"),
    (re.compile(r"\bVersion\s*\d+\s+simulates\b", re.IGNORECASE), "EPOS simulates"),
)

# Factor names as prose. Matched without regard to case, and the replacement takes the
# capitalisation of the text it replaces so sentence and title positions both read correctly.
_FACTOR_PROSE: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\btask execution\b", re.IGNORECASE), "task delivery"),
    (re.compile(r"\brisk exposure\b", re.IGNORECASE), "risk management"),
    (re.compile(r"\bdata freshness\b", re.IGNORECASE), "reporting freshness"),
    (re.compile(r"\bresource capacity\b", re.IGNORECASE), "team capacity"),
    (re.compile(r"\bschedule performance\b", re.IGNORECASE), "schedule health"),
)


def _match_case(original: str, replacement: str) -> str:
    """Give the replacement the same opening capitalisation as the text it replaces."""
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _key_label(match: re.Match[str]) -> str:
    token = match.group(0)
    for table in (HEALTH_FACTOR_LABELS, CONFIDENCE_FACTOR_LABELS, ALERT_TYPE_LABELS):
        if token in table:
            return table[token]
    return token.replace("_", " ")


def humanise_keys(text: str) -> str:
    """Rewrite only snake_case keys, leaving ordinary words exactly as written."""
    return _SNAKE_CASE_TOKEN.sub(_key_label, text)


def humanise(text: str) -> str:
    """Rewrite any snake_case token inside an engine message into readable words.

    Known factor and alert keys use their product label; anything else simply loses its
    underscores. Internal build vocabulary is removed. The meaning is never altered.
    """
    result = humanise_keys(text)
    for pattern, replacement in _BUILD_VOCABULARY:
        result = pattern.sub(replacement, result)
    for pattern, replacement in _FACTOR_PROSE:
        result = pattern.sub(lambda m, r=replacement: _match_case(m.group(0), r), result)
    return result


def humanise_all(texts: list[str]) -> list[str]:
    """Humanise every message in a list."""
    return [humanise(text) for text in texts]


def missing_labels() -> list[str]:
    """Return every engine key that has no explicit product label.

    Used by tests to guarantee the translation table stays complete as engines evolve.
    """
    missing = [key for key in HEALTH_FACTORS if key not in HEALTH_FACTOR_LABELS]
    missing += [key for key in CONFIDENCE_FACTORS if key not in CONFIDENCE_FACTOR_LABELS]
    missing += [key for key in HEALTH_FACTORS if key not in HEALTH_FACTOR_DESCRIPTIONS]
    missing += [key for key in CONFIDENCE_FACTORS if key not in CONFIDENCE_FACTOR_DESCRIPTIONS]
    return missing
