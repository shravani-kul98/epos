"""User-facing wording must not carry internal build or engine vocabulary.

The engines are written for engineers and are deliberately left unchanged. The label layer is
responsible for translating their prose before it reaches a person.
"""

from __future__ import annotations

import json

import pytest

from api import labels
from tests.api.conftest import url

FORBIDDEN = ("version 1", "task execution", "risk exposure", "data freshness", "resource capacity")


@pytest.mark.parametrize(
    "message",
    [
        "Schedule performance uses calendar-day variance (Version 1).",
        "Schedule impact is a coarse Version 1 heuristic lookup, not a validated method.",
        "Version 1 simulates a single dependency at a time.",
        "No tasks are available; task execution cannot be fully assessed.",
        "Reduced task execution by 15 points.",
        "Reduced risk exposure by 35 points.",
        "No open risks exceed the threshold; risk exposure is 96.",
    ],
)
def test_engine_prose_loses_internal_vocabulary(message: str) -> None:
    result = labels.humanise(message).lower()
    for term in FORBIDDEN:
        assert term not in result, f"{term!r} survived in {result!r}"


def test_snake_case_field_names_are_still_rewritten() -> None:
    assert "_" not in labels.humanise("Risk R-2001 has no mitigation_owner.")


def test_meaning_and_figures_are_preserved() -> None:
    """Translation must never change a number or drop the substance of a message."""
    result = labels.humanise("Reduced task execution by 15 points.")
    assert "15 points" in result
    assert result.startswith("Reduced")


def test_ordinary_wording_is_untouched() -> None:
    message = "Milestone M-202 is forecast 46 calendar days later than baseline."
    assert labels.humanise(message) == message


def test_no_internal_vocabulary_reaches_a_project_dashboard(client) -> None:
    """End-to-end check across every string the project view renders."""
    response = client.get(url("/analytics/projects/P-002"))
    assert response.status_code == 200

    body = json.dumps(response.json()).lower()
    for term in FORBIDDEN:
        assert term not in body, f"{term!r} reached the project dashboard"


def test_no_internal_vocabulary_reaches_the_portfolio(client) -> None:
    response = client.get(url("/analytics/portfolio"))
    assert response.status_code == 200

    body = json.dumps(response.json()).lower()
    for term in FORBIDDEN:
        assert term not in body, f"{term!r} reached the portfolio view"
