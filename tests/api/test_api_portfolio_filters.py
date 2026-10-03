"""Portfolio view filters must preserve authoritative calculations and authorization scope."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import url


@pytest.mark.parametrize(
    ("parameter", "field"),
    [
        ("project_id", "project_id"),
        ("health_band", "health_band"),
        ("confidence_band", "confidence_band"),
        ("domain", "domain"),
        ("manager", "project_manager"),
        ("phase", "project_phase"),
        ("priority", "business_priority"),
    ],
)
def test_filters_select_the_same_unmodified_project_results(
    client: TestClient, parameter: str, field: str
) -> None:
    baseline = client.get(url("/analytics/portfolio")).json()
    chosen = baseline["projects"][0][field]
    response = client.get(url("/analytics/portfolio"), params={parameter: chosen})
    assert response.status_code == 200
    filtered = response.json()
    expected = [row for row in baseline["projects"] if row[field] == chosen]
    assert filtered["projects"] == expected
    assert filtered["project_count"] == len(expected)
    assert sum(filtered["health_bands"].values()) == len(expected)
    assert sum(filtered["confidence_bands"].values()) == len(expected)
    assert sum(filtered["alert_severities"].values()) == sum(
        row["open_alert_count"] for row in expected
    )
    visible = {row["project_id"] for row in expected}
    assert all(alert["project_id"] in visible for alert in filtered["top_alerts"])


def test_severity_filter_uses_the_engine_alerts(client: TestClient) -> None:
    alerts = client.get(url("/analytics/alerts"), params={"severity": "Critical"}).json()
    filtered = client.get(url("/analytics/portfolio"), params={"alert_severity": "Critical"}).json()
    assert {row["project_id"] for row in filtered["projects"]} == {
        alert["project_id"] for alert in alerts
    }


def test_combined_filters_do_not_widen_an_empty_selection(client: TestClient) -> None:
    response = client.get(
        url("/analytics/portfolio"),
        params={"project_id": "P-NOT-RECORDED", "health_band": "Red"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["projects"] == []
    assert result["top_alerts"] == []
    assert result["project_count"] == 0
    assert not any(result["alert_severities"].values())


def test_forecast_range_uses_only_recorded_dates(client: TestClient) -> None:
    baseline = client.get(url("/analytics/portfolio")).json()
    dates = [row["forecast_end_date"] for row in baseline["projects"] if row["forecast_end_date"]]
    chosen = dates[0]
    result = client.get(
        url("/analytics/portfolio"),
        params={"forecast_after": chosen, "forecast_before": chosen},
    ).json()
    assert result["projects"] == [
        row for row in baseline["projects"] if row["forecast_end_date"] == chosen
    ]


@pytest.mark.parametrize(
    "filters",
    [
        {"health_band": "invented"},
        {"confidence_band": "invented"},
        {"forecast_after": "2026-12-31", "forecast_before": "2026-01-01"},
    ],
)
def test_invalid_filters_are_refused(client: TestClient, filters: dict[str, str]) -> None:
    assert client.get(url("/analytics/portfolio"), params=filters).status_code == 422


def test_filters_never_expand_the_callers_scope(engineer_client: TestClient) -> None:
    visible = engineer_client.get(url("/analytics/portfolio")).json()["projects"]
    allowed = {row["project_id"] for row in visible}
    for project_id in ("P-002", "P-007", "P-NOT-RECORDED"):
        result = engineer_client.get(
            url("/analytics/portfolio"), params={"project_id": project_id}
        ).json()
        assert {row["project_id"] for row in result["projects"]} <= allowed
