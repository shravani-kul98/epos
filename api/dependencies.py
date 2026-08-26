"""Shared FastAPI dependencies."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlmodel import Session

from api import clock
from api.database import get_session
from api.security.dependencies import CurrentUser
from api.security.project_scope import project_ids_for
from api.services.portfolio_service import load_portfolio_from_db
from src.data_loader import PortfolioData
from src.validators import DataValidationError

SessionDep = Annotated[Session, Depends(get_session)]
RowVersionDep = Annotated[
    int,
    Query(ge=1, description="Version of the record being withdrawn."),
]


def get_as_of_date(
    as_of_date: Annotated[
        date | None,
        Query(
            description=(
                "Reference date for ageing calculations. Defaults to today in UTC. Records are "
                "scored as currently stored, so a date earlier than their last update is refused."
            )
        ),
    ] = None,
) -> date:
    """Resolve the analysis date for a scored request."""
    return as_of_date or clock.utc_today()


AsOfDateDep = Annotated[date, Depends(get_as_of_date)]


def get_portfolio(session: SessionDep, user: CurrentUser) -> PortfolioData:
    """Materialise the portfolio for the engines, surfacing validation failures as 503."""
    try:
        return load_portfolio_from_db(session, project_ids_for(session, user))
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio data failed validation: {exc}",
        ) from exc


PortfolioDep = Annotated[PortfolioData, Depends(get_portfolio)]
