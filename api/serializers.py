"""Convert validated entity models into API response models."""

from __future__ import annotations

from api.crud import to_entity
from api.models import ActionTable, GateTable, RiskTable, TaskTable
from api.schemas import (
    ActionOut,
    ChangeRequestOut,
    DependencyOut,
    GateOut,
    MilestoneOut,
    ProjectOut,
    RequirementOut,
    ResourceOut,
    RiskOut,
    TaskOut,
    TestCaseOut,
)
from src.delivery_rules import SCHEDULABLE_ENDPOINT_TYPES
from src.gate_rules import GateStatus, result_for_gate_status
from src.schemas import (
    Action,
    ChangeRequest,
    DeliveryMilestone,
    DeliveryTask,
    Dependency,
    GovernedDependency,
    Project,
    Requirement,
    Resource,
    Risk,
    TestCase,
)
from src.utils import safe_div


def project_out(project: Project, row_version: int | None = None) -> ProjectOut:
    return ProjectOut(**project.model_dump(), row_version=row_version)


def gate_out(row: GateTable) -> GateOut:
    """Present a Gate row, deriving the recorded result from its lifecycle status."""
    data = {field: getattr(row, field) for field in GateOut.model_fields if field != "result"}
    return GateOut.model_validate(
        {**data, "result": result_for_gate_status(GateStatus(row.status))}
    )


def milestone_out(milestone: DeliveryMilestone, row_version: int | None = None) -> MilestoneOut:
    return MilestoneOut(
        **milestone.model_dump(),
        forecast_variance_days=milestone.forecast_variance_days,
        actual_variance_days=milestone.actual_variance_days,
        row_version=row_version,
    )


def task_out(
    task: DeliveryTask,
    row_version: int | None = None,
    owner_user_id: int | None = None,
) -> TaskOut:
    return TaskOut(
        **{**task.model_dump(), "owner_user_id": owner_user_id},
        forecast_start_variance_days=task.forecast_start_variance_days,
        forecast_finish_variance_days=task.forecast_finish_variance_days,
        actual_start_variance_days=task.actual_start_variance_days,
        actual_finish_variance_days=task.actual_finish_variance_days,
        row_version=row_version,
    )


def risk_out(risk: Risk, row_version: int | None = None) -> RiskOut:
    """Include the derived severity score so the client never multiplies it itself."""
    return RiskOut(**risk.model_dump(), severity_score=risk.severity_score, row_version=row_version)


def action_out(action: Action, row_version: int | None = None) -> ActionOut:
    return ActionOut(**action.model_dump(), row_version=row_version)


def task_row_out(row: TaskTable) -> TaskOut:
    """A stored task with its assignee account and optional completion review."""
    return task_out(to_entity(row, DeliveryTask), row.row_version, row.owner_user_id).model_copy(
        update={
            "review_required": row.review_required,
            "review_status": row.review_status,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at,
            "review_note": row.review_note,
            "assignment_status": row.assignment_status,
            "assignment_responded_at": row.assignment_responded_at,
            "assignment_note": row.assignment_note,
        }
    )


def risk_row_out(row: RiskTable) -> RiskOut:
    """A stored risk with the account that owns its mitigation."""
    return risk_out(to_entity(row, Risk), row.row_version).model_copy(
        update={"mitigation_owner_user_id": row.mitigation_owner_user_id}
    )


def action_row_out(row: ActionTable) -> ActionOut:
    """A stored action with the account it is assigned to."""
    return action_out(to_entity(row, Action), row.row_version).model_copy(
        update={"owner_user_id": row.owner_user_id}
    )


def requirement_out(requirement: Requirement, row_version: int | None = None) -> RequirementOut:
    return RequirementOut(**requirement.model_dump(), row_version=row_version)


def change_request_out(
    change_request: ChangeRequest, row_version: int | None = None
) -> ChangeRequestOut:
    return ChangeRequestOut(**change_request.model_dump(), row_version=row_version)


def test_case_out(test_case: TestCase) -> TestCaseOut:
    return TestCaseOut(**test_case.model_dump())


def dependency_out(
    dependency: Dependency | GovernedDependency, row_version: int | None = None
) -> DependencyOut:
    if isinstance(dependency, GovernedDependency):
        return DependencyOut(
            **dependency.model_dump(),
            schedule_data_complete=dependency.schedule_data_complete,
            row_version=row_version,
        )
    schedulable = {endpoint.value for endpoint in SCHEDULABLE_ENDPOINT_TYPES}
    return DependencyOut(
        **dependency.model_dump(),
        schedule_data_complete=(
            dependency.predecessor_type in schedulable
            and dependency.successor_type in schedulable
            and dependency.relationship_type is not None
            and dependency.lag_days is not None
        ),
        row_version=row_version,
    )


def resource_out(resource: Resource, row_version: int | None = None) -> ResourceOut:
    """Include utilisation so capacity views never recompute it client-side."""
    utilisation = safe_div(resource.allocated_hours * 100, resource.capacity_hours, default=0.0)
    return ResourceOut(
        **resource.model_dump(),
        utilisation_percent=round(utilisation, 1),
        is_overallocated=resource.is_overallocated,
        row_version=row_version,
    )
