"""Evidence availability for presenting project delivery scores."""

from pydantic import BaseModel

from src.data_loader import PortfolioData


class ProjectAssessment(BaseModel):
    is_assessed: bool
    reason: str
    source_ids: list[str]


def assess_project_evidence(project_id: str, portfolio: PortfolioData) -> ProjectAssessment:
    """Distinguish absent delivery evidence from calculated fallback values."""
    if portfolio.get_project(project_id) is None:
        raise KeyError(project_id)
    source_ids = sorted(
        [row.milestone_id for row in portfolio.milestones if row.project_id == project_id]
        + [row.task_id for row in portfolio.tasks if row.project_id == project_id]
    )
    return ProjectAssessment(
        is_assessed=bool(source_ids),
        reason=(
            "Based on recorded delivery work; review data confidence and calculation limitations."
            if source_ids
            else "Add a milestone or task before interpreting delivery scores. No delivery records are available."
        ),
        source_ids=[project_id, *source_ids],
    )
