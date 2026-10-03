"""Tests for the Phase 3 shared scoring foundation (config, vocabulary, result models)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from src import scoring_rules as sr
from src.data_loader import PortfolioData, find_status_anomalies
from src.schemas import (
    CriticalDriver,
    DataQualityIssue,
    EarlyWarningAlert,
    HealthResult,
    Milestone,
)
from src.utils import confidence_band, health_band, reference_timestamp


def test_weight_families_sum_to_one() -> None:
    assert round(sum(sr.HEALTH_WEIGHTS.values()), 6) == 1.0
    assert round(sum(sr.CONFIDENCE_WEIGHTS.values()), 6) == 1.0


def test_validate_scoring_config_passes() -> None:
    # Should not raise for the shipped configuration.
    sr.validate_scoring_config()


@pytest.mark.parametrize(
    ("band", "severities", "expected"),
    [
        ("Green", [], False),
        ("Green", ["Medium", "Low"], False),
        ("Green", ["High"], False),
        ("Green", ["Critical"], True),
        ("Amber", [], True),
        ("Red", ["Low"], True),
    ],
)
def test_needs_attention_is_one_shared_rule(
    band: str, severities: list[str], expected: bool
) -> None:
    assert sr.needs_attention(band, severities) is expected


def test_factor_keys_match_weight_keys() -> None:
    assert set(sr.HEALTH_WEIGHTS) == set(sr.HEALTH_FACTORS)
    assert set(sr.CONFIDENCE_WEIGHTS) == set(sr.CONFIDENCE_FACTORS)


def test_criticality_penalty_tables_cover_all_levels() -> None:
    for penalties in (
        sr.MILESTONE_SLIP_PENALTY,
        sr.DEPENDENCY_DELAY_PENALTY,
        sr.ACTION_OVERDUE_PENALTY,
    ):
        assert set(penalties) == set(sr.CRITICALITY_LEVELS)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100.0, "Green"),
        (80.0, "Green"),
        (79.99, "Amber"),
        (60.0, "Amber"),
        (59.99, "Red"),
        (0.0, "Red"),
    ],
)
def test_health_band_boundaries(score: float, expected: str) -> None:
    assert health_band(score) == expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [(80.0, "High"), (79.99, "Medium"), (60.0, "Medium"), (59.99, "Low")],
)
def test_confidence_band_boundaries(score: float, expected: str) -> None:
    assert confidence_band(score) == expected


@pytest.mark.parametrize(
    ("raw", "domain", "expected"),
    [
        ("Completed", sr.StatusDomain.SCHEDULE, "Complete"),
        (" completed ", sr.StatusDomain.SCHEDULE, "Complete"),
        ("in progress", sr.StatusDomain.SCHEDULE, "In Progress"),
        ("At Risk", sr.StatusDomain.SCHEDULE, "At Risk"),
        ("Open", sr.StatusDomain.RISK, "Open"),
        ("Blocked", sr.StatusDomain.ACTION, "Blocked"),
        ("Completed", sr.StatusDomain.ACTION, "Complete"),
        ("Not Run", sr.StatusDomain.TEST_CASE, "Not Run"),
        ("nonsense", sr.StatusDomain.SCHEDULE, None),
        (None, sr.StatusDomain.SCHEDULE, None),
        ("", sr.StatusDomain.SCHEDULE, None),
    ],
)
def test_normalize_status(raw: str | None, domain: sr.StatusDomain, expected: str | None) -> None:
    assert sr.normalize_status(raw, domain) == expected


def test_is_known_and_terminal_status() -> None:
    assert sr.is_known_status("Completed", sr.StatusDomain.SCHEDULE) is True
    assert sr.is_known_status("nonsense", sr.StatusDomain.SCHEDULE) is False
    assert sr.is_terminal_schedule_status("Completed") is True
    assert sr.is_terminal_schedule_status("In Progress") is False


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [
        (0, sr.FRESHNESS_FRESH),
        (7, sr.FRESHNESS_FRESH),
        (8, sr.FRESHNESS_STALE),
        (14, sr.FRESHNESS_STALE),
        (15, sr.FRESHNESS_SIGNIFICANTLY_STALE),
        (21, sr.FRESHNESS_SIGNIFICANTLY_STALE),
        (22, sr.FRESHNESS_CRITICALLY_STALE),
    ],
)
def test_classify_freshness(age_days: int, expected: str) -> None:
    assert sr.classify_freshness(age_days) == expected


def test_reference_timestamp_is_midnight_utc() -> None:
    assert reference_timestamp(date(2026, 8, 25)) == datetime(2026, 8, 25, tzinfo=UTC)


def test_result_models_accept_valid_payloads() -> None:
    driver = CriticalDriver(
        factor_name="risk_exposure",
        severity="Critical",
        message="Risk R-2001 has probability 4 and impact 5 (exposure 20/25) with no owner.",
        source_ids=["R-2001"],
        score_impact_description="Reduced risk exposure factor by 30 points.",
    )
    issue = DataQualityIssue(
        issue_type="stale_status",
        severity="High",
        message="Project P-007 status is 51 days old.",
        source_ids=["P-007"],
        remediation_hint="Request an updated project status.",
    )
    result = HealthResult(
        project_id="P-002",
        overall_score=42.5,
        health_band="Red",
        factor_scores={"schedule_performance": 25.0},
        factor_weights=dict(sr.HEALTH_WEIGHTS),
        factor_explanations={"schedule_performance": ["Forecast is 77 days later than baseline."]},
        critical_drivers=[driver],
        source_ids=["P-002", "R-2001"],
        as_of_date=date(2026, 8, 25),
        calculated_at=reference_timestamp(date(2026, 8, 25)),
        assumptions_or_limitations=["Calendar-day variance used for schedule performance."],
    )
    assert result.health_band == "Red"
    assert result.critical_drivers[0].source_ids == ["R-2001"]
    assert issue.severity == "High"


def test_health_band_literal_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        HealthResult(
            project_id="P-002",
            overall_score=10.0,
            health_band="Purple",
            factor_scores={},
            factor_weights={},
            factor_explanations={},
            critical_drivers=[],
            source_ids=[],
            as_of_date=date(2026, 8, 25),
            calculated_at=reference_timestamp(date(2026, 8, 25)),
            assumptions_or_limitations=[],
        )


def test_early_warning_alert_rejects_invalid_severity() -> None:
    with pytest.raises(ValidationError):
        EarlyWarningAlert(
            alert_id="A1",
            project_id="P-002",
            severity="Severe",
            alert_type="unowned_risk",
            title="x",
            explanation="x",
            source_ids=["R-2001"],
            recommended_next_step="x",
            as_of_date=date(2026, 8, 25),
            detected_at=reference_timestamp(date(2026, 8, 25)),
        )


def test_real_portfolio_has_no_status_anomalies(portfolio: PortfolioData) -> None:
    assert portfolio.status_anomalies == []


def test_find_status_anomalies_detects_unknown_value() -> None:
    milestone = Milestone(
        milestone_id="M-X",
        project_id="P-002",
        milestone_name="Bad status milestone",
        baseline_date="2026-01-01",
        forecast_date="2026-01-01",
        status="Wobbling",
        criticality="High",
        owner="Someone",
    )
    portfolio = PortfolioData(milestones=[milestone])
    anomalies = find_status_anomalies(portfolio)
    assert any("M-X" in issue and "Wobbling" in issue for issue in anomalies)
