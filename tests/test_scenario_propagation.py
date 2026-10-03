"""Scenario propagation must be causal, repeatable, and never reward delay.

These tests build small explicit networks rather than relying on the synthetic CSV portfolio, so
each propagation rule is proved in isolation and a data change cannot silently weaken them.
"""

from __future__ import annotations

import copy
from datetime import date

import pytest

from src.data_loader import PortfolioData
from src.scenario_engine import run_scenario, simulate_dependency_delay
from src.schemas import (
    Dependency,
    Milestone,
    Project,
    Resource,
    Risk,
    ScenarioIntervention,
    Task,
)
from src.scoring_rules import ScenarioInterventionType
from src.validators import DataValidationError

AS_OF = date(2026, 8, 25)


def _project(project_id: str = "P-900") -> Project:
    return Project(
        project_id=project_id,
        project_name="Propagation Probe",
        domain="Engineering",
        project_manager="Synthetic Manager",
        start_date=date(2026, 1, 1),
        baseline_end_date=date(2026, 12, 1),
        forecast_end_date=date(2026, 12, 1),
        project_phase="Execution",
        business_priority="High",
    )


def _task(task_id: str, planned: date, forecast: date, milestone_id: str = "M-900") -> Task:
    return Task(
        task_id=task_id,
        project_id="P-900",
        milestone_id=milestone_id,
        task_name=f"Task {task_id}",
        status="In Progress",
        planned_end_date=planned,
        forecast_end_date=forecast,
        completion_percent=50,
        is_blocked=False,
        planned_start_date=planned,
    )


def _milestone(milestone_id: str, baseline: date, forecast: date) -> Milestone:
    return Milestone(
        milestone_id=milestone_id,
        project_id="P-900",
        milestone_name=f"Milestone {milestone_id}",
        baseline_date=baseline,
        forecast_date=forecast,
        status="On Track",
        criticality="High",
    )


def _dependency(
    dependency_id: str,
    predecessor_id: str,
    successor_id: str,
    *,
    predecessor_type: str = "Task",
    successor_type: str = "Task",
    lag_days: int | None = None,
) -> Dependency:
    return Dependency(
        dependency_id=dependency_id,
        project_id="P-900",
        predecessor_type=predecessor_type,
        predecessor_id=predecessor_id,
        successor_type=successor_type,
        successor_id=successor_id,
        dependency_name=f"Dependency {dependency_id}",
        status="On Track",
        delay_days=0,
        criticality="High",
        relationship_type="Finish-to-Start" if lag_days is not None else None,
        lag_days=lag_days,
    )


@pytest.fixture
def chain() -> PortfolioData:
    """T-1 -> T-2 -> T-3, plus an unrelated branch T-9, all with zero float."""
    day = date(2026, 6, 1)
    return PortfolioData(
        projects=[_project()],
        milestones=[_milestone("M-900", date(2026, 11, 1), date(2026, 11, 1))],
        tasks=[
            _task("T-1", day, day),
            _task("T-2", day, day),
            _task("T-3", day, day),
            _task("T-9", day, day),
        ],
        dependencies=[
            _dependency("D-1", "T-1", "T-2", lag_days=0),
            _dependency("D-2", "T-2", "T-3", lag_days=0),
        ],
    )


class TestDelayMagnitude:
    """The defect that started this: a one-day slip scored the same as a one-year slip."""

    @pytest.mark.parametrize("days", [1, 5, 10, 30, 90, 180, 365])
    def test_every_delay_moves_the_successor_by_that_many_days(
        self, chain: PortfolioData, days: int
    ) -> None:
        result = simulate_dependency_delay("D-1", days, chain, AS_OF)
        moved = {item.record_id: item.shift_days for item in result.schedule_movements}
        assert moved["T-2"] == days
        assert moved["T-3"] == days

    def test_movement_is_strictly_ordered_by_delay_size(self, chain: PortfolioData) -> None:
        shifts = [
            max(
                item.shift_days
                for item in simulate_dependency_delay("D-1", days, chain, AS_OF).schedule_movements
            )
            for days in (1, 5, 10, 30, 90, 180, 365)
        ]
        assert shifts == sorted(shifts)
        assert len(set(shifts)) == len(shifts)

    def test_any_improvement_under_added_delay_is_explained_not_hidden(
        self, chain: PortfolioData
    ) -> None:
        """Task execution drops its overdue penalty once a forecast passes today.

        That is a property of the recorded scoring rules, not of the simulation. The scenario must
        surface it rather than present added delay as an improvement.
        """
        for days in (1, 5, 10, 30, 90, 180, 365):
            result = simulate_dependency_delay("D-1", days, chain, AS_OF)
            improved = [
                item for item in result.affected_projects[0].factor_deltas if item.score_delta > 0
            ]
            for factor in improved:
                assert any(
                    factor.factor in note and "rather than because delivery improved" in note
                    for note in result.assumptions_or_limitations
                )

    def test_forecast_movement_never_shrinks_as_delay_grows(self, chain: PortfolioData) -> None:
        shifts = [
            simulate_dependency_delay("D-1", days, chain, AS_OF)
            .affected_projects[0]
            .forecast_end_shift_days
            for days in (1, 5, 10, 30, 90, 180, 365)
        ]
        assert shifts == sorted(shifts)


class TestPropagation:
    def test_delay_reaches_every_downstream_hop(self, chain: PortfolioData) -> None:
        result = simulate_dependency_delay("D-1", 10, chain, AS_OF)
        hops = {item.record_id: item.propagation_hop for item in result.schedule_movements}
        assert hops["T-2"] == 0
        assert hops["T-3"] == 1

    def test_each_movement_names_the_dependency_that_controlled_it(
        self, chain: PortfolioData
    ) -> None:
        result = simulate_dependency_delay("D-1", 10, chain, AS_OF)
        propagated = next(i for i in result.schedule_movements if i.record_id == "T-3")
        assert propagated.controlling_dependency_id == "D-2"
        assert propagated.controlling_predecessor_id == "T-2"

    def test_an_unrelated_branch_is_never_moved(self, chain: PortfolioData) -> None:
        result = simulate_dependency_delay("D-1", 365, chain, AS_OF)
        assert "T-9" not in {item.record_id for item in result.schedule_movements}

    def test_free_float_absorbs_delay_before_it_travels(self) -> None:
        portfolio = PortfolioData(
            projects=[_project()],
            milestones=[_milestone("M-900", date(2026, 11, 1), date(2026, 11, 1))],
            tasks=[
                _task("T-1", date(2026, 6, 1), date(2026, 6, 1)),
                # Ten days of recorded slack before this successor is due to start.
                _task("T-2", date(2026, 6, 11), date(2026, 6, 11)),
            ],
            dependencies=[_dependency("D-1", "T-1", "T-2", lag_days=0)],
        )
        absorbed = simulate_dependency_delay("D-1", 4, portfolio, AS_OF)
        assert absorbed.schedule_movements == []

        exceeded = simulate_dependency_delay("D-1", 15, portfolio, AS_OF)
        moved = {item.record_id: item.shift_days for item in exceeded.schedule_movements}
        assert moved["T-2"] == 5

    def test_converging_paths_take_the_controlling_delay_not_the_sum(self) -> None:
        day = date(2026, 6, 1)
        portfolio = PortfolioData(
            projects=[_project()],
            milestones=[_milestone("M-900", date(2026, 11, 1), date(2026, 11, 1))],
            tasks=[_task(name, day, day) for name in ("T-1", "T-2", "T-3")],
            dependencies=[
                _dependency("D-1", "T-1", "T-3", lag_days=0),
                _dependency("D-2", "T-2", "T-3", lag_days=0),
            ],
        )
        result = run_scenario(
            [
                ScenarioIntervention(
                    intervention_type=ScenarioInterventionType.TASK_DELAY,
                    target_id="T-1",
                    value=10,
                ),
                ScenarioIntervention(
                    intervention_type=ScenarioInterventionType.TASK_DELAY,
                    target_id="T-2",
                    value=25,
                ),
            ],
            portfolio,
            AS_OF,
        )
        moved = {item.record_id: item.shift_days for item in result.schedule_movements}
        assert moved["T-3"] == 25

    def test_recorded_lag_is_honoured_as_slack(self) -> None:
        portfolio = PortfolioData(
            projects=[_project()],
            milestones=[_milestone("M-900", date(2026, 11, 1), date(2026, 11, 1))],
            tasks=[
                _task("T-1", date(2026, 6, 1), date(2026, 6, 1)),
                _task("T-2", date(2026, 6, 21), date(2026, 6, 21)),
            ],
            dependencies=[_dependency("D-1", "T-1", "T-2", lag_days=15)],
        )
        # 20 days of gap minus 15 days of required lag leaves 5 days of true float.
        result = simulate_dependency_delay("D-1", 12, portfolio, AS_OF)
        moved = {item.record_id: item.shift_days for item in result.schedule_movements}
        assert moved["T-2"] == 7

    def test_a_cyclic_network_fails_safely(self) -> None:
        day = date(2026, 6, 1)
        portfolio = PortfolioData(
            projects=[_project()],
            milestones=[_milestone("M-900", date(2026, 11, 1), date(2026, 11, 1))],
            tasks=[_task("T-1", day, day), _task("T-2", day, day)],
            dependencies=[
                _dependency("D-1", "T-1", "T-2", lag_days=0),
                _dependency("D-2", "T-2", "T-1", lag_days=0),
            ],
        )
        with pytest.raises(DataValidationError, match="cannot be simulated"):
            simulate_dependency_delay("D-1", 10, portfolio, AS_OF)

    def test_a_milestone_moves_and_pushes_the_project_finish(self) -> None:
        portfolio = PortfolioData(
            projects=[_project()],
            milestones=[_milestone("M-900", date(2026, 11, 1), date(2026, 11, 1))],
            tasks=[_task("T-1", date(2026, 6, 1), date(2026, 6, 1))],
            dependencies=[
                _dependency("D-1", "T-1", "M-900", successor_type="Milestone", lag_days=0)
            ],
        )
        result = simulate_dependency_delay("D-1", 200, portfolio, AS_OF)
        comparison = result.affected_projects[0]
        assert comparison.forecast_end_shift_days > 0
        assert comparison.scenario_forecast_end_date > comparison.baseline_forecast_end_date


class TestDeterminism:
    def test_the_baseline_is_never_modified(self, chain: PortfolioData) -> None:
        before = copy.deepcopy(chain)
        simulate_dependency_delay("D-1", 365, chain, AS_OF)
        assert chain == before

    def test_repeating_a_scenario_returns_the_same_result(self, chain: PortfolioData) -> None:
        first = simulate_dependency_delay("D-1", 30, chain, AS_OF)
        second = simulate_dependency_delay("D-1", 30, chain, AS_OF)
        assert first.model_dump() == second.model_dump()

    def test_commutative_interventions_are_order_independent(self, chain: PortfolioData) -> None:
        one = ScenarioIntervention(
            intervention_type=ScenarioInterventionType.TASK_DELAY, target_id="T-1", value=10
        )
        two = ScenarioIntervention(
            intervention_type=ScenarioInterventionType.TASK_DELAY, target_id="T-9", value=20
        )
        forward = run_scenario([one, two], chain, AS_OF)
        reverse = run_scenario([two, one], chain, AS_OF)
        assert forward.model_dump() == reverse.model_dump()


class TestValidation:
    def test_an_unknown_target_is_refused(self, chain: PortfolioData) -> None:
        with pytest.raises(DataValidationError, match="unknown"):
            run_scenario(
                [
                    ScenarioIntervention(
                        intervention_type=ScenarioInterventionType.TASK_DELAY,
                        target_id="T-NOPE",
                        value=5,
                    )
                ],
                chain,
                AS_OF,
            )

    @pytest.mark.parametrize("value", [0, 366])
    def test_a_delay_outside_the_documented_bounds_is_refused(
        self, chain: PortfolioData, value: int
    ) -> None:
        with pytest.raises(DataValidationError):
            run_scenario(
                [
                    ScenarioIntervention(
                        intervention_type=ScenarioInterventionType.TASK_DELAY,
                        target_id="T-1",
                        value=value,
                    )
                ],
                chain,
                AS_OF,
            )

    def test_conflicting_interventions_on_one_record_are_refused(
        self, chain: PortfolioData
    ) -> None:
        duplicate = [
            ScenarioIntervention(
                intervention_type=ScenarioInterventionType.TASK_DELAY, target_id="T-1", value=5
            ),
            ScenarioIntervention(
                intervention_type=ScenarioInterventionType.TASK_DELAY, target_id="T-1", value=9
            ),
        ]
        with pytest.raises(DataValidationError, match="conflicting"):
            run_scenario(duplicate, chain, AS_OF)

    def test_a_scenario_needs_at_least_one_intervention(self, chain: PortfolioData) -> None:
        with pytest.raises(DataValidationError, match="at least one"):
            run_scenario([], chain, AS_OF)


class TestNonScheduleInterventions:
    def test_raising_risk_probability_changes_risk_exposure(self) -> None:
        portfolio = PortfolioData(
            projects=[_project()],
            milestones=[_milestone("M-900", date(2026, 11, 1), date(2026, 11, 1))],
            tasks=[_task("T-1", date(2026, 6, 1), date(2026, 6, 1))],
            risks=[
                Risk(
                    risk_id="R-900",
                    project_id="P-900",
                    risk_name="Synthetic exposure",
                    probability=1,
                    impact=1,
                    status="Open",
                    due_date=date(2026, 10, 1),
                )
            ],
        )
        result = run_scenario(
            [
                ScenarioIntervention(
                    intervention_type=ScenarioInterventionType.RISK_PROBABILITY,
                    target_id="R-900",
                    value=5,
                ),
                ScenarioIntervention(
                    intervention_type=ScenarioInterventionType.RISK_IMPACT,
                    target_id="R-900",
                    value=5,
                ),
            ],
            portfolio,
            AS_OF,
        )
        exposure = next(
            item
            for item in result.affected_projects[0].factor_deltas
            if item.factor == "risk_exposure"
        )
        assert exposure.score_delta < 0

    def test_cutting_capacity_changes_resource_capacity(self) -> None:
        portfolio = PortfolioData(
            projects=[_project()],
            milestones=[_milestone("M-900", date(2026, 11, 1), date(2026, 11, 1))],
            tasks=[_task("T-1", date(2026, 6, 1), date(2026, 6, 1))],
            resources=[
                Resource(
                    resource_id="RES-900",
                    resource_name="Synthetic Engineer",
                    project_id="P-900",
                    allocated_hours=40,
                    capacity_hours=40,
                    week_start_date=date(2026, 8, 24),
                )
            ],
        )
        result = run_scenario(
            [
                ScenarioIntervention(
                    intervention_type=ScenarioInterventionType.RESOURCE_CAPACITY,
                    target_id="RES-900",
                    value=20,
                )
            ],
            portfolio,
            AS_OF,
        )
        capacity = next(
            item
            for item in result.affected_projects[0].factor_deltas
            if item.factor == "resource_capacity"
        )
        assert capacity.score_delta < 0


class TestExplainability:
    def test_every_moved_record_is_cited(self, chain: PortfolioData) -> None:
        result = simulate_dependency_delay("D-1", 30, chain, AS_OF)
        for movement in result.schedule_movements:
            assert movement.record_id in result.source_ids

    def test_the_factor_waterfall_covers_every_health_factor(self, chain: PortfolioData) -> None:
        from src.scoring_rules import HEALTH_FACTORS

        deltas = simulate_dependency_delay("D-1", 30, chain, AS_OF).affected_projects[0]
        assert {item.factor for item in deltas.factor_deltas} == set(HEALTH_FACTORS)

    def test_the_applied_interventions_are_returned_with_the_result(
        self, chain: PortfolioData
    ) -> None:
        result = simulate_dependency_delay("D-1", 30, chain, AS_OF)
        assert [item.target_id for item in result.interventions] == ["D-1"]
        assert result.interventions[0].unit == "calendar days"
