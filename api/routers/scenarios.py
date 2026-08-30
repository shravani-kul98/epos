"""Non-mutating what-if simulation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.dependencies import AsOfDateDep, PortfolioDep
from api.schemas import (
    CopilotAnswer,
    DependencyOut,
    ScenarioOut,
    ScenarioRequest,
    ScenarioRunRequest,
    ScenarioSensitivityOut,
    ScenarioSensitivityRequest,
)
from api.security.dependencies import AssistantQuota, CurrentUser, ScenarioRunner
from api.serializers import dependency_out
from api.services import analytics_service, scenario_explanation
from src.schemas import ScenarioIntervention
from src.validators import DataValidationError

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _refused(exc: DataValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"The scenario could not be run: {exc}",
    )


@router.get("/dependencies", response_model=list[DependencyOut])
def list_simulatable_dependencies(portfolio: PortfolioDep, _: CurrentUser) -> list[DependencyOut]:
    """List the dependencies a delay scenario can be run against."""
    return [
        dependency_out(dependency)
        for dependency in sorted(portfolio.dependencies, key=lambda d: d.dependency_id)
    ]


@router.post("/dependency-delay", response_model=ScenarioOut)
def simulate_dependency_delay_scenario(
    payload: ScenarioRequest,
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    _: ScenarioRunner,
) -> ScenarioOut:
    """Compare baseline against a hypothetical additional dependency delay.

    The simulation runs on a copy of the portfolio. Stored data is never modified.
    """
    try:
        return analytics_service.run_scenario(
            payload.dependency_id, payload.additional_delay_days, portfolio, as_of_date
        )
    except DataValidationError as exc:
        raise _refused(exc) from exc


@router.post("/explain", response_model=CopilotAnswer, dependencies=[AssistantQuota])
def explain_dependency_delay_scenario(
    payload: ScenarioRequest,
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    _: ScenarioRunner,
) -> CopilotAnswer:
    """Explain an already governed deterministic scenario without changing its facts."""
    try:
        result = analytics_service.run_scenario(
            payload.dependency_id, payload.additional_delay_days, portfolio, as_of_date
        )
    except DataValidationError as exc:
        raise _refused(exc) from exc
    return scenario_explanation.explain(result, portfolio)


@router.post("/run", response_model=ScenarioOut)
def run_multi_event_scenario(
    payload: ScenarioRunRequest,
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    _: ScenarioRunner,
) -> ScenarioOut:
    """Run several simultaneous interventions against a copy of the portfolio."""
    try:
        return analytics_service.run_multi_event_scenario(
            [
                ScenarioIntervention(
                    intervention_type=item.intervention_type,
                    target_id=item.target_id,
                    value=item.value,
                    note=item.note,
                )
                for item in payload.interventions
            ],
            portfolio,
            as_of_date,
        )
    except DataValidationError as exc:
        raise _refused(exc) from exc


@router.post("/sensitivity", response_model=ScenarioSensitivityOut)
def run_sensitivity_analysis(
    payload: ScenarioSensitivityRequest,
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    _: ScenarioRunner,
) -> ScenarioSensitivityOut:
    """Re-run one intervention across a range and report where outcomes change."""
    try:
        return analytics_service.run_sensitivity(
            payload.intervention_type, payload.target_id, portfolio, as_of_date, payload.values
        )
    except DataValidationError as exc:
        raise _refused(exc) from exc
