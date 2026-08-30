"""Deterministic analytics: dashboards, scores, alerts and traceability."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import AsOfDateDep, PortfolioDep, SessionDep
from api.schemas import (
    AlertOut,
    ConfidenceOut,
    ExecutiveReport,
    HealthOut,
    PortfolioDashboard,
    PortfolioFilters,
    ProjectDashboard,
    TraceabilityMatrix,
)
from api.security.dependencies import CurrentUser, ReportReader
from api.services import analytics_service, report_service
from src.confidence_engine import calculate_project_confidence
from src.health_engine import calculate_project_health
from src.risk_engine import generate_early_warnings, generate_portfolio_early_warnings

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _require_project(portfolio, project_id: str) -> None:
    """Raise 404 when the project is not in the portfolio."""
    if portfolio.get_project(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} was not found."
        )


@router.get("/portfolio", response_model=PortfolioDashboard)
def get_portfolio_dashboard(
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    _: CurrentUser,
    filters: Annotated[PortfolioFilters, Depends()],
) -> PortfolioDashboard:
    """Portfolio overview: band mix, alert mix and a scored project table."""
    if (
        filters.forecast_after
        and filters.forecast_before
        and filters.forecast_after > filters.forecast_before
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The forecast range must start on or before its end date.",
        )
    try:
        return analytics_service.portfolio_dashboard(portfolio, as_of_date, filters)
    except analytics_service.PortfolioAnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio analysis is unavailable for project {exc.project_id}.",
        ) from exc


@router.get("/projects/{project_id}", response_model=ProjectDashboard)
def get_project_dashboard(
    project_id: str, portfolio: PortfolioDep, as_of_date: AsOfDateDep, _: CurrentUser
) -> ProjectDashboard:
    """Full intelligence view for one project."""
    _require_project(portfolio, project_id)
    return analytics_service.project_dashboard(project_id, portfolio, as_of_date)


@router.get("/projects/{project_id}/health", response_model=HealthOut)
def get_project_health(
    project_id: str, portfolio: PortfolioDep, as_of_date: AsOfDateDep, _: CurrentUser
) -> HealthOut:
    """Health score with its factor breakdown and evidence."""
    _require_project(portfolio, project_id)
    return analytics_service.health_out(calculate_project_health(project_id, portfolio, as_of_date))


@router.get("/projects/{project_id}/confidence", response_model=ConfidenceOut)
def get_project_confidence(
    project_id: str, portfolio: PortfolioDep, as_of_date: AsOfDateDep, _: CurrentUser
) -> ConfidenceOut:
    """Delivery confidence with its factor breakdown and information-quality issues."""
    _require_project(portfolio, project_id)
    return analytics_service.confidence_out(
        calculate_project_confidence(project_id, portfolio, as_of_date)
    )


@router.get("/alerts", response_model=list[AlertOut])
def get_alerts(
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    _: CurrentUser,
    project_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
) -> list[AlertOut]:
    """Early-warning alerts across the portfolio or for one project."""
    if project_id is not None:
        _require_project(portfolio, project_id)
        alerts = generate_early_warnings(project_id, portfolio, as_of_date)
    else:
        alerts = generate_portfolio_early_warnings(portfolio, as_of_date)

    if severity is not None:
        alerts = [alert for alert in alerts if alert.severity == severity]
    return [analytics_service.alert_out(alert) for alert in alerts]


@router.get("/traceability", response_model=TraceabilityMatrix)
def get_traceability(
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    _: CurrentUser,
    project_id: str | None = Query(default=None),
) -> TraceabilityMatrix:
    """Requirement-to-test coverage derived from trace links."""
    if project_id is not None:
        _require_project(portfolio, project_id)
    return analytics_service.traceability_matrix(portfolio, as_of_date, project_id)


@router.get("/executive-report", response_model=ExecutiveReport)
def get_executive_report(
    session: SessionDep,
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    _: ReportReader,
    days: int = Query(default=7, ge=1, le=365),
) -> ExecutiveReport:
    """The weekly executive report, assembled from calculated scores and recorded history."""
    return report_service.build(session, portfolio, as_of_date, days)
