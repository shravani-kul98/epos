"""EPOS Next FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import select

from api import settings
from api.database import init_db, schema_is_current
from api.dependencies import AsOfDateDep, SessionDep
from api.models import ProjectTable
from api.routers import (
    actions,
    activity,
    admin,
    analytics,
    assumptions,
    auth,
    change_requests,
    copilot,
    decisions,
    deliverables,
    dependencies,
    gates,
    issues,
    meeting_notes,
    milestones,
    notifications,
    projects,
    requirements,
    resources,
    risks,
    scenarios,
    search,
    tasks,
    verification,
    work_packages,
)
from api.schemas import HealthCheck, ReadinessCheck
from api.security.rate_limit import RateLimits
from api.static_files import mount_frontend
from src.config import get_azure_settings
from src.validators import DataValidationError

API_PREFIX = "/api/v1"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepare the schema for local development only.

    Elsewhere a versioned database is brought up to date on first use, once per instance and under
    a database lock (see ``api.database.ensure_schema_upgraded``), so cold starts never race.
    """
    if settings.run_migrations_on_startup():
        init_db()
    yield


def create_app() -> FastAPI:
    """Build the application. Kept as a factory so tests can construct isolated instances."""
    docs_enabled = settings.api_docs_enabled()
    app = FastAPI(
        title="EPOS",
        description=(
            "Engineering portfolio intelligence. Deterministic Python calculates every score; "
            "the AI layer only explains evidence that was already calculated."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.rate_limits = RateLimits.from_settings()

    # Added only when a cross-origin caller is configured. Served from this process the browser is
    # same-origin, and omitting the middleware also lets the platform serve assets from its CDN.
    cross_origin_callers = settings.allowed_origins()
    if cross_origin_callers:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cross_origin_callers),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )

    @app.exception_handler(StaleDataError)
    async def stale_write_handler(_: Request, __: StaleDataError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "This record changed after it was loaded. Refresh it and try again."
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_conflict_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        # The statement and its parameters can carry record content, so only the failure class is
        # logged.
        logger.warning(
            "Write conflict on %s %s (%s)",
            request.method,
            request.url.path,
            type(exc.orig).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "The write conflicted with current database state."},
        )

    @app.exception_handler(DataValidationError)
    async def analysis_validation_handler(
        request: Request, exc: DataValidationError
    ) -> JSONResponse:
        # A requested analysis date earlier than the stored records is the caller's to change;
        # otherwise the stored records themselves failed the engines' checks.
        if "as_of_date" in request.query_params:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={"detail": f"The requested analysis date cannot be used: {exc}"},
            )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": f"Analysis is unavailable because stored data failed validation: {exc}"
            },
        )

    for module in (
        auth,
        projects,
        milestones,
        work_packages,
        deliverables,
        tasks,
        gates,
        risks,
        actions,
        issues,
        assumptions,
        requirements,
        verification,
        change_requests,
        decisions,
        dependencies,
        resources,
        meeting_notes,
        analytics,
        scenarios,
        search,
        copilot,
        activity,
        notifications,
        admin,
    ):
        app.include_router(module.router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health", response_model=HealthCheck, tags=["meta"])
    def health(session: SessionDep, as_of_date: AsOfDateDep) -> HealthCheck:
        """Service readiness. Never reports secret values, only whether config is present."""
        project_count = session.exec(
            select(func.count()).select_from(ProjectTable).where(ProjectTable.deleted_at.is_(None))
        ).one()
        return HealthCheck(
            status="ok",
            database_seeded=project_count > 0,
            project_count=project_count,
            ai_configured=get_azure_settings().is_configured,
            analysis_date=as_of_date,
            schema_current=schema_is_current(session.connection()),
        )

    @app.get(f"{API_PREFIX}/ready", response_model=ReadinessCheck, tags=["meta"])
    def ready() -> ReadinessCheck:
        """Liveness probe that reaches no dependency and reports only the environment category."""
        return ReadinessCheck(
            status="ok",
            environment=settings.environment(),
            version=app.version,
        )

    # Registered last so it cannot shadow any API route.
    mount_frontend(app, API_PREFIX)

    return app


app = create_app()
