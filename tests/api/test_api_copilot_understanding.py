"""Ask EPOS understanding of questions phrased in a user's own words.

These tests cover the routing layer only. Nothing here contacts a model; the deterministic
resolver is what decides whether a question can be answered at all.
"""

from __future__ import annotations

from api.services import copilot_service
from src.ui_formatting import ANALYSIS_DATE


def test_a_project_named_in_words_is_recognised(csv_portfolio) -> None:
    matches = copilot_service.resolve_projects_by_name(
        "Why is the Supplier Decarbonisation Programme at risk?", csv_portfolio
    )
    assert matches, "a project named in full should be resolved"
    names = {p.project_id: p.project_name for p in csv_portfolio.projects}
    assert "Supplier" in names[matches[0]]


def test_filler_words_alone_never_match_a_project(csv_portfolio) -> None:
    assert (
        copilot_service.resolve_projects_by_name("why is the project at risk?", csv_portfolio) == []
    )


def test_an_unknown_name_resolves_to_nothing(csv_portfolio) -> None:
    assert (
        copilot_service.resolve_projects_by_name("How is Apollo Rocket doing?", csv_portfolio) == []
    )


def test_a_named_project_supplies_the_missing_context(csv_portfolio) -> None:
    """ "Why is <name> red?" must work without the user knowing the identifier."""
    answer = copilot_service.ask(
        "Why is the Supplier Decarbonisation Programme red?", csv_portfolio, ANALYSIS_DATE
    )
    assert answer.status != "clarification" or "Which project" not in answer.executive_summary


def test_an_unsupported_question_explains_what_epos_can_do(csv_portfolio) -> None:
    answer = copilot_service.ask("What is the weather tomorrow?", csv_portfolio, ANALYSIS_DATE)
    assert answer.status == "clarification"
    summary = answer.executive_summary.lower()
    assert "project status" in summary and "portfolio" in summary
    assert answer.suggested_questions


def test_guidance_never_exposes_routing_vocabulary(csv_portfolio) -> None:
    answer = copilot_service.ask("qwertyuiop", csv_portfolio, ANALYSIS_DATE)
    lowered = answer.executive_summary.lower()
    for term in ("intent", "route", "regex", "parser", "unsupported intent"):
        assert term not in lowered


def test_name_resolution_cannot_invent_a_project(csv_portfolio) -> None:
    """Every resolved id must exist in the portfolio the caller is allowed to see."""
    resolved = copilot_service.resolve_projects_by_name(
        "supplier decarbonisation and requirements digitalisation", csv_portfolio
    )
    assert set(resolved) <= set(csv_portfolio.project_ids)
