"""Ask EPOS may route a scenario, but only the deterministic engine calculates it."""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from api.services import analytics_service, copilot_scenarios, semantic_router
from src.ui_formatting import ANALYSIS_DATE
from tests.api.conftest import url

DEPENDENCY = "D-2001"
DELAY = 10


class TestScenarioAnswer:
    def test_the_answer_matches_the_deterministic_engine(self, csv_portfolio) -> None:
        expected = analytics_service.run_scenario(DEPENDENCY, DELAY, csv_portfolio, ANALYSIS_DATE)

        result = copilot_scenarios.answer(
            DEPENDENCY, DELAY, csv_portfolio, ANALYSIS_DATE, allowed=True
        )

        assert result.status == "ok"
        assert result.executive_summary == expected.explanation
        assert result.source_ids == [f"SCENARIO-{DEPENDENCY}-{DELAY}D", *expected.source_ids]
        assert len(result.key_findings) == len(expected.decision_brief)
        for insight, finding in zip(expected.decision_brief, result.key_findings, strict=True):
            assert insight.headline in finding
            assert insight.detail in finding
            assert all(source_id in finding for source_id in insight.source_ids)
        assert result.human_review_required is False

    def test_every_scenario_source_has_visible_evidence(self, csv_portfolio) -> None:
        result = copilot_scenarios.answer(
            DEPENDENCY, DELAY, csv_portfolio, ANALYSIS_DATE, allowed=True
        )

        assert set(result.source_ids) == {record.record_id for record in result.evidence}

    def test_the_scenario_does_not_mutate_the_portfolio(self, csv_portfolio) -> None:
        before = copy.deepcopy(csv_portfolio)

        copilot_scenarios.answer(DEPENDENCY, DELAY, csv_portfolio, ANALYSIS_DATE, allowed=True)

        for collection in (
            "projects",
            "milestones",
            "tasks",
            "risks",
            "dependencies",
            "actions",
            "resources",
        ):
            assert [item.model_dump() for item in getattr(csv_portfolio, collection)] == [
                item.model_dump() for item in getattr(before, collection)
            ]

    def test_missing_inputs_produce_guidance_not_a_guess(self, csv_portfolio) -> None:
        result = copilot_scenarios.answer(None, None, csv_portfolio, ANALYSIS_DATE, allowed=True)

        assert result.status == "clarification"
        assert "Name a dependency" in result.executive_summary
        assert result.source_ids == []

    def test_a_role_without_permission_cannot_run_the_engine(self, csv_portfolio) -> None:
        result = copilot_scenarios.answer(
            DEPENDENCY, DELAY, csv_portfolio, ANALYSIS_DATE, allowed=False
        )

        assert result.status == "clarification"
        assert "role does not allow" in result.executive_summary
        assert result.source_ids == []


class TestEndpointPermission:
    @staticmethod
    def _semantic_route(*_args, **_kwargs) -> semantic_router.SemanticRoute:
        return semantic_router.SemanticRoute(
            status="ok",
            intent=semantic_router.SCENARIO_ANALYSIS,
            confidence="high",
            dependency_id=DEPENDENCY,
            additional_delay_days=DELAY,
        )

    def test_administrator_can_run_a_scenario_through_ask(
        self, client: TestClient, monkeypatch
    ) -> None:
        monkeypatch.setattr(semantic_router, "interpret", self._semantic_route)

        response = client.post(
            url("/copilot/ask"),
            json={"question": "What if D-2001 slips by 10 days?"},
        )

        assert response.status_code == 200
        assert response.json()["matched_intent"] == semantic_router.SCENARIO_ANALYSIS

    def test_engineer_cannot_bypass_scenario_permission_through_ask(
        self, engineer_client: TestClient, monkeypatch
    ) -> None:
        monkeypatch.setattr(semantic_router, "interpret", self._semantic_route)

        response = engineer_client.post(
            url("/copilot/ask"),
            json={"question": "What if D-2001 slips by 10 days?"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "clarification"
        assert "role does not allow" in response.json()["executive_summary"]
