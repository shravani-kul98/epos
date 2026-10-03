"""Tests for Pydantic entity/result schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas import (
    CopilotResponse,
    DeliveryMilestone,
    DeliveryTask,
    GovernedDependency,
    Resource,
    Risk,
    TestCase,
)


def _valid_risk_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "risk_id": "R-1",
        "project_id": "P-1",
        "risk_name": "Example risk",
        "probability": "3",
        "impact": "4",
        "status": "Open",
        "mitigation_owner": "",
        "mitigation_status": "Not Started",
        "due_date": "2026-09-30",
    }
    row.update(overrides)
    return row


def test_valid_risk_parses_and_computes_severity() -> None:
    risk = Risk.model_validate(_valid_risk_row())
    assert risk.severity_score == 12
    # Empty string mitigation owner is normalised to None.
    assert risk.mitigation_owner is None


@pytest.mark.parametrize("bad_value", ["0", "6", "-1"])
def test_risk_probability_out_of_range_rejected(bad_value: str) -> None:
    with pytest.raises(ValidationError):
        Risk.model_validate(_valid_risk_row(probability=bad_value))


def test_completion_percent_range_enforced() -> None:
    resource = Resource.model_validate(
        {
            "resource_id": "RES-1",
            "resource_name": "Sam",
            "project_id": "P-1",
            "allocated_hours": "48",
            "capacity_hours": "40",
            "week_start_date": "2026-08-24",
        }
    )
    assert resource.is_overallocated is True


def test_delivery_schedule_variances_are_deterministic() -> None:
    milestone = DeliveryMilestone(
        milestone_id="M-1",
        project_id="P-1",
        milestone_name="Synthetic milestone",
        baseline_date="2026-09-10",
        forecast_date="2026-09-14",
        actual_date="2026-09-12",
        status="Complete",
        criticality="High",
    )
    task = DeliveryTask(
        task_id="T-1",
        project_id="P-1",
        milestone_id="M-1",
        task_name="Synthetic task",
        status="Complete",
        planned_start_date="2026-09-01",
        forecast_start_date="2026-09-03",
        actual_start_date="2026-09-02",
        planned_end_date="2026-09-10",
        forecast_end_date="2026-09-15",
        actual_end_date="2026-09-12",
        completion_percent=100,
        is_blocked=False,
    )

    assert milestone.forecast_variance_days == 4
    assert milestone.actual_variance_days == 2
    assert task.forecast_start_variance_days == 2
    assert task.forecast_finish_variance_days == 5
    assert task.actual_start_variance_days == 1
    assert task.actual_finish_variance_days == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"planned_start_date": "2026-09-11"},
        {"forecast_start_date": "2026-09-16"},
        {"actual_end_date": "2026-09-12"},
        {"actual_start_date": "2026-09-13", "actual_end_date": "2026-09-12"},
    ],
)
def test_delivery_task_rejects_incoherent_date_ranges(overrides: dict[str, str]) -> None:
    payload = {
        "task_id": "T-1",
        "project_id": "P-1",
        "milestone_id": "M-1",
        "task_name": "Synthetic task",
        "status": "In Progress",
        "planned_start_date": "2026-09-01",
        "forecast_start_date": "2026-09-03",
        "actual_start_date": None,
        "planned_end_date": "2026-09-10",
        "forecast_end_date": "2026-09-15",
        "actual_end_date": None,
        "completion_percent": 50,
        "is_blocked": False,
    }
    with pytest.raises(ValidationError):
        DeliveryTask.model_validate(payload | overrides)


def test_legacy_dependency_keeps_missing_schedule_metadata_visible() -> None:
    dependency = GovernedDependency(
        dependency_id="D-1",
        project_id="P-1",
        predecessor_type="Task",
        predecessor_id="T-1",
        successor_type="Task",
        successor_id="T-2",
        dependency_name="Synthetic edge",
        status="On Track",
        delay_days=0,
        criticality="High",
    )
    assert dependency.relationship_type is None
    assert dependency.lag_days is None
    assert dependency.schedule_data_complete is False


def test_dependency_rejects_partial_schedule_metadata() -> None:
    with pytest.raises(ValidationError):
        GovernedDependency(
            dependency_id="D-1",
            project_id="P-1",
            predecessor_type="Task",
            predecessor_id="T-1",
            successor_type="Task",
            successor_id="T-2",
            dependency_name="Synthetic edge",
            relationship_type="Finish-to-Start",
            status="On Track",
            delay_days=0,
            criticality="High",
        )


def test_zero_capacity_rejected() -> None:
    with pytest.raises(ValidationError):
        Resource.model_validate(
            {
                "resource_id": "RES-1",
                "resource_name": "Sam",
                "project_id": "P-1",
                "allocated_hours": "10",
                "capacity_hours": "0",
                "week_start_date": "2026-08-24",
            }
        )


def test_test_case_missing_evidence_flagged() -> None:
    test_case = TestCase.model_validate(
        {
            "test_case_id": "TC-1",
            "project_id": "P-1",
            "test_case_name": "Verify something",
            "status": "Failed",
            "owner": "Priya",
            "verification_evidence": "",
            "last_updated_date": "2026-07-19",
        }
    )
    assert test_case.has_verification_evidence is False


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Risk.model_validate(_valid_risk_row(unexpected="x"))


def test_copilot_response_forbids_extra_fields() -> None:
    payload = {
        "executive_summary": "s",
        "key_findings": [],
        "recommended_actions": [],
        "source_ids": [],
        "human_review_required": True,
        "disclaimer": "AI-generated decision-support draft; human review required.",
    }
    assert CopilotResponse.model_validate(payload).human_review_required is True
    with pytest.raises(ValidationError):
        CopilotResponse.model_validate({**payload, "hallucinated": 1})


def test_copilot_response_drops_citation_fields_echoed_into_prose() -> None:
    response = CopilotResponse.model_validate(
        {
            "executive_summary": "P-002 is red (valid_source_ids: P-002, R-201).",
            "key_findings": ["Supplier risk R-201 is open [source_ids: R-201]"],
            "recommended_actions": ["Review the supplier plan. source_ids: R-201"],
            "source_ids": ["P-002", "R-201"],
            "human_review_required": True,
            "disclaimer": "AI-generated decision-support draft; human review required.",
        }
    )
    assert response.executive_summary == "P-002 is red."
    assert response.key_findings == ["Supplier risk R-201 is open"]
    assert response.recommended_actions == ["Review the supplier plan."]
    assert response.source_ids == ["P-002", "R-201"]
