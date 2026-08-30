"""One search across every record type in the workspace."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.dependencies import SessionDep
from api.schemas import SearchResults
from api.security.dependencies import PortfolioReader
from api.security.project_scope import project_ids_for
from api.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResults)
def search_workspace(
    session: SessionDep,
    actor: PortfolioReader,
    q: str = Query(
        max_length=200, description="What to look for. Matches identifiers, names and owners."
    ),
    limit: int = Query(default=20, ge=1, le=100),
) -> SearchResults:
    """Find any project, delivery record, register entry, requirement, decision or meeting note."""
    return search_service.search(session, q, limit, project_ids_for(session, actor))
