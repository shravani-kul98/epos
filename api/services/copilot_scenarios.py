"""Ask EPOS adapter for the existing deterministic dependency-delay scenario engine."""

from __future__ import annotations

from datetime import date

from api.schemas import CopilotAnswer, EvidenceRecordOut
from api.services import analytics_service, workspace_evidence
from api.services.semantic_router import SCENARIO_ANALYSIS
from src.config import AI_DISCLAIMER
from src.data_loader import PortfolioData
from src.scoring_rules import SCENARIO_MAX_DELAY_DAYS, SCENARIO_MIN_DELAY_DAYS
from src.ui_formatting import format_score, format_signed_score
from src.validators import DataValidationError


def _clarification(message: str) -> CopilotAnswer:
    return CopilotAnswer(
        status="clarification",
        matched_intent=None,
        matched_question=None,
        executive_summary=message,
        key_findings=[],
        recommended_actions=[],
        source_ids=[],
        human_review_required=True,
        disclaimer=AI_DISCLAIMER,
        warnings=[],
        evidence=[],
        suggested_questions=[
            "What happens if dependency D-2001 slips by 10 days?",
        ],
    )


def answer(
    dependency_id: str | None,
    additional_delay_days: int | None,
    portfolio: PortfolioData,
    as_of_date: date,
    allowed: bool,
) -> CopilotAnswer:
    """Validate permission and inputs, then run the existing non-mutating engine."""
    if not allowed:
        return _clarification("Your role does not allow scenario simulation.")
    if dependency_id is None or additional_delay_days is None:
        examples = ", ".join(
            dependency.dependency_id
            for dependency in sorted(portfolio.dependencies, key=lambda item: item.dependency_id)[
                :4
            ]
        )
        return _clarification(
            "Name a dependency and an additional delay. "
            f"Delay must be {SCENARIO_MIN_DELAY_DAYS} to {SCENARIO_MAX_DELAY_DAYS} days; "
            f"available examples include {examples}."
        )

    known = {item.dependency_id.casefold(): item.dependency_id for item in portfolio.dependencies}
    dependency_id = known.get(dependency_id.strip().casefold())
    if dependency_id is None:
        return _clarification("That dependency is not available in the projects you can access.")
    try:
        result = analytics_service.run_scenario(
            dependency_id, additional_delay_days, portfolio, as_of_date
        )
    except DataValidationError:
        return _clarification(
            "The scenario inputs or recorded dependency network cannot be simulated. Review the target and delay bounds."
        )
    scenario_id = f"SCENARIO-{dependency_id}-{additional_delay_days}D"
    scenario_evidence = EvidenceRecordOut(
        record_type="scenario_result",
        record_id=scenario_id,
        fields={
            "dependency_id": result.dependency_id,
            "dependency_name": result.dependency_name,
            "additional_delay_days": str(result.additional_delay_days),
            "baseline_delay_days": str(result.baseline_delay_days),
            "scenario_delay_days": str(result.scenario_delay_days),
            "affected_project_count": str(len(result.affected_projects)),
            "as_of_date": result.as_of_date.isoformat(),
            "calculated_at": result.calculated_at.isoformat(),
            "explanation": result.explanation,
        },
    )
    source_records = workspace_evidence.records_by_ids(portfolio, result.source_ids)
    known = {record.record_id for record in source_records}
    derived_sources = [
        EvidenceRecordOut(
            record_type="derived_scenario_source",
            record_id=source_id,
            fields={"derived_by": "deterministic scenario engine"},
        )
        for source_id in result.source_ids
        if source_id not in known
    ]
    findings = [
        f"{item.headline}. {item.detail} Sources: {', '.join(item.source_ids)}."
        for item in result.decision_brief
    ] or [
        (
            f"{project.project_name} changes from "
            f"{format_score(project.baseline_health_score)} "
            f"{project.baseline_health_band} to "
            f"{format_score(project.scenario_health_score)} "
            f"{project.scenario_health_band}; the deterministic health delta is "
            f"{format_signed_score(project.health_score_delta)}."
        )
        for project in result.affected_projects
    ]
    return CopilotAnswer(
        status="ok",
        matched_intent=SCENARIO_ANALYSIS,
        matched_question="What happens if this dependency slips?",
        executive_summary=result.explanation,
        key_findings=findings,
        recommended_actions=[
            "Review the simulated comparison before making any change to the delivery plan."
        ],
        source_ids=[scenario_id, *result.source_ids],
        human_review_required=False,
        disclaimer=AI_DISCLAIMER,
        warnings=result.assumptions_or_limitations,
        evidence=[scenario_evidence, *source_records, *derived_sources],
        suggested_questions=[],
    )
