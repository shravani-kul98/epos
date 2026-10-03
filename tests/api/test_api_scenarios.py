"""Scenario simulation endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.scoring_rules import SCENARIO_MAX_DELAY_DAYS, SCENARIO_MIN_DELAY_DAYS
from tests.api.conftest import url

DELAY_SCENARIO = {"dependency_id": "D-7002", "additional_delay_days": 30}


def test_dependencies_are_listed_for_simulation(client: TestClient) -> None:
    dependencies = client.get(url("/scenarios/dependencies")).json()
    assert {dependency["dependency_id"] for dependency in dependencies} >= {"D-7002", "D-2002"}


def test_scenario_reproduces_known_health_change(client: TestClient) -> None:
    payload = client.post(url("/scenarios/dependency-delay"), json=DELAY_SCENARIO).json()
    comparison = next(c for c in payload["affected_projects"] if c["project_id"] == "P-007")
    assert comparison["baseline_health_score"] == 51.15
    assert comparison["scenario_health_score"] == 48.35


def test_scenario_reproduces_known_alert_growth(client: TestClient) -> None:
    payload = client.post(url("/scenarios/dependency-delay"), json=DELAY_SCENARIO).json()
    comparison = next(c for c in payload["affected_projects"] if c["project_id"] == "P-007")
    assert sum(comparison["baseline_alert_counts"].values()) == 9
    assert sum(comparison["scenario_alert_counts"].values()) == 11
    assert comparison["changed_alert_ids"] == []


def test_second_known_scenario_reproduces_its_health_change(client: TestClient) -> None:
    payload = client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-2002", "additional_delay_days": 30},
    ).json()
    comparison = next(c for c in payload["affected_projects"] if c["project_id"] == "P-002")
    assert comparison["baseline_health_score"] == 49.9
    # Added delay never improves health, even where a task factor rises past a date threshold.
    assert comparison["scenario_health_score"] == 49.4


def test_scenario_resolves_the_dependency_name(client: TestClient) -> None:
    payload = client.post(url("/scenarios/dependency-delay"), json=DELAY_SCENARIO).json()
    assert payload["dependency_name"]
    assert payload["dependency_name"] != payload["dependency_id"]


def test_scenario_reports_the_delay_arithmetic(client: TestClient) -> None:
    payload = client.post(url("/scenarios/dependency-delay"), json=DELAY_SCENARIO).json()
    assert payload["scenario_delay_days"] == payload["baseline_delay_days"] + 30


def test_minimum_delay_is_enforced_from_the_engine_bounds(client: TestClient) -> None:
    """The API must not accept a delay the scenario engine would reject."""
    response = client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-7002", "additional_delay_days": SCENARIO_MIN_DELAY_DAYS - 1},
    )
    assert response.status_code == 422


def test_smallest_permitted_delay_is_accepted(client: TestClient) -> None:
    response = client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-7002", "additional_delay_days": SCENARIO_MIN_DELAY_DAYS},
    )
    assert response.status_code == 200


def test_largest_permitted_delay_is_accepted(client: TestClient) -> None:
    response = client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-7002", "additional_delay_days": SCENARIO_MAX_DELAY_DAYS},
    )
    assert response.status_code == 200


def test_scenario_does_not_mutate_stored_data(client: TestClient) -> None:
    """A what-if must never write to the database."""
    before = client.get(url("/projects/P-007/dependencies")).json()
    client.post(url("/scenarios/dependency-delay"), json=DELAY_SCENARIO)
    after = client.get(url("/projects/P-007/dependencies")).json()
    assert after == before


def test_scenario_does_not_change_the_stored_health_score(client: TestClient) -> None:
    before = client.get(url("/analytics/projects/P-007/health")).json()["score"]
    client.post(url("/scenarios/dependency-delay"), json=DELAY_SCENARIO)
    after = client.get(url("/analytics/projects/P-007/health")).json()["score"]
    assert after == before


def test_scenario_writes_no_activity_events(client: TestClient) -> None:
    client.post(url("/scenarios/dependency-delay"), json=DELAY_SCENARIO)
    assert client.get(url("/activity")).json() == []


def test_unknown_dependency_is_rejected(client: TestClient) -> None:
    response = client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-0000", "additional_delay_days": 10},
    )
    assert response.status_code == 422


def test_negative_delay_is_rejected(client: TestClient) -> None:
    response = client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-7002", "additional_delay_days": -1},
    )
    assert response.status_code == 422


def test_excessive_delay_is_rejected(client: TestClient) -> None:
    response = client.post(
        url("/scenarios/dependency-delay"),
        json={"dependency_id": "D-7002", "additional_delay_days": SCENARIO_MAX_DELAY_DAYS + 1},
    )
    assert response.status_code == 422


def test_scenario_carries_evidence_and_limitations(client: TestClient) -> None:
    payload = client.post(url("/scenarios/dependency-delay"), json=DELAY_SCENARIO).json()
    assert payload["source_ids"]
    assert payload["assumptions_or_limitations"]


class TestMultiEventEndpoint:
    def test_a_multi_event_scenario_returns_every_intervention(self, client: TestClient) -> None:
        payload = client.post(
            url("/scenarios/run"),
            json={
                "interventions": [
                    {"intervention_type": "dependency_delay", "target_id": "D-7002", "value": 30},
                    {"intervention_type": "task_delay", "target_id": "T-7001", "value": 10},
                ]
            },
        )
        assert payload.status_code == 200
        body = payload.json()
        assert {item["target_id"] for item in body["interventions"]} == {"D-7002", "T-7001"}
        assert body["calculation_version"]

    def test_every_movement_names_its_record_and_controlling_link(self, client: TestClient) -> None:
        body = client.post(
            url("/scenarios/run"),
            json={
                "interventions": [
                    {"intervention_type": "dependency_delay", "target_id": "D-7002", "value": 90}
                ]
            },
        ).json()
        for movement in body["schedule_movements"]:
            assert movement["record_name"]
            assert movement["shift_days"] > 0
            assert movement["scenario_date"] > movement["original_date"]

    def test_an_unknown_target_is_refused(self, client: TestClient) -> None:
        response = client.post(
            url("/scenarios/run"),
            json={
                "interventions": [
                    {"intervention_type": "task_delay", "target_id": "T-NOPE", "value": 5}
                ]
            },
        )
        assert response.status_code == 422

    def test_conflicting_interventions_are_refused(self, client: TestClient) -> None:
        response = client.post(
            url("/scenarios/run"),
            json={
                "interventions": [
                    {"intervention_type": "task_delay", "target_id": "T-7001", "value": 5},
                    {"intervention_type": "task_delay", "target_id": "T-7001", "value": 9},
                ]
            },
        )
        assert response.status_code == 422


class TestSensitivityEndpoint:
    def test_sensitivity_reports_a_tested_response_curve(self, client: TestClient) -> None:
        body = client.post(
            url("/scenarios/sensitivity"),
            json={"intervention_type": "dependency_delay", "target_id": "D-7002"},
        ).json()
        assert len(body["tested_values"]) == len(body["health_scores"])
        assert body["thresholds"]
        for threshold in body["thresholds"]:
            if threshold["occurs_at_value"] is not None:
                assert threshold["occurs_at_value"] in body["tested_values"]

    def test_scenario_routes_require_the_scenario_permission(
        self, engineer_client: TestClient
    ) -> None:
        for path, payload in (
            (
                "/scenarios/run",
                {
                    "interventions": [
                        {"intervention_type": "task_delay", "target_id": "T-7001", "value": 5}
                    ]
                },
            ),
            (
                "/scenarios/sensitivity",
                {"intervention_type": "dependency_delay", "target_id": "D-7002"},
            ),
            (
                "/scenarios/explain",
                {"dependency_id": "D-7002", "additional_delay_days": 5},
            ),
        ):
            assert engineer_client.post(url(path), json=payload).status_code == 403
