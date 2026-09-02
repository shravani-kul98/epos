"""Adapter that materialises a :class:`PortfolioData` from database rows.

This is the seam between persistence and the deterministic engines. The engines are unchanged and
remain unaware that a database exists.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlmodel import Session, SQLModel

from api import models
from api.crud import list_rows, to_entity
from src.data_loader import PortfolioData, find_status_anomalies
from src.schemas import (
    Action,
    ChangeRequest,
    Dependency,
    Milestone,
    Project,
    Requirement,
    Resource,
    Risk,
    Task,
    TestCase,
    TraceLink,
)

# Portfolio attribute -> (table, entity model).
_LOAD_PLAN: tuple[tuple[str, type[SQLModel], type[BaseModel]], ...] = (
    ("projects", models.ProjectTable, Project),
    ("milestones", models.MilestoneTable, Milestone),
    ("tasks", models.TaskTable, Task),
    ("risks", models.RiskTable, Risk),
    ("dependencies", models.DependencyTable, Dependency),
    ("actions", models.ActionTable, Action),
    ("resources", models.ResourceTable, Resource),
    ("requirements", models.RequirementTable, Requirement),
    ("test_cases", models.TestCaseTable, TestCase),
    ("trace_links", models.TraceLinkTable, TraceLink),
    ("change_requests", models.ChangeRequestTable, ChangeRequest),
)


def load_portfolio_from_db(session: Session, project_ids: set[str] | None = None) -> PortfolioData:
    """Read every live table row and return a validated portfolio for the engines to consume.

    Withdrawn records are excluded, so deleting work changes the analysis exactly as a user would
    expect while the row itself is kept for audit.
    """
    collections: dict[str, list[BaseModel]] = {}
    for attribute, table, model in _LOAD_PLAN:
        rows = list_rows(session, table, project_id=None, project_ids=project_ids)
        collections[attribute] = [to_entity(row, model) for row in rows]

    portfolio = PortfolioData(**collections)  # type: ignore[arg-type]
    portfolio.status_anomalies = find_status_anomalies(portfolio)
    return portfolio
