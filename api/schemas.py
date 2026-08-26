"""Request and response models for the EPOS Next API.

Responses speak product language. Internal factor keys and alert types are translated in
``api/labels.py`` before they reach these models.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from api import clock
from src.delivery_rules import (
    DEPENDENCY_MAX_DELAY_DAYS,
    DEPENDENCY_MAX_LAG_DAYS,
    DependencyEndpointType,
    DependencyRelationshipType,
)
from src.gate_rules import (
    GateCriterionStatus,
    GateReadinessState,
    GateResult,
    GateReviewOutcome,
    GateStatus,
)
from src.project_assessment import ProjectAssessment
from src.schemas import ConfidenceBand, HealthBand, Severity
from src.scoring_rules import (
    CANONICAL_STATUSES,
    SCENARIO_CALCULATION_VERSION,
    SCENARIO_MAX_DELAY_DAYS,
    SCENARIO_MIN_DELAY_DAYS,
    ScenarioInterventionType,
    StatusDomain,
    normalize_status,
)
from src.workflow_rules import (
    MIN_DECISION_RATIONALE_LENGTH,
    ActionStatus,
    AssumptionStatus,
    DecisionStatus,
    IssueStatus,
)


class ApiModel(BaseModel):
    """Base for all API models: reject unexpected fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# Identifiers appear in URL paths and in cited evidence, so they stay URL- and citation-safe.
RecordId = Annotated[
    str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
]
ProjectId = Annotated[
    str, Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
]
PersonName = Annotated[str, Field(max_length=120)]
ExternalReference = Annotated[str, Field(min_length=1, max_length=100)]


def _vocabulary(domain: StatusDomain) -> AfterValidator:
    """Store only values the engines recognise, in their canonical spelling."""

    def canonical(value: str) -> str:
        result = normalize_status(value, domain)
        if result is None:
            raise ValueError("must be one of: " + ", ".join(CANONICAL_STATUSES[domain]))
        return result

    return AfterValidator(canonical)


def _not_after_today(value: date) -> date:
    """A reported date in the future would make every analysis of the project fail."""
    if value > clock.utc_today():
        raise ValueError("cannot be later than today")
    return value


def _code() -> object:
    return Field(min_length=1, max_length=50)


ScheduleStatus = Annotated[str, _code(), _vocabulary(StatusDomain.SCHEDULE)]
Priority = Annotated[str, _code(), _vocabulary(StatusDomain.PRIORITY)]
RiskStatus = Annotated[str, _code(), _vocabulary(StatusDomain.RISK)]
MitigationStatus = Annotated[str, _code(), _vocabulary(StatusDomain.MITIGATION)]
DependencyStatus = Annotated[str, _code(), _vocabulary(StatusDomain.DEPENDENCY)]
RequirementStatus = Annotated[str, _code(), _vocabulary(StatusDomain.REQUIREMENT)]
ReportedDate = Annotated[date, AfterValidator(_not_after_today)]
DecisionRationale = Annotated[str, Field(min_length=MIN_DECISION_RATIONALE_LENGTH, max_length=1000)]
TaskReviewStatus = Literal["Pending review", "Accepted", "Returned"]


class VersionedOut(ApiModel):
    """Concurrency token returned for mutable records."""

    row_version: int | None = Field(default=None, ge=1)


class VersionedUpdate(ApiModel):
    """Expected record version required for a safe update."""

    non_nullable_fields: ClassVar[frozenset[str]] = frozenset()
    row_version: int = Field(ge=1)

    @model_validator(mode="before")
    @classmethod
    def reject_null_for_required_fields(cls, value: object) -> object:
        """Reject explicit nulls for columns that persistence requires."""
        if isinstance(value, dict):
            null_fields = sorted(
                field
                for field in cls.non_nullable_fields
                if field in value and value[field] is None
            )
            if null_fields:
                raise ValueError(f"{', '.join(null_fields)} cannot be null")
        return value


# --------------------------------------------------------------------------- shared
class FactorBreakdown(ApiModel):
    """One scored factor, expressed for a human reader."""

    key: str
    label: str
    description: str
    score: float
    weight: float
    weighted_contribution: float
    explanations: list[str]


class DriverOut(ApiModel):
    """A factor that materially reduced a score."""

    factor_label: str
    severity: Severity
    message: str
    source_ids: list[str]
    score_impact_description: str


class DataQualityIssueOut(ApiModel):
    issue_type: str
    severity: Severity
    message: str
    source_ids: list[str]
    remediation_hint: str


class HealthOut(ApiModel):
    project_id: str
    score: float
    band: HealthBand
    factors: list[FactorBreakdown]
    critical_drivers: list[DriverOut]
    source_ids: list[str]
    as_of_date: date
    calculated_at: datetime
    assumptions_or_limitations: list[str]


class ConfidenceOut(ApiModel):
    project_id: str
    score: float
    band: ConfidenceBand
    factors: list[FactorBreakdown]
    data_quality_issues: list[DataQualityIssueOut]
    source_ids: list[str]
    as_of_date: date
    calculated_at: datetime
    assumptions_or_limitations: list[str]


class AlertOut(ApiModel):
    alert_id: str
    project_id: str
    severity: Severity
    alert_type: str
    alert_type_label: str
    title: str
    explanation: str
    source_ids: list[str]
    recommended_next_step: str
    as_of_date: date
    detected_at: datetime


# --------------------------------------------------------------------------- entities
class ProjectOut(VersionedOut):
    project_id: str
    project_name: str
    domain: str
    project_manager: str
    start_date: date
    baseline_end_date: date | None
    forecast_end_date: date | None
    status_update_date: date | None
    project_phase: str
    business_priority: str


class ProjectCreate(ApiModel):
    project_id: ProjectId
    project_name: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=100)
    project_manager: str = Field(min_length=1, max_length=100)
    project_manager_user_id: int | None = Field(default=None, gt=0, strict=True)
    start_date: date
    baseline_end_date: date | None = None
    forecast_end_date: date | None = None
    status_update_date: ReportedDate | None = None
    project_phase: str = Field(min_length=1, max_length=100)
    business_priority: Priority


class ProjectUpdate(VersionedUpdate):
    non_nullable_fields = frozenset(
        {
            "project_name",
            "domain",
            "project_manager",
            "start_date",
            "project_phase",
            "business_priority",
        }
    )
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = Field(default=None, min_length=1, max_length=100)
    project_manager: str | None = Field(default=None, min_length=1, max_length=100)
    project_manager_user_id: int | None = Field(default=None, gt=0, strict=True)
    start_date: date | None = None
    baseline_end_date: date | None = None
    forecast_end_date: date | None = None
    status_update_date: ReportedDate | None = None
    project_phase: str | None = Field(default=None, min_length=1, max_length=100)
    business_priority: Priority | None = None


class MilestoneOut(VersionedOut):
    milestone_id: str
    project_id: str
    milestone_name: str
    baseline_date: date | None
    forecast_date: date | None
    actual_date: date | None
    forecast_variance_days: int | None
    actual_variance_days: int | None
    status: str
    criticality: str
    owner: str | None


class MilestoneCreate(ApiModel):
    milestone_id: RecordId | None = None
    project_id: RecordId
    milestone_name: str = Field(min_length=1, max_length=200)
    baseline_date: date | None = None
    forecast_date: date | None = None
    actual_date: date | None = None
    status: ScheduleStatus
    criticality: Priority
    owner: PersonName | None = None


class MilestoneUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"milestone_name", "status", "criticality"})
    milestone_name: str | None = Field(default=None, min_length=1, max_length=200)
    baseline_date: date | None = None
    forecast_date: date | None = None
    actual_date: date | None = None
    status: ScheduleStatus | None = None
    criticality: Priority | None = None
    owner: PersonName | None = None


class GateOut(VersionedOut):
    gate_id: str
    project_id: str
    milestone_id: str | None
    gate_name: str
    sequence: int
    planned_review_date: date
    actual_review_date: date | None
    owner: str
    status: GateStatus
    review_cycle: int
    result: GateResult | None
    applicable_baseline: str | None


class GateCreate(ApiModel):
    """A new Gate. Omit ``gate_id`` or ``sequence`` to receive the next ones in the project."""

    gate_id: RecordId | None = None
    project_id: RecordId
    milestone_id: RecordId | None = None
    gate_name: str = Field(min_length=1, max_length=200)
    sequence: int | None = Field(default=None, gt=0)
    planned_review_date: date
    owner: str = Field(min_length=1, max_length=100)
    applicable_baseline: str | None = Field(default=None, max_length=200)


class GateUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"gate_name", "sequence", "planned_review_date", "owner"})
    milestone_id: RecordId | None = None
    gate_name: str | None = Field(default=None, min_length=1, max_length=200)
    sequence: int | None = Field(default=None, gt=0)
    planned_review_date: date | None = None
    owner: str | None = Field(default=None, min_length=1, max_length=100)
    applicable_baseline: str | None = Field(default=None, max_length=200)


class GateTransitionRequest(VersionedUpdate):
    target_status: GateStatus
    rationale: str = Field(min_length=1, max_length=2000)


class GateCriterionOut(VersionedOut):
    criterion_id: str
    gate_id: str
    project_id: str
    criterion_type: Literal["Entry", "Exit"]
    criterion_name: str
    description: str
    is_mandatory: bool
    evidence_required: bool
    status: GateCriterionStatus
    evidence_reference: str | None
    assessment_rationale: str | None
    assessed_by: str | None
    assessed_at: datetime | None


class GateCriterionCreate(ApiModel):
    criterion_id: RecordId | None = None
    criterion_type: Literal["Entry", "Exit"]
    criterion_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    is_mandatory: bool = True
    evidence_required: bool = False


class GateCriterionUpdate(VersionedUpdate):
    non_nullable_fields = frozenset(
        {
            "criterion_type",
            "criterion_name",
            "description",
            "is_mandatory",
            "evidence_required",
        }
    )
    criterion_type: Literal["Entry", "Exit"] | None = None
    criterion_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    is_mandatory: bool | None = None
    evidence_required: bool | None = None


class GateCriterionAssessmentRequest(VersionedUpdate):
    target_status: Literal[GateCriterionStatus.MET, GateCriterionStatus.NOT_MET]
    rationale: str = Field(min_length=1, max_length=2000)
    evidence_reference: str | None = Field(default=None, max_length=2000)


class GateReviewOut(ApiModel):
    review_id: str
    gate_id: str
    project_id: str
    reviewer: str
    review_cycle: int
    outcome: GateReviewOutcome
    rationale: str
    conditions: str | None
    reviewed_at: datetime
    created_by: str


class GateReviewCreate(ApiModel):
    review_id: RecordId | None = None
    outcome: GateReviewOutcome
    rationale: str = Field(min_length=1, max_length=2000)
    conditions: str | None = Field(default=None, max_length=2000)

    @field_validator("conditions")
    @classmethod
    def normalize_blank_conditions(cls, value: str | None) -> str | None:
        return value or None


class GateReadinessFindingOut(ApiModel):
    message: str
    source_ids: list[str]


class GateReadinessOut(ApiModel):
    gate_id: str
    project_id: str
    state: GateReadinessState
    percentage: int | None
    complete_criterion_ids: list[str]
    incomplete_criterion_ids: list[str]
    blockers: list[GateReadinessFindingOut]
    warnings: list[GateReadinessFindingOut]
    evidence_references: list[str]
    latest_review_id: str | None
    latest_review_outcome: GateReviewOutcome | None
    calculated_at: datetime
    methodology_version: str
    applicable_baseline: str | None


class WorkPackageOut(VersionedOut):
    work_package_id: str
    project_id: str
    work_package_name: str
    description: str
    owner: str | None
    accountable_owner: str | None
    status: str
    priority: str


class WorkPackageCreate(ApiModel):
    work_package_id: RecordId | None = None
    project_id: RecordId
    work_package_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    owner: PersonName | None = None
    accountable_owner: PersonName | None = None
    status: str = Field(min_length=1, max_length=50)
    priority: str = Field(min_length=1, max_length=50)


class WorkPackageUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"work_package_name", "description", "status", "priority"})
    work_package_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    owner: PersonName | None = None
    accountable_owner: PersonName | None = None
    status: str | None = Field(default=None, min_length=1, max_length=50)
    priority: str | None = Field(default=None, min_length=1, max_length=50)


class DeliverableOut(VersionedOut):
    deliverable_id: str
    project_id: str
    work_package_id: str
    deliverable_name: str
    description: str
    owner: str | None
    accountable_owner: str | None
    status: str
    priority: str
    acceptance_criteria: str | None
    completion_evidence: str | None


class DeliverableCreate(ApiModel):
    deliverable_id: RecordId | None = None
    project_id: RecordId
    work_package_id: RecordId
    deliverable_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    owner: PersonName | None = None
    accountable_owner: PersonName | None = None
    status: str = Field(min_length=1, max_length=50)
    priority: str = Field(min_length=1, max_length=50)
    acceptance_criteria: str | None = Field(default=None, max_length=4000)
    completion_evidence: str | None = Field(default=None, max_length=4000)


class DeliverableUpdate(VersionedUpdate):
    non_nullable_fields = frozenset(
        {"work_package_id", "deliverable_name", "description", "status", "priority"}
    )
    work_package_id: RecordId | None = None
    deliverable_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    owner: PersonName | None = None
    accountable_owner: PersonName | None = None
    status: str | None = Field(default=None, min_length=1, max_length=50)
    priority: str | None = Field(default=None, min_length=1, max_length=50)
    acceptance_criteria: str | None = Field(default=None, max_length=4000)
    completion_evidence: str | None = Field(default=None, max_length=4000)


class TaskOut(VersionedOut):
    task_id: str
    project_id: str
    milestone_id: str
    deliverable_id: str | None
    parent_task_id: str | None
    task_name: str
    owner: str | None
    owner_user_id: int | None
    status: str
    planned_start_date: date | None
    forecast_start_date: date | None
    actual_start_date: date | None
    planned_end_date: date
    forecast_end_date: date
    actual_end_date: date | None
    forecast_start_variance_days: int | None
    forecast_finish_variance_days: int
    actual_start_variance_days: int | None
    actual_finish_variance_days: int | None
    completion_percent: int
    is_blocked: bool
    last_updated_date: date | None
    review_required: bool = False
    review_status: TaskReviewStatus | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    assignment_status: Literal["Pending", "Accepted", "Declined"] | None = None
    assignment_responded_at: datetime | None = None
    assignment_note: str | None = None


class TaskAssignmentResponse(VersionedUpdate):
    """The assignee's answer to an assignment. Declining must say why."""

    decision: Literal["accept", "decline"]
    note: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def declining_has_a_reason(self) -> TaskAssignmentResponse:
        if self.decision == "decline" and not (self.note and self.note.strip()):
            raise ValueError("Say why you are declining so the work can be reassigned.")
        return self


class TaskCreate(ApiModel):
    """A new task. Its reporting date is always stamped by the server."""

    task_id: RecordId | None = None
    project_id: RecordId
    milestone_id: RecordId
    deliverable_id: RecordId | None = None
    parent_task_id: RecordId | None = None
    task_name: str = Field(min_length=1, max_length=200)
    owner: PersonName | None = None
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    status: str = Field(min_length=1, max_length=50)
    planned_start_date: date | None = None
    forecast_start_date: date | None = None
    actual_start_date: date | None = None
    planned_end_date: date
    forecast_end_date: date
    actual_end_date: date | None = None
    completion_percent: int = Field(ge=0, le=100)
    is_blocked: bool = False
    review_required: bool = False


class TaskUpdate(VersionedUpdate):
    """Task changes. The reporting date is always stamped by the server.

    ``progress_note`` is the reporter's own account of the update. It is kept in the task's
    history with the changes it explains, not stored as a field of the task.
    """

    non_nullable_fields = frozenset(
        {
            "milestone_id",
            "task_name",
            "status",
            "planned_end_date",
            "forecast_end_date",
            "completion_percent",
            "is_blocked",
            "review_required",
        }
    )
    milestone_id: RecordId | None = None
    deliverable_id: RecordId | None = None
    parent_task_id: RecordId | None = None
    task_name: str | None = Field(default=None, min_length=1, max_length=200)
    owner: PersonName | None = None
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    status: str | None = Field(default=None, min_length=1, max_length=50)
    planned_start_date: date | None = None
    forecast_start_date: date | None = None
    actual_start_date: date | None = None
    planned_end_date: date | None = None
    forecast_end_date: date | None = None
    actual_end_date: date | None = None
    completion_percent: int | None = Field(default=None, ge=0, le=100)
    is_blocked: bool | None = None
    review_required: bool | None = None
    progress_note: str | None = Field(default=None, min_length=1, max_length=1000)


class TaskCompletionRequest(VersionedUpdate):
    """Completion of a task, optionally with the assignee's note on what was delivered."""

    progress_note: str | None = Field(default=None, min_length=1, max_length=1000)


class TaskReviewRequest(VersionedUpdate):
    """A manager's decision on reported completion. Returning work must say why."""

    decision: Literal["accept", "return"]
    note: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def returned_work_has_a_reason(self) -> TaskReviewRequest:
        if self.decision == "return" and not (self.note and self.note.strip()):
            raise ValueError("Say what needs to change before returning the task.")
        return self


class RiskOut(VersionedOut):
    risk_id: str
    project_id: str
    risk_name: str
    probability: int
    impact: int
    severity_score: int
    status: str
    mitigation_owner: str | None
    mitigation_owner_user_id: int | None = None
    mitigation_status: str | None
    due_date: date


class RiskCreate(ApiModel):
    """A new risk. Omit ``risk_id`` to receive the next project reference."""

    risk_id: RecordId | None = None
    project_id: RecordId
    risk_name: str = Field(min_length=1, max_length=200)
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    status: RiskStatus
    mitigation_owner: PersonName | None = None
    mitigation_owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    mitigation_status: MitigationStatus | None = None
    due_date: date


class RiskUpdate(VersionedUpdate):
    """Risk changes. Closing or accepting a risk requires the reasoning behind it."""

    non_nullable_fields = frozenset({"risk_name", "probability", "impact", "status", "due_date"})
    risk_name: str | None = Field(default=None, min_length=1, max_length=200)
    probability: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    status: RiskStatus | None = None
    mitigation_owner: PersonName | None = None
    mitigation_owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    mitigation_status: MitigationStatus | None = None
    due_date: date | None = None
    rationale: str | None = Field(default=None, min_length=1, max_length=1000)


class ActionOut(VersionedOut):
    action_id: str
    project_id: str
    action_description: str
    owner: str | None
    owner_user_id: int | None = None
    due_date: date
    status: ActionStatus
    priority: str
    source_reference: str | None


class ActionCreate(ApiModel):
    action_id: RecordId | None = None
    project_id: RecordId
    action_description: str = Field(min_length=1, max_length=500)
    owner: PersonName | None = None
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    due_date: date
    status: Literal["Open"] = "Open"
    priority: Priority
    source_reference: str | None = Field(default=None, max_length=500)


class ActionUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"action_description", "due_date", "priority"})
    action_description: str | None = Field(default=None, min_length=1, max_length=500)
    owner: PersonName | None = None
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    due_date: date | None = None
    priority: Priority | None = None
    source_reference: str | None = Field(default=None, max_length=500)


class ActionTransitionRequest(VersionedUpdate):
    """Starting an action needs no reason; every other step records one."""

    target_status: ActionStatus
    rationale: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def reason_unless_starting(self) -> ActionTransitionRequest:
        if self.target_status is not ActionStatus.IN_PROGRESS and not (
            self.rationale and self.rationale.strip()
        ):
            raise ValueError("Record the reason for this change.")
        return self


class IssueOut(VersionedOut):
    issue_id: str
    project_id: str
    title: str
    description: str
    severity: Severity
    owner: str | None
    owner_user_id: int | None = None
    status: IssueStatus
    raised_date: date
    target_resolution_date: date | None
    resolution_summary: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    source_reference: str | None


class IssueCreate(ApiModel):
    issue_id: RecordId | None = None
    project_id: RecordId
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    severity: Severity
    owner: str | None = Field(default=None, max_length=100)
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    raised_date: date
    target_resolution_date: date | None = None
    source_reference: str | None = Field(default=None, max_length=500)


class IssueUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"title", "description", "severity"})
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    severity: Severity | None = None
    owner: str | None = Field(default=None, max_length=100)
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    target_resolution_date: date | None = None
    source_reference: str | None = Field(default=None, max_length=500)


class IssueTransitionRequest(VersionedUpdate):
    """Starting work on an open issue needs no reason; every other step records one."""

    target_status: IssueStatus
    rationale: str | None = Field(default=None, min_length=1, max_length=2000)


class AssumptionOut(VersionedOut):
    assumption_id: str
    project_id: str
    assumption_text: str
    owner: str
    owner_user_id: int | None = None
    status: AssumptionStatus
    validation_due_date: date | None
    impact_if_false: str | None
    validation_evidence: str | None
    validated_by: str | None
    validated_at: datetime | None
    source_reference: str | None


class AssumptionCreate(ApiModel):
    assumption_id: RecordId | None = None
    project_id: RecordId
    assumption_text: str = Field(min_length=1, max_length=2000)
    owner: str = Field(min_length=1, max_length=100)
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    validation_due_date: date | None = None
    impact_if_false: str | None = Field(default=None, max_length=1000)
    source_reference: str | None = Field(default=None, max_length=500)


class AssumptionUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"assumption_text", "owner"})
    assumption_text: str | None = Field(default=None, min_length=1, max_length=2000)
    owner: str | None = Field(default=None, min_length=1, max_length=100)
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    validation_due_date: date | None = None
    impact_if_false: str | None = Field(default=None, max_length=1000)
    source_reference: str | None = Field(default=None, max_length=500)


class AssumptionTransitionRequest(VersionedUpdate):
    target_status: AssumptionStatus
    evidence: str = Field(min_length=1, max_length=2000)


class RequirementOut(VersionedOut):
    requirement_id: str
    project_id: str
    requirement_text: str
    requirement_type: str
    priority: str
    status: str
    owner: str | None
    last_updated_date: date | None


class RequirementCreate(ApiModel):
    """A new requirement. Its reporting date is always stamped by the server."""

    requirement_id: RecordId | None = None
    project_id: RecordId
    requirement_text: str = Field(min_length=1, max_length=1000)
    requirement_type: str = Field(min_length=1, max_length=50)
    priority: Priority
    status: RequirementStatus
    owner: PersonName | None = None


class RequirementUpdate(VersionedUpdate):
    """Requirement changes. The reporting date is always stamped by the server."""

    non_nullable_fields = frozenset({"requirement_text", "requirement_type", "priority", "status"})
    requirement_text: str | None = Field(default=None, min_length=1, max_length=1000)
    requirement_type: str | None = Field(default=None, min_length=1, max_length=50)
    priority: Priority | None = None
    status: RequirementStatus | None = None
    owner: PersonName | None = None


class ChangeRequestOut(VersionedOut):
    change_request_id: str
    project_id: str
    requirement_id: str
    change_description: str
    reason: str
    priority: str
    status: str
    requested_by: str | None
    requested_date: date


class ChangeRequestCreate(ApiModel):
    """A raised change. The requester is always the signed-in account."""

    change_request_id: RecordId | None = None
    project_id: RecordId
    requirement_id: RecordId
    change_description: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=500)
    priority: Priority
    status: Literal["Raised", "Open"] = "Raised"
    requested_date: date


class ChangeRequestUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"change_description", "reason", "priority", "requested_date"})
    change_description: str | None = Field(default=None, min_length=1, max_length=1000)
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    priority: Priority | None = None
    requested_date: date | None = None


class ChangeDecision(StrEnum):
    """The outcome of reviewing a change request."""

    APPROVED = "Approved"
    REJECTED = "Rejected"


class ChangeDecisionRequest(VersionedUpdate):
    """A recorded approval or rejection, with the reasoning behind it."""

    decision: ChangeDecision
    rationale: DecisionRationale


# --------------------------------------------------------------------------- decisions
class DecisionOut(VersionedOut):
    decision_id: str
    project_id: str
    title: str
    description: str
    category: str
    decision_date: date
    owner: str
    status: DecisionStatus
    rationale: str | None
    delivery_impact: str | None
    related_milestone_id: str | None
    related_risk_id: str | None
    related_change_request_id: str | None
    related_requirement_id: str | None
    approver: str | None
    approval_date: date | None
    notes: str | None


class DecisionCreate(ApiModel):
    """A proposed decision. Status and approver are never accepted from the client.

    Omit ``decision_id`` to receive the next project reference.
    """

    decision_id: RecordId | None = None
    project_id: RecordId
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    category: str = Field(min_length=1, max_length=100)
    decision_date: date
    owner: str = Field(min_length=1, max_length=100)
    rationale: str | None = Field(default=None, max_length=2000)
    delivery_impact: str | None = Field(default=None, max_length=1000)
    related_milestone_id: RecordId | None = None
    related_risk_id: RecordId | None = None
    related_change_request_id: RecordId | None = None
    related_requirement_id: RecordId | None = None
    notes: str | None = Field(default=None, max_length=2000)


class DecisionUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"title", "description", "category", "decision_date", "owner"})
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    decision_date: date | None = None
    owner: str | None = Field(default=None, min_length=1, max_length=100)
    rationale: str | None = Field(default=None, max_length=2000)
    delivery_impact: str | None = Field(default=None, max_length=1000)
    related_milestone_id: RecordId | None = None
    related_risk_id: RecordId | None = None
    related_change_request_id: RecordId | None = None
    related_requirement_id: RecordId | None = None
    notes: str | None = Field(default=None, max_length=2000)


class DecisionOutcome(StrEnum):
    """The outcome of reviewing a proposed decision."""

    APPROVED = "Approved"
    REJECTED = "Rejected"
    SUPERSEDED = "Superseded"


class DecisionOutcomeRequest(VersionedUpdate):
    """A recorded outcome. The rationale is mandatory so the reasoning survives."""

    outcome: DecisionOutcome
    rationale: DecisionRationale


# --------------------------------------------------------------------------- meeting notes
class MeetingNoteOut(VersionedOut):
    note_id: str
    project_id: str
    title: str
    meeting_date: date
    attendees: str | None
    body: str


class MeetingNoteCreate(ApiModel):
    """A captured meeting note. Omit ``note_id`` to receive the next project reference."""

    note_id: RecordId | None = None
    project_id: RecordId
    title: str = Field(min_length=1, max_length=200)
    meeting_date: date
    attendees: str | None = Field(default=None, max_length=500)
    body: str = Field(min_length=1, max_length=20000)


class MeetingNoteUpdate(VersionedUpdate):
    non_nullable_fields = frozenset({"title", "meeting_date", "body"})
    title: str | None = Field(default=None, min_length=1, max_length=200)
    meeting_date: date | None = None
    attendees: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, min_length=1, max_length=20000)


class MeetingNoteProposal(ApiModel):
    """A follow-up EPOS believes the note contains.

    A proposal is not a record. It names the line it was read from and the phrase that matched, so
    a reviewer can accept or dismiss it without opening the original note.
    """

    proposal_id: str
    kind: Literal["action", "risk", "decision"]
    text: str
    source_line_number: int
    source_line: str
    matched_phrase: str
    suggested_owner: str | None
    suggested_due_date: date | None


class MeetingNoteExtraction(ApiModel):
    """Everything read out of one note, with nothing created."""

    note_id: str
    project_id: str
    line_count: int
    proposals: list[MeetingNoteProposal]
    action_count: int
    risk_count: int
    decision_count: int


class MeetingNotePromotion(ApiModel):
    """A reviewer's confirmed instruction to turn one proposal into a real record.

    The reviewer sends the values they accepted rather than a reference to the proposal, because
    the record that gets created must be the one a person actually read.
    """

    kind: Literal["action", "risk", "decision"]
    text: str = Field(min_length=1, max_length=1000)
    owner: str = Field(min_length=1, max_length=100)
    owner_user_id: int | None = Field(default=None, gt=0, strict=True)
    due_date: date | None = None
    source_line_number: int = Field(ge=1)
    probability: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def assess_risks_explicitly(self) -> MeetingNotePromotion:
        """A promoted risk is scored, so its probability and impact must come from the reviewer."""
        assessed = self.probability is not None and self.impact is not None
        if self.kind == "risk" and not assessed:
            raise ValueError("A risk needs the reviewer's probability and impact.")
        if self.kind != "risk" and (self.probability is not None or self.impact is not None):
            raise ValueError("Probability and impact apply only to risks.")
        return self


class TestCaseOut(ApiModel):
    __test__ = False

    test_case_id: str
    project_id: str
    test_case_name: str
    status: str
    owner: str | None
    verification_evidence: str | None
    last_updated_date: date | None
    row_version: int | None = None


class TestCaseCreate(ApiModel):
    """A new test case. It starts as Not Run; results are recorded separately with evidence."""

    __test__ = False

    test_case_id: RecordId | None = None
    project_id: RecordId
    test_case_name: str = Field(min_length=1, max_length=200)
    owner: PersonName | None = None


class TestCaseResultUpdate(VersionedUpdate):
    """A recorded verification result. A pass must name the evidence that shows it."""

    __test__ = False

    status: Literal["Passed", "Failed", "Not Run"]
    verification_evidence: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def a_pass_names_its_evidence(self) -> TestCaseResultUpdate:
        if self.status == "Passed" and not (
            self.verification_evidence and self.verification_evidence.strip()
        ):
            raise ValueError("Name the verification evidence before recording a pass.")
        return self


class TraceLinkOut(VersionedOut):
    trace_link_id: str
    project_id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    link_type: str


class TraceLinkCreate(ApiModel):
    """Link a requirement to the work, test or milestone that realises it."""

    project_id: RecordId
    requirement_id: RecordId
    target_type: Literal["Task", "TestCase", "Milestone"]
    target_id: RecordId


class NotificationOut(ApiModel):
    id: int
    kind: str
    title: str
    detail: str | None
    project_id: str | None
    entity_type: str | None
    entity_id: str | None
    actor_name: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationSummary(ApiModel):
    unread: int


class DependencyOut(VersionedOut):
    dependency_id: str
    project_id: str
    predecessor_type: DependencyEndpointType
    predecessor_id: str
    successor_type: DependencyEndpointType
    successor_id: str
    dependency_name: str
    relationship_type: DependencyRelationshipType | None
    lag_days: int | None
    schedule_data_complete: bool
    status: str
    delay_days: int
    criticality: str


class DependencyCreate(ApiModel):
    dependency_id: RecordId | None = None
    project_id: RecordId
    predecessor_type: DependencyEndpointType
    predecessor_id: ExternalReference
    successor_type: DependencyEndpointType
    successor_id: ExternalReference
    dependency_name: str = Field(min_length=1, max_length=300)
    relationship_type: DependencyRelationshipType | None = None
    lag_days: int | None = Field(
        default=None, ge=-DEPENDENCY_MAX_LAG_DAYS, le=DEPENDENCY_MAX_LAG_DAYS
    )
    status: DependencyStatus
    delay_days: int = Field(ge=0, le=DEPENDENCY_MAX_DELAY_DAYS)
    criticality: Priority


class DependencyUpdate(VersionedUpdate):
    non_nullable_fields = frozenset(
        {
            "predecessor_type",
            "predecessor_id",
            "successor_type",
            "successor_id",
            "dependency_name",
            "status",
            "delay_days",
            "criticality",
        }
    )
    predecessor_type: DependencyEndpointType | None = None
    predecessor_id: ExternalReference | None = None
    successor_type: DependencyEndpointType | None = None
    successor_id: ExternalReference | None = None
    dependency_name: str | None = Field(default=None, min_length=1, max_length=300)
    relationship_type: DependencyRelationshipType | None = None
    lag_days: int | None = Field(
        default=None, ge=-DEPENDENCY_MAX_LAG_DAYS, le=DEPENDENCY_MAX_LAG_DAYS
    )
    status: DependencyStatus | None = None
    delay_days: int | None = Field(default=None, ge=0, le=DEPENDENCY_MAX_DELAY_DAYS)
    criticality: Priority | None = None


class ResourceOut(ApiModel):
    resource_id: str
    resource_name: str
    project_id: str
    allocated_hours: int
    capacity_hours: int
    utilisation_percent: float
    is_overallocated: bool
    week_start_date: date
    row_version: int | None = None


class ResourceCreate(ApiModel):
    """One person's allocation to a project for one week."""

    resource_id: RecordId | None = None
    project_id: RecordId
    resource_name: str = Field(min_length=1, max_length=120)
    allocated_hours: int = Field(ge=0, le=168)
    capacity_hours: int = Field(gt=0, le=168)
    week_start_date: date


class ResourceUpdate(VersionedUpdate):
    non_nullable_fields = frozenset(
        {"resource_name", "allocated_hours", "capacity_hours", "week_start_date"}
    )
    resource_name: str | None = Field(default=None, min_length=1, max_length=120)
    allocated_hours: int | None = Field(default=None, ge=0, le=168)
    capacity_hours: int | None = Field(default=None, gt=0, le=168)
    week_start_date: date | None = None


# --------------------------------------------------------------------------- analytics
class ProjectSummary(ApiModel):
    """One row of the portfolio table."""

    project_id: str
    project_name: str
    domain: str
    project_manager: str
    project_phase: str
    business_priority: str
    forecast_end_date: date | None
    health_score: float
    health_band: HealthBand
    confidence_score: float
    confidence_band: ConfidenceBand
    open_alert_count: int
    critical_alert_count: int
    needs_attention: bool = False
    assessment: ProjectAssessment | None = None


class BandCounts(ApiModel):
    green: int = 0
    amber: int = 0
    red: int = 0


class ConfidenceBandCounts(ApiModel):
    high: int = 0
    medium: int = 0
    low: int = 0


class SeverityCounts(ApiModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class PortfolioFilters(ApiModel):
    """Optional view filters over authorized records and already-calculated project results."""

    project_id: str | None = None
    health_band: HealthBand | None = None
    confidence_band: ConfidenceBand | None = None
    domain: str | None = None
    manager: str | None = None
    phase: str | None = None
    priority: str | None = None
    alert_severity: Severity | None = None
    forecast_after: date | None = None
    forecast_before: date | None = None
    needs_attention: bool | None = None


class PortfolioDashboard(ApiModel):
    """Portfolio overview.

    Reports tallies of engine-produced bands only. No portfolio-level score is invented here.
    """

    as_of_date: date
    project_count: int
    unassessed_count: int = 0
    health_bands: BandCounts
    confidence_bands: ConfidenceBandCounts
    alert_severities: SeverityCounts
    project_phases: dict[str, int] = Field(default_factory=dict)
    project_domains: dict[str, int] = Field(default_factory=dict)
    projects: list[ProjectSummary]
    top_alerts: list[AlertOut]


class ProjectDashboard(ApiModel):
    project: ProjectOut
    assessment: ProjectAssessment | None = None
    health: HealthOut
    confidence: ConfidenceOut
    alerts: list[AlertOut]


class TraceabilityRow(ApiModel):
    requirement_id: str
    requirement_text: str
    project_id: str
    requirement_status: str
    priority: str
    owner: str | None
    linked_test_case_ids: list[str]
    verified_test_case_ids: list[str]
    trace_status: str
    open_change_request_ids: list[str]


class TraceabilityMatrix(ApiModel):
    as_of_date: date
    project_id: str | None
    total_requirements: int
    status_counts: dict[str, int]
    coverage_percent: float
    rows: list[TraceabilityRow]


class ChangeImpactOut(ApiModel):
    change_request_id: str
    requirement_id: str
    affected_task_ids: list[str]
    affected_test_case_ids: list[str]
    affected_dependency_ids: list[str]
    affected_milestone_ids: list[str]
    estimated_schedule_impact_days: int
    risk_level: Severity
    explanation: str
    source_ids: list[str]
    as_of_date: date
    calculated_at: datetime
    assumptions_or_limitations: list[str]
    evidence_status: Literal["Assessed", "Insufficient evidence"] = "Assessed"


class ScenarioRequest(ApiModel):
    """Bounds mirror the scenario engine's own limits so the API cannot accept an input the
    engine would reject."""

    dependency_id: str = Field(min_length=1, max_length=100)
    additional_delay_days: int = Field(ge=SCENARIO_MIN_DELAY_DAYS, le=SCENARIO_MAX_DELAY_DAYS)


class ScenarioInterventionOut(ApiModel):
    intervention_type: ScenarioInterventionType
    target_id: str
    value: int
    unit: str
    note: str | None = None


class ScheduleMovementOut(ApiModel):
    record_type: str
    record_id: str
    record_name: str
    original_date: date
    scenario_date: date
    shift_days: int
    controlling_dependency_id: str | None = None
    controlling_predecessor_id: str | None = None
    propagation_hop: int


class ScenarioFactorDeltaOut(ApiModel):
    factor: str
    factor_label: str
    baseline_score: float
    scenario_score: float
    score_delta: float
    weight: float
    weighted_contribution: float


class ScenarioInterventionIn(ApiModel):
    """One requested change. Bounds are validated again by the engine before anything runs."""

    intervention_type: ScenarioInterventionType
    target_id: str = Field(min_length=1, max_length=100)
    value: int
    note: str | None = Field(default=None, max_length=500)


class ScenarioRunRequest(ApiModel):
    """A multi-event scenario. At least one intervention is required."""

    interventions: list[ScenarioInterventionIn] = Field(min_length=1, max_length=25)


class ScenarioSensitivityRequest(ApiModel):
    intervention_type: ScenarioInterventionType
    target_id: str = Field(min_length=1, max_length=100)
    values: list[int] | None = Field(default=None, max_length=25)


class ScenarioComparisonOut(ApiModel):
    project_id: str
    project_name: str
    baseline_health_score: float
    baseline_health_band: HealthBand
    scenario_health_score: float
    scenario_health_band: HealthBand
    health_score_delta: float
    baseline_confidence_score: float
    baseline_confidence_band: ConfidenceBand
    scenario_confidence_score: float
    scenario_confidence_band: ConfidenceBand
    confidence_score_delta: float
    baseline_alert_counts: SeverityCounts
    scenario_alert_counts: SeverityCounts
    new_alert_ids: list[str]
    resolved_alert_ids: list[str]
    changed_alert_ids: list[str]
    baseline_forecast_end_date: date | None = None
    scenario_forecast_end_date: date | None = None
    forecast_end_shift_days: int = 0
    factor_deltas: list[ScenarioFactorDeltaOut] = Field(default_factory=list)


class ScenarioInsightOut(ApiModel):
    kind: Literal["schedule", "score", "coverage", "review"]
    headline: str
    detail: str
    source_ids: list[str]
    project_id: str | None = None


class ScenarioOut(ApiModel):
    scenario_type: str
    dependency_id: str
    dependency_name: str
    additional_delay_days: int
    baseline_delay_days: int
    scenario_delay_days: int
    affected_projects: list[ScenarioComparisonOut]
    explanation: str
    source_ids: list[str]
    as_of_date: date
    calculated_at: datetime
    assumptions_or_limitations: list[str]
    interventions: list[ScenarioInterventionOut] = Field(default_factory=list)
    schedule_movements: list[ScheduleMovementOut] = Field(default_factory=list)
    decision_brief: list[ScenarioInsightOut] = Field(default_factory=list)
    calculation_version: str = SCENARIO_CALCULATION_VERSION


class ScenarioThresholdOut(ApiModel):
    outcome: str
    occurs_at_value: int | None
    unit: str
    tested_values: list[int]
    explanation: str


class ScenarioSensitivityOut(ApiModel):
    intervention_type: ScenarioInterventionType
    target_id: str
    project_id: str
    unit: str
    tested_values: list[int]
    health_scores: list[float]
    forecast_shift_days: list[int]
    is_responsive: bool
    saturated_at_value: int | None
    thresholds: list[ScenarioThresholdOut]
    assumptions_or_limitations: list[str]


# --------------------------------------------------------------------------- copilot
class CopilotAskRequest(ApiModel):
    question: str = Field(min_length=1, max_length=1000)
    project_id: str | None = Field(default=None, max_length=32)
    conversation_id: int | None = None
    reset_context: bool = False


class EvidenceRecordOut(ApiModel):
    record_type: str
    record_id: str
    fields: dict[str, str]


class ProjectReferenceOut(ApiModel):
    project_id: str
    project_name: str


class AppliedFilterOut(ApiModel):
    """A restriction applied to the answer, shown back so the reader can check or correct it."""

    field: str
    label: str
    values: list[str]
    excluded: bool = False
    interpreted_from: str | None = None


class CopilotAnswer(ApiModel):
    status: Literal["ok", "unavailable", "error", "invalid_response", "clarification"]
    matched_intent: str | None
    matched_question: str | None
    executive_summary: str
    key_findings: list[str]
    recommended_actions: list[str]
    source_ids: list[str]
    human_review_required: bool
    disclaimer: str
    warnings: list[str]
    evidence: list[EvidenceRecordOut]
    suggested_questions: list[str]
    conversation_id: int | None = None
    resolved_project_id: str | None = Field(default=None, exclude=True)
    context: dict[str, str] = Field(default_factory=dict)
    project_references: list[ProjectReferenceOut] = Field(default_factory=list)
    applied_filters: list[AppliedFilterOut] = Field(default_factory=list)
    unapplied_filters: list[str] = Field(default_factory=list)


class ConversationMessageOut(ApiModel):
    id: int
    role: str
    content: str
    matched_intent: str | None
    status: str | None
    source_ids: list[str]
    evidence: list[EvidenceRecordOut]
    created_at: datetime
    answer: CopilotAnswer | None = None


class ConversationSummary(ApiModel):
    id: int
    title: str
    project_id: str | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ApiModel):
    id: int
    title: str
    project_id: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageOut]
    context: dict[str, str] = Field(default_factory=dict)


class SupportedQuestion(ApiModel):
    intent: str
    question: str
    requires_context: str | None


# --------------------------------------------------------------------------- activity
class ActivityFieldChange(ApiModel):
    """One sanitized before/after value in an append-only activity event."""

    field: str
    label: str
    before: JsonValue
    after: JsonValue


class ActivityEventOut(ApiModel):
    id: int
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str
    project_id: str | None
    summary: str
    detail: str | None
    changes: list[ActivityFieldChange] | None
    actor_name: str | None
    headline: str


class TaskProgressEntry(ApiModel):
    """One recorded report on a task: who made it, what changed and, in their words, why."""

    id: int
    occurred_at: datetime
    action: str
    actor_name: str | None
    note: str | None
    changes: list[ActivityFieldChange]


# --------------------------------------------------------------------------- project delta
class ProjectDeltaEntry(ApiModel):
    """One record that moved inside the delta window."""

    entity_type: str
    entity_id: str
    change_type: Literal["added", "updated", "withdrawn"]
    headline: str
    status: str | None
    occurred_at: datetime
    actor_name: str | None


class ProjectDeltaGroup(ApiModel):
    """Changes of one kind, counted so a reader can skim before reading."""

    key: str
    label: str
    added: int
    updated: int
    withdrawn: int
    entries: list[ProjectDeltaEntry]


class ProjectDelta(ApiModel):
    """What changed on a project since a chosen moment.

    ``has_history`` is false when the project record itself was created inside the window. An empty
    or wholly "added" result should then be read as "there is no earlier state to compare against"
    rather than as a review delta.
    """

    project_id: str
    project_name: str
    since: datetime
    generated_at: datetime
    total_changes: int
    has_history: bool
    earliest_record_at: datetime | None
    groups: list[ProjectDeltaGroup]


# --------------------------------------------------------------------------- search
class SearchHit(ApiModel):
    """One record matching a workspace search, with where to find it."""

    record_type: str
    record_type_label: str
    record_id: str
    title: str
    subtitle: str | None
    status: str | None
    project_id: str
    project_name: str
    path: str


class SearchResults(ApiModel):
    """Search results, best match first.

    ``total`` counts every match, while ``hits`` holds only the page returned, so the interface can
    say how much was left out instead of implying the list is complete.
    """

    query: str
    total: int
    hits: list[SearchHit]


# --------------------------------------------------------------------------- executive report
class ExecutiveReportItem(ApiModel):
    """One statement in the report, with the records it was drawn from."""

    text: str
    source_ids: list[str]


class ExecutiveReportSection(ApiModel):
    """A themed part of the report. Sections with nothing to say are omitted rather than shown empty."""

    key: str
    title: str
    summary: str
    items: list[ExecutiveReportItem]


class ExecutiveReport(ApiModel):
    """The weekly executive report.

    Assembled on request from already-calculated scores and already-recorded history. Nothing here
    is generated text, so the report carries no review warning.
    """

    as_of_date: date
    window_days: int
    generated_at: datetime
    headline: str
    project_count: int
    health_bands: BandCounts
    confidence_bands: ConfidenceBandCounts
    alert_severities: SeverityCounts
    sections: list[ExecutiveReportSection]
    source_ids: list[str]


# --------------------------------------------------------------------------- meta
class HealthCheck(ApiModel):
    status: Literal["ok"]
    database_seeded: bool
    project_count: int
    ai_configured: bool
    analysis_date: date
    schema_current: bool = True


class ReadinessCheck(ApiModel):
    """Dependency-free liveness result. Carries the environment category and nothing else."""

    status: Literal["ok"]
    environment: str
    version: str
