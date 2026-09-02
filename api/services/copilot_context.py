"""Validated conversational selectors; earlier model prose is never factual evidence."""

from __future__ import annotations

import json
import re
from dataclasses import fields, replace

from src.data_loader import PortfolioData

_GLOBAL_SCOPE = re.compile(
    r"\b(whole portfolio|all projects|every project|across (?:the )?portfolio|portfolio-wide|whole workspace)\b",
    re.I,
)
_FOLLOW_UP = re.compile(
    r"\b(it|its|that|those|them|this project|same|what about|how about|why|and at)\b", re.I
)
_SCHEDULE = re.compile(r"\b(what if|scenario|simulate|simulation|slips?|delay|and at)\b", re.I)
_DAYS = re.compile(r"(?<![\w.])([0-9]+)\s*(?:calendar\s+)?days?\b", re.I)
_SELECTOR_KEYS = (
    "project_id",
    "project_ids",
    "record_type",
    "status_filter",
    "domain_filter",
    "project_query",
    "dependency_id",
    "additional_delay_days",
)


def known_ids(question: str, values: list[str]) -> list[str]:
    """Resolve identifiers in text only from the currently authorized vocabulary."""
    matches = []
    for value in values:
        match = re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", question, re.I)
        if match:
            matches.append((match.start(), value))
    return [value for _, value in sorted(matches)]


def previous_context(history: list[dict[str, str | None]] | None) -> dict[str, str]:
    """Read only validated selector metadata from the most recent usable turn."""
    for turn in reversed(history or []):
        if turn.get("role") != "assistant":
            continue
        context = {
            key: value
            for key in _SELECTOR_KEYS
            if isinstance(value := turn.get(key), str) and value
        }
        if context:
            if intent := turn.get("matched_intent") or turn.get("intent"):
                context["intent"] = intent
            return context
    return {}


def apply_context(
    question: str,
    intent: str | None,
    context: dict[str, str],
    history: list[dict[str, str | None]] | None,
    portfolio: PortfolioData,
    selected_project_id: str | None,
) -> tuple[str | None, dict[str, str]]:
    """Prefer explicit selectors, then page scope, then the conversation's current topic."""
    current = dict(context)
    previous = previous_context(history)
    if _GLOBAL_SCOPE.search(question):
        previous = {}
        selected_project_id = None
    if selected_project_id in portfolio.project_ids:
        current.setdefault("project_id", selected_project_id)
    if "project_id" not in current and "project_ids" not in current:
        prior = previous.get("project_id")
        if prior in portfolio.project_ids:
            current["project_id"] = prior
        elif _FOLLOW_UP.search(question) and previous.get("project_ids"):
            try:
                candidates = json.loads(previous["project_ids"])
            except (TypeError, json.JSONDecodeError):
                candidates = []
            if (
                isinstance(candidates, list)
                and candidates
                and all(isinstance(pid, str) and pid in portfolio.project_ids for pid in candidates)
            ):
                current["project_ids"] = json.dumps(candidates)
    if (
        re.match(r"\s*(?:and\s+)?(?:what|how) about\b", question, re.I)
        and previous.get("intent")
        and intent in {None, "list_projects", "why_project_band", "projects_needing_attention"}
    ):
        intent = previous["intent"]
        for key in ("record_type", "status_filter", "domain_filter", "project_query"):
            if previous.get(key):
                current.setdefault(key, previous[key])
    dependencies = known_ids(question, [item.dependency_id for item in portfolio.dependencies])
    if _SCHEDULE.search(question):
        if dependencies:
            current["dependency_id"] = dependencies[0]
        elif previous.get("intent") == "scenario_analysis" and previous.get("dependency_id"):
            current["dependency_id"] = previous["dependency_id"]
        delay = _DAYS.search(question)
        if delay:
            current["additional_delay_days"] = delay.group(1)
        if current.get("dependency_id"):
            intent = "scenario_analysis"
    return intent, current


def select_portfolio(portfolio: PortfolioData, project_ids: set[str]) -> PortfolioData:
    """Narrow an already authorized snapshot; never retrieve extra records or mutate it."""
    return replace(
        portfolio,
        **{
            field.name: [
                row
                for row in getattr(portfolio, field.name)
                if getattr(row, "project_id", None) in project_ids
            ]
            for field in fields(portfolio)
            if field.name != "status_anomalies"
        },
        status_anomalies=[],
    )
