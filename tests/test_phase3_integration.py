"""Phase 3 integration tests: Health, Confidence and Risk engines together on real data.

These exercise the three deterministic engines against the real synthetic portfolio loaded by
the production loader, verifying cross-engine consistency, project scoping, no mutation and full
determinism. No engine logic is defined here; only the public functions are called.
"""

from __future__ import annotations

import copy
from datetime import date

import pytest

from src.confidence_engine import calculate_portfolio_confidence, calculate_project_confidence
from src.data_loader import PortfolioData, load_portfolio
from src.health_engine import calculate_project_health
from src.risk_engine import generate_early_warnings, generate_portfolio_early_warnings
from src.validators import DataValidationError

AS_OF_DATE = date(2026, 8, 25)
PROJECT_IDS = ("P-002", "P-007")

# Regression snapshot of the real engines on the real synthetic data as of AS_OF_DATE.
EXPECTED = {
    "P-002": {
        "health_score": 49.9,
        "health_band": "Red",
        "confidence_score": 82.0,
        "confidence_band": "High",
        "alert_count": 7,
        "severity_counts": {"Critical": 5, "High": 2},
    },
    "P-007": {
        "health_score": 51.15,
        "health_band": "Red",
        "confidence_score": 68.0,
        "confidence_band": "Medium",
        "alert_count": 9,
        "severity_counts": {"Critical": 4, "High": 4, "Medium": 1},
    },
}


def _project_id_universe(portfolio: PortfolioData, project_id: str) -> set[str]:
    """All record IDs that belong to a project (the only IDs its results may reference)."""
    universe = {project_id}
    universe |= {m.milestone_id for m in portfolio.milestones if m.project_id == project_id}
    universe |= {t.task_id for t in portfolio.tasks if t.project_id == project_id}
    universe |= {r.risk_id for r in portfolio.risks if r.project_id == project_id}
    universe |= {d.dependency_id for d in portfolio.dependencies if d.project_id == project_id}
    universe |= {r.resource_id for r in portfolio.resources if r.project_id == project_id}
    universe |= {a.action_id for a in portfolio.actions if a.project_id == project_id}
    universe |= {r.requirement_id for r in portfolio.requirements if r.project_id == project_id}
    universe |= {t.test_case_id for t in portfolio.test_cases if t.project_id == project_id}
    universe |= {
        link.trace_link_id for link in portfolio.trace_links if link.project_id == project_id
    }
    universe |= {
        c.change_request_id for c in portfolio.change_requests if c.project_id == project_id
    }
    return universe


def _severity_counts(alerts) -> dict[str, int]:
    counts: dict[str, int] = {}
    for alert in alerts:
        counts[alert.severity] = counts.get(alert.severity, 0) + 1
    return counts


def _alert_source_ids(alerts) -> set[str]:
    return {sid for alert in alerts for sid in alert.source_ids}


# ------------------------------------------------------------------------ 1. load
def test_full_portfolio_load_succeeds(portfolio):
    assert set(PROJECT_IDS) <= portfolio.project_ids
    assert portfolio.status_anomalies == []


# --------------------------------------------------------------- 2. all engines run
@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_all_engines_return_valid_results(portfolio, project_id):
    health = calculate_project_health(project_id, portfolio, AS_OF_DATE)
    confidence = calculate_project_confidence(project_id, portfolio, AS_OF_DATE)
    alerts = generate_early_warnings(project_id, portfolio, AS_OF_DATE)

    assert health.health_band in ("Green", "Amber", "Red")
    assert len(health.factor_scores) == 7
    assert 0.0 <= health.overall_score <= 100.0
    assert confidence.confidence_band in ("High", "Medium", "Low")
    assert len(confidence.factor_scores) == 4
    assert 0.0 <= confidence.overall_score <= 100.0
    for alert in alerts:
        assert alert.alert_id and alert.project_id == project_id
        assert alert.severity in ("Low", "Medium", "High", "Critical")
        assert alert.source_ids


# ------------------------------------------------------------ 3. project-scope isolation
@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_source_ids_are_project_scoped_and_real(portfolio, project_id):
    universe = _project_id_universe(portfolio, project_id)
    other = next(p for p in PROJECT_IDS if p != project_id)
    other_universe = _project_id_universe(portfolio, other)

    health = calculate_project_health(project_id, portfolio, AS_OF_DATE)
    confidence = calculate_project_confidence(project_id, portfolio, AS_OF_DATE)
    alerts = generate_early_warnings(project_id, portfolio, AS_OF_DATE)

    used = set(health.source_ids) | set(confidence.source_ids) | _alert_source_ids(alerts)
    assert used <= universe
    assert used.isdisjoint(other_universe - universe)


# ------------------------------------------------------- 4. known signals, correct project
def test_known_adverse_signals_are_project_specific(portfolio):
    p002 = generate_early_warnings("P-002", portfolio, AS_OF_DATE)
    p007 = generate_early_warnings("P-007", portfolio, AS_OF_DATE)
    types_002 = {a.alert_type for a in p002}
    types_007 = {a.alert_type for a in p007}

    # Unowned high-exposure risks are isolated to their own project.
    assert "R-2001" in _alert_source_ids(p002)
    assert "R-2001" not in _alert_source_ids(p007)
    assert "R-7001" in _alert_source_ids(p007)
    assert "R-7001" not in _alert_source_ids(p002)

    # Supplier delayed-dependency alert only in P-002.
    assert "milestone_delayed_dependency" in types_002
    assert "milestone_delayed_dependency" not in types_007

    # Stale status and missing-verification only in P-007.
    assert "stale_project_status" in types_007
    assert "stale_project_status" not in types_002
    assert "requirement_missing_verification" in types_007
    assert "requirement_missing_verification" not in types_002


# ----------------------------------------------------------- 5. distinct, realistic outcomes
def test_projects_produce_distinct_non_perfect_outcomes(portfolio):
    h002 = calculate_project_health("P-002", portfolio, AS_OF_DATE)
    h007 = calculate_project_health("P-007", portfolio, AS_OF_DATE)
    c002 = calculate_project_confidence("P-002", portfolio, AS_OF_DATE)
    c007 = calculate_project_confidence("P-007", portfolio, AS_OF_DATE)
    a002 = generate_early_warnings("P-002", portfolio, AS_OF_DATE)
    a007 = generate_early_warnings("P-007", portfolio, AS_OF_DATE)

    assert h002.overall_score != h007.overall_score
    assert c002.overall_score != c007.overall_score
    assert {a.alert_id for a in a002} != {a.alert_id for a in a007}

    for health, confidence in ((h002, c002), (h007, c007)):
        assert health.overall_score < 100.0
        assert confidence.overall_score < 100.0


# --------------------------------------------------- 6. Health vs Confidence independence
def test_health_and_confidence_are_independent(portfolio):
    c002 = calculate_project_confidence("P-002", portfolio, AS_OF_DATE)
    c007 = calculate_project_confidence("P-007", portfolio, AS_OF_DATE)
    h002 = calculate_project_health("P-002", portfolio, AS_OF_DATE)
    h007 = calculate_project_health("P-007", portfolio, AS_OF_DATE)

    # Both projects are Red on Health, yet their Confidence differs, proving independence.
    assert h002.health_band == "Red" and h007.health_band == "Red"
    assert c002.confidence_band != c007.confidence_band
    assert c002.factor_scores["data_freshness"] != c007.factor_scores["data_freshness"]


# ------------------------------------------------------------------ 7. no mutation
def test_no_mutation_across_full_run():
    portfolio = load_portfolio()
    snapshot = copy.deepcopy(portfolio)
    for project_id in PROJECT_IDS:
        calculate_project_health(project_id, portfolio, AS_OF_DATE)
        calculate_project_confidence(project_id, portfolio, AS_OF_DATE)
        generate_early_warnings(project_id, portfolio, AS_OF_DATE)

    for attr in (
        "projects",
        "milestones",
        "tasks",
        "risks",
        "dependencies",
        "actions",
        "resources",
        "requirements",
        "test_cases",
        "trace_links",
        "change_requests",
    ):
        after = [r.model_dump() for r in getattr(portfolio, attr)]
        before = [r.model_dump() for r in getattr(snapshot, attr)]
        assert after == before


# --------------------------------------------- 8. Critical alert implies non-Green health
@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_critical_alert_implies_not_green(portfolio, project_id):
    alerts = generate_early_warnings(project_id, portfolio, AS_OF_DATE)
    health = calculate_project_health(project_id, portfolio, AS_OF_DATE)
    if any(a.severity == "Critical" for a in alerts):
        assert health.health_band != "Green"


# ------------------------------------------------------------------ 9. determinism
def test_repeated_execution_is_deterministic():
    first = load_portfolio()
    second = load_portfolio()
    for project_id in PROJECT_IDS:
        h1 = calculate_project_health(project_id, first, AS_OF_DATE)
        h2 = calculate_project_health(project_id, second, AS_OF_DATE)
        c1 = calculate_project_confidence(project_id, first, AS_OF_DATE)
        c2 = calculate_project_confidence(project_id, second, AS_OF_DATE)
        a1 = generate_early_warnings(project_id, first, AS_OF_DATE)
        a2 = generate_early_warnings(project_id, second, AS_OF_DATE)

        assert h1.model_dump() == h2.model_dump()
        assert c1.model_dump() == c2.model_dump()
        assert [a.model_dump() for a in a1] == [a.model_dump() for a in a2]


# ------------------------------------------------------- 10. portfolio-level aggregation
def test_portfolio_level_functions_match_project_level(portfolio):
    """Aggregation must cover every project and agree with the per-project calculation."""
    project_ids = set(portfolio.project_ids)
    confidences = {c.project_id: c for c in calculate_portfolio_confidence(portfolio, AS_OF_DATE)}
    assert set(confidences) == project_ids
    for project_id in project_ids:
        direct = calculate_project_confidence(project_id, portfolio, AS_OF_DATE)
        assert confidences[project_id].model_dump() == direct.model_dump()

    portfolio_alerts = generate_portfolio_early_warnings(portfolio, AS_OF_DATE)
    per_project_ids = set()
    for project_id in project_ids:
        per_project_ids |= {
            a.alert_id for a in generate_early_warnings(project_id, portfolio, AS_OF_DATE)
        }
    assert {a.alert_id for a in portfolio_alerts} == per_project_ids


# ------------------------------------------------------- 11. consistent unknown-project error
def test_unknown_project_raises_consistently(portfolio):
    for func in (
        calculate_project_health,
        calculate_project_confidence,
        generate_early_warnings,
    ):
        with pytest.raises(DataValidationError) as exc:
            func("P-NONE", portfolio, AS_OF_DATE)
        assert "P-NONE" in str(exc.value)


# ------------------------------------------------------------ regression snapshot
@pytest.mark.parametrize("project_id", PROJECT_IDS)
def test_regression_snapshot(portfolio, project_id):
    expected = EXPECTED[project_id]
    health = calculate_project_health(project_id, portfolio, AS_OF_DATE)
    confidence = calculate_project_confidence(project_id, portfolio, AS_OF_DATE)
    alerts = generate_early_warnings(project_id, portfolio, AS_OF_DATE)

    assert health.overall_score == expected["health_score"]
    assert health.health_band == expected["health_band"]
    assert confidence.overall_score == expected["confidence_score"]
    assert confidence.confidence_band == expected["confidence_band"]
    assert len(alerts) == expected["alert_count"]
    assert _severity_counts(alerts) == expected["severity_counts"]
