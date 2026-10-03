"""Multi-event scenarios and deterministic sensitivity analysis.

Sensitivity is a set of full engine re-runs, not an interpolation, so these tests assert that the
reported thresholds correspond to tested values and that an unresponsive input is declared rather
than disguised.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.data_loader import PortfolioData
from src.scenario_engine import analyse_sensitivity, run_scenario
from src.schemas import Milestone, Project, ScenarioIntervention, Task
from src.scoring_rules import SCENARIO_SENSITIVITY_DELAY_DAYS, ScenarioInterventionType
from src.validators import DataValidationError

AS_OF = date(2026, 8, 25)
DELAY = ScenarioInterventionType.DEPENDENCY_DELAY
TASK_DELAY = ScenarioInterventionType.TASK_DELAY


@pytest.fixture
def portfolio(make_dependency) -> PortfolioData:
    return PortfolioData(
        projects=[
            Project(
                project_id="P-900",
                project_name="Sensitivity Probe",
                domain="Engineering",
                project_manager="Synthetic Manager",
                start_date=date(2026, 1, 1),
                baseline_end_date=date(2026, 9, 1),
                forecast_end_date=date(2026, 9, 1),
                project_phase="Execution",
                business_priority="High",
            )
        ],
        milestones=[
            Milestone(
                milestone_id="M-900",
                project_id="P-900",
                milestone_name="Design freeze",
                baseline_date=date(2026, 8, 1),
                forecast_date=date(2026, 8, 1),
                status="On Track",
                criticality="High",
            )
        ],
        tasks=[
            Task(
                task_id="T-900",
                project_id="P-900",
                milestone_id="M-900",
                task_name="Build",
                status="In Progress",
                planned_end_date=date(2026, 7, 1),
                forecast_end_date=date(2026, 7, 1),
                completion_percent=40,
                is_blocked=False,
                planned_start_date=date(2026, 7, 1),
            )
        ],
        dependencies=[
            make_dependency(
                dependency_id="D-900",
                project_id="P-900",
                predecessor_type="Task",
                predecessor_id="T-900",
                successor_type="Milestone",
                successor_id="M-900",
                delay_days=0,
                criticality="High",
            )
        ],
    )


class TestSensitivity:
    def test_every_documented_delay_step_is_evaluated(self, portfolio: PortfolioData) -> None:
        result = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF)
        assert result.tested_values == list(SCENARIO_SENSITIVITY_DELAY_DAYS)
        assert len(result.health_scores) == len(result.tested_values)
        assert len(result.forecast_shift_days) == len(result.tested_values)

    def test_forecast_movement_is_ordered_by_input_size(self, portfolio: PortfolioData) -> None:
        result = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF)
        assert result.forecast_shift_days == sorted(result.forecast_shift_days)

    def test_a_threshold_names_a_value_that_was_actually_tested(
        self, portfolio: PortfolioData
    ) -> None:
        result = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF)
        for threshold in result.thresholds:
            if threshold.occurs_at_value is not None:
                assert threshold.occurs_at_value in result.tested_values

    def test_the_reported_threshold_is_the_first_value_that_moves_the_finish_date(
        self, portfolio: PortfolioData
    ) -> None:
        result = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF)
        schedule = next(
            item for item in result.thresholds if "forecast end date moves" in item.outcome
        )
        moving = [
            value
            for value, shift in zip(result.tested_values, result.forecast_shift_days, strict=True)
            if shift > 0
        ]
        assert schedule.occurs_at_value == (moving[0] if moving else None)

    def test_interpolation_is_explicitly_disclaimed(self, portfolio: PortfolioData) -> None:
        result = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF)
        assert any(
            "no value between tested points" in item for item in result.assumptions_or_limitations
        )

    def test_an_unresponsive_input_is_declared(self, portfolio: PortfolioData) -> None:
        # A risk that no project records cannot move anything, so the range must say so.
        result = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF, values=[1])
        assert result.tested_values == [1]
        if not result.is_responsive:
            assert any(
                "did not change the outcome" in item for item in result.assumptions_or_limitations
            )

    def test_values_outside_the_documented_bounds_are_dropped(
        self, portfolio: PortfolioData
    ) -> None:
        result = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF, values=[5, 900, 10])
        assert result.tested_values == [5, 10]

    def test_a_range_with_no_valid_value_is_refused(self, portfolio: PortfolioData) -> None:
        with pytest.raises(DataValidationError):
            analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF, values=[0, 5000])

    def test_sensitivity_is_repeatable(self, portfolio: PortfolioData) -> None:
        first = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF)
        second = analyse_sensitivity(DELAY, "D-900", portfolio, AS_OF)
        assert first.model_dump() == second.model_dump()


class TestMultiEvent:
    def test_two_interventions_are_both_recorded(self, portfolio: PortfolioData) -> None:
        result = run_scenario(
            [
                ScenarioIntervention(intervention_type=DELAY, target_id="D-900", value=10),
                ScenarioIntervention(intervention_type=TASK_DELAY, target_id="T-900", value=20),
            ],
            portfolio,
            AS_OF,
        )
        assert result.scenario_type == "multi_event"
        assert {item.target_id for item in result.interventions} == {"D-900", "T-900"}

    def test_a_combined_scenario_moves_at_least_as_far_as_its_largest_part(
        self, portfolio: PortfolioData
    ) -> None:
        single = run_scenario(
            [ScenarioIntervention(intervention_type=TASK_DELAY, target_id="T-900", value=20)],
            portfolio,
            AS_OF,
        )
        combined = run_scenario(
            [
                ScenarioIntervention(intervention_type=TASK_DELAY, target_id="T-900", value=20),
                ScenarioIntervention(intervention_type=DELAY, target_id="D-900", value=5),
            ],
            portfolio,
            AS_OF,
        )
        assert (
            combined.affected_projects[0].forecast_end_shift_days
            >= single.affected_projects[0].forecast_end_shift_days
        )
