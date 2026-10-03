"""Analytics endpoint tests, asserting the engines' known ground-truth values."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.labels import HEALTH_FACTOR_LABELS
from api.services import analytics_service
from src.scoring_rules import CONFIDENCE_FACTORS, HEALTH_FACTORS
from tests.api.conftest import ANALYSIS_DATE_ISO, url


# ------------------------------------------------------------------ portfolio dashboard
def test_portfolio_dashboard_returns_every_project(client: TestClient, csv_portfolio) -> None:
    """Checked against the loaded workspace, so the assertion survives the data growing."""
    payload = client.get(url("/analytics/portfolio")).json()
    assert payload["project_count"] == len(csv_portfolio.projects)
    assert {row["project_id"] for row in payload["projects"]} == set(csv_portfolio.project_ids)


def test_portfolio_dashboard_reports_project_calculation_failure(
    client: TestClient,
    csv_portfolio,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_project_id = csv_portfolio.projects[0].project_id
    original = analytics_service.calculate_project_health

    def calculate_or_fail(project_id, portfolio, as_of_date):
        if project_id == failed_project_id:
            raise RuntimeError("synthetic calculation failure")
        return original(project_id, portfolio, as_of_date)

    monkeypatch.setattr(analytics_service, "calculate_project_health", calculate_or_fail)

    response = client.get(url("/analytics/portfolio"))

    assert response.status_code == 503
    assert failed_project_id in response.json()["detail"]


def test_portfolio_dashboard_uses_the_explicit_test_clock(client: TestClient) -> None:
    assert client.get(url("/analytics/portfolio")).json()["as_of_date"] == ANALYSIS_DATE_ISO


@pytest.mark.parametrize("today", [date(2026, 9, 22), date(2026, 9, 23)])
def test_default_analysis_date_and_health_follow_the_utc_clock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, today: date
) -> None:
    monkeypatch.setattr("api.clock.utc_today", lambda: today)
    dashboard = client.get(url("/analytics/portfolio"))
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["as_of_date"] == today.isoformat()
    assert client.get(url("/health")).json()["analysis_date"] == today.isoformat()


def test_portfolio_alert_tally_matches_the_alerts_endpoint(client: TestClient) -> None:
    """The dashboard tally and the alert list must not disagree about how many exist."""
    severities = client.get(url("/analytics/portfolio")).json()["alert_severities"]
    alerts = client.get(url("/analytics/alerts")).json()
    assert sum(severities.values()) == len(alerts)


def test_portfolio_health_bands_account_for_every_project(client: TestClient) -> None:
    payload = client.get(url("/analytics/portfolio")).json()
    bands = payload["health_bands"]
    assert set(bands) == {"green", "amber", "red"}
    assert sum(bands.values()) == payload["project_count"]


def test_health_band_tallies_match_the_project_rows(client: TestClient) -> None:
    """A tally that disagreed with the rows beneath it would mislead silently."""
    payload = client.get(url("/analytics/portfolio")).json()
    counted = {"green": 0, "amber": 0, "red": 0}
    for row in payload["projects"]:
        counted[row["health_band"].lower()] += 1
    assert payload["health_bands"] == counted


def test_portfolio_projects_are_ordered_worst_first(client: TestClient) -> None:
    payload = client.get(url("/analytics/portfolio")).json()
    scores = [row["health_score"] for row in payload["projects"]]
    assert scores == sorted(scores)


def test_portfolio_dashboard_tallies_confidence_bands(client: TestClient) -> None:
    payload = client.get(url("/analytics/portfolio")).json()
    bands = payload["confidence_bands"]
    assert set(bands) == {"high", "medium", "low"}
    assert sum(bands.values()) == payload["project_count"]


def test_portfolio_dashboard_tallies_stored_phases_and_domains(client: TestClient) -> None:
    payload = client.get(url("/analytics/portfolio")).json()

    for field, row_field in (
        ("project_phases", "project_phase"),
        ("project_domains", "domain"),
    ):
        counted: dict[str, int] = {}
        for row in payload["projects"]:
            value = row[row_field]
            counted[value] = counted.get(value, 0) + 1
        assert payload[field] == dict(sorted(counted.items()))
        assert sum(payload[field].values()) == payload["project_count"]


def test_portfolio_dashboard_invents_no_aggregate_score(client: TestClient) -> None:
    """Only engine-produced bands are tallied; no portfolio-level score is fabricated."""
    payload = client.get(url("/analytics/portfolio")).json()
    assert "average_health_score" not in payload
    assert "portfolio_confidence_score" not in payload


def test_portfolio_dashboard_on_empty_database_is_safe(empty_client: TestClient) -> None:
    payload = empty_client.get(url("/analytics/portfolio")).json()
    assert payload["project_count"] == 0
    assert payload["projects"] == []
    assert payload["health_bands"] == {"green": 0, "amber": 0, "red": 0}
    assert payload["project_phases"] == {}
    assert payload["project_domains"] == {}


# ------------------------------------------------------------------ project dashboard
def test_project_dashboard_matches_known_health_and_confidence(client: TestClient) -> None:
    payload = client.get(url("/analytics/projects/P-002")).json()
    assert payload["health"]["score"] == 49.9
    assert payload["health"]["band"] == "Red"
    assert payload["confidence"]["score"] == 82.0
    assert payload["confidence"]["band"] == "High"


def test_project_dashboard_returns_the_known_alert_count(client: TestClient) -> None:
    alerts = client.get(url("/analytics/projects/P-007")).json()["alerts"]
    assert len(alerts) == 9
    assert sum(1 for alert in alerts if alert["severity"] == "Critical") == 4


def test_project_dashboard_for_unknown_project_returns_404(client: TestClient) -> None:
    response = client.get(url("/analytics/projects/P-000"))
    assert response.status_code == 404
    assert "P-000" in response.json()["detail"]


def test_project_health_endpoint_matches_dashboard(client: TestClient) -> None:
    dashboard = client.get(url("/analytics/projects/P-007")).json()["health"]
    direct = client.get(url("/analytics/projects/P-007/health")).json()
    assert direct["score"] == dashboard["score"]


def test_project_confidence_endpoint_matches_dashboard(client: TestClient) -> None:
    dashboard = client.get(url("/analytics/projects/P-007")).json()["confidence"]
    direct = client.get(url("/analytics/projects/P-007/confidence")).json()
    assert direct["score"] == dashboard["score"]


def test_health_response_covers_every_engine_factor(client: TestClient) -> None:
    factors = client.get(url("/analytics/projects/P-002/health")).json()["factors"]
    assert {factor["key"] for factor in factors} == set(HEALTH_FACTORS)


def test_confidence_response_covers_every_engine_factor(client: TestClient) -> None:
    factors = client.get(url("/analytics/projects/P-002/confidence")).json()["factors"]
    assert {factor["key"] for factor in factors} == set(CONFIDENCE_FACTORS)


def test_factors_are_ordered_weakest_first(client: TestClient) -> None:
    factors = client.get(url("/analytics/projects/P-002/health")).json()["factors"]
    scores = [factor["score"] for factor in factors]
    assert scores == sorted(scores)


def test_weighted_contribution_is_score_times_weight(client: TestClient) -> None:
    for factor in client.get(url("/analytics/projects/P-002/health")).json()["factors"]:
        assert factor["weighted_contribution"] == round(factor["score"] * factor["weight"], 2)


def test_health_carries_evidence_source_ids(client: TestClient) -> None:
    assert client.get(url("/analytics/projects/P-002/health")).json()["source_ids"]


def test_critical_drivers_use_display_labels(client: TestClient) -> None:
    drivers = client.get(url("/analytics/projects/P-002/health")).json()["critical_drivers"]
    for driver in drivers:
        assert driver["factor_label"] in HEALTH_FACTOR_LABELS.values()


def test_analysis_date_can_be_overridden(client: TestClient) -> None:
    payload = client.get(url("/analytics/portfolio"), params={"as_of_date": "2026-09-30"}).json()
    assert payload["as_of_date"] == "2026-09-30"


def test_a_later_analysis_date_changes_the_result(client: TestClient) -> None:
    baseline = client.get(url("/analytics/projects/P-002/health")).json()["score"]
    later = client.get(
        url("/analytics/projects/P-002/health"), params={"as_of_date": "2027-06-30"}
    ).json()["score"]
    assert later != baseline


def test_invalid_analysis_date_is_rejected(client: TestClient) -> None:
    response = client.get(url("/analytics/portfolio"), params={"as_of_date": "not-a-date"})
    assert response.status_code == 422


def test_analysis_date_before_recorded_evidence_is_rejected(client: TestClient) -> None:
    response = client.get(
        url("/analytics/projects/P-002/confidence"),
        params={"as_of_date": "2025-01-01"},
    )

    assert response.status_code == 422
    assert "P-002" in response.json()["detail"]


# ------------------------------------------------------------------ alerts
def test_project_alert_filters_partition_the_portfolio(client: TestClient, csv_portfolio) -> None:
    """Filtering by each project in turn must account for every alert exactly once."""
    everything = client.get(url("/analytics/alerts")).json()
    per_project = 0
    for project_id in csv_portfolio.project_ids:
        alerts = client.get(url("/analytics/alerts"), params={"project_id": project_id}).json()
        assert {alert["project_id"] for alert in alerts} <= {project_id}
        per_project += len(alerts)
    assert per_project == len(everything)


def test_alerts_can_be_filtered_by_project(client: TestClient) -> None:
    alerts = client.get(url("/analytics/alerts"), params={"project_id": "P-002"}).json()
    assert alerts
    assert {alert["project_id"] for alert in alerts} == {"P-002"}


def test_alerts_can_be_filtered_by_severity(client: TestClient) -> None:
    alerts = client.get(url("/analytics/alerts"), params={"severity": "Critical"}).json()
    assert alerts
    assert {alert["severity"] for alert in alerts} == {"Critical"}


def test_alerts_for_unknown_project_return_404(client: TestClient) -> None:
    assert client.get(url("/analytics/alerts"), params={"project_id": "P-000"}).status_code == 404


def test_every_alert_carries_evidence_and_a_next_step(client: TestClient) -> None:
    for alert in client.get(url("/analytics/alerts")).json():
        assert alert["source_ids"]
        assert alert["recommended_next_step"].strip()


# ------------------------------------------------------------------ traceability
def test_traceability_covers_every_requirement(client: TestClient, csv_portfolio) -> None:
    payload = client.get(url("/analytics/traceability")).json()
    assert payload["total_requirements"] == len(csv_portfolio.requirements)
    assert len(payload["rows"]) == len(csv_portfolio.requirements)


def test_traceability_can_be_scoped_to_one_project(client: TestClient) -> None:
    payload = client.get(url("/analytics/traceability"), params={"project_id": "P-002"}).json()
    assert payload["project_id"] == "P-002"
    assert {row["project_id"] for row in payload["rows"]} == {"P-002"}


def test_traceability_status_counts_sum_to_the_row_count(client: TestClient) -> None:
    payload = client.get(url("/analytics/traceability")).json()
    assert sum(payload["status_counts"].values()) == payload["total_requirements"]


def test_traceability_coverage_is_a_percentage(client: TestClient) -> None:
    assert 0.0 <= client.get(url("/analytics/traceability")).json()["coverage_percent"] <= 100.0


def test_verified_requirements_have_linked_tests(client: TestClient) -> None:
    for row in client.get(url("/analytics/traceability")).json()["rows"]:
        if row["trace_status"] == "Verified":
            assert row["verified_test_case_ids"]


def test_unlinked_requirements_have_no_tests(client: TestClient) -> None:
    for row in client.get(url("/analytics/traceability")).json()["rows"]:
        if row["trace_status"] == "No linked test case":
            assert row["linked_test_case_ids"] == []


def test_traceability_on_empty_database_is_safe(empty_client: TestClient) -> None:
    payload = empty_client.get(url("/analytics/traceability")).json()
    assert payload["total_requirements"] == 0
    assert payload["coverage_percent"] == 0.0
