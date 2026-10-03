"""Scenario explanations must reflect the intervention and sampled evidence."""

from __future__ import annotations

from src import scoring_rules as sr
from src.scenario_engine import analyse_sensitivity, run_scenario
from src.schemas import ScenarioIntervention


def test_sensitivity_samples_are_sorted_and_deduplicated(portfolio, as_of_date):
    result = analyse_sensitivity(
        sr.ScenarioInterventionType.DEPENDENCY_DELAY,
        "D-2002",
        portfolio,
        as_of_date,
        [90, 1, 30, 1],
    )
    assert result.tested_values == [1, 30, 90]
    for threshold in result.thresholds:
        assert threshold.tested_values == result.tested_values
        assert "tested" in threshold.explanation.lower()


def test_risk_improvement_is_not_described_as_a_delay_artifact(portfolio, as_of_date):
    risk = max(portfolio.risks, key=lambda item: item.probability * item.impact)
    result = run_scenario(
        [
            ScenarioIntervention(
                intervention_type=sr.ScenarioInterventionType.RISK_PROBABILITY,
                target_id=risk.risk_id,
                value=1,
            ),
            ScenarioIntervention(
                intervention_type=sr.ScenarioInterventionType.RISK_IMPACT,
                target_id=risk.risk_id,
                value=1,
            ),
        ],
        portfolio,
        as_of_date,
    )
    assert any(
        factor.score_delta > 0
        for project in result.affected_projects
        for factor in project.factor_deltas
    )
    assert all("delay moved work" not in note for note in result.assumptions_or_limitations)
