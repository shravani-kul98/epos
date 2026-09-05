"""Pydantic v2 models for EPOS Lite entities and deterministic result objects.

Entity models mirror the CSV schema (see ``docs/data-dictionary.md``). Result models are
the typed outputs of the deterministic engines and the AI layer. Keeping these together
gives a single, validated contract shared by the data layer, engines, UI and tests.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.delivery_rules import (
    SCHEDULABLE_ENDPOINT_TYPES,
    DeliveryNetworkError,
    DependencyEdge,
    DependencyEndpointType,
    DependencyRelationshipType,
    ensure_dependency_metadata,
)
from src.scoring_rules import (
    SCENARIO_CALCULATION_VERSION,
    SCENARIO_INTERVENTION_UNITS,
    ScenarioInterventionType,
)

# Constrained value sets kept as tuples for reuse in validation and docs.
CRITICALITY_VALUES = ("Low", "Medium", "High", "Critical")
SEVERITY_VALUES = ("Low", "Medium", "High", "Critical")

# Type aliases shared across result and alert models.
Severity = Literal["Low", "Medium", "High", "Critical"]
HealthBand = Literal["Green", "Amber", "Red"]
ConfidenceBand = Literal["High", "Medium", "Low"]
CopilotStatus = Literal["ok", "unavailable", "error", "invalid_response"]


class _Base(BaseModel):
    """Shared config: strip whitespace and forbid unexpected fields."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        """Treat empty/whitespace strings as missing so optional fields become None."""
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


# --------------------------------------------------------------------------- entities
class Project(_Base):
    project_id: str
    project_name: str
    domain: str
    project_manager: str
    start_date: date
    baseline_end_date: date | None = None
    forecast_end_date: date | None = None
    status_update_date: date | None = None
    project_phase: str
    business_priority: str


class Milestone(_Base):
    milestone_id: str
    project_id: str
    milestone_name: str
    baseline_date: date | None = None
    forecast_date: date | None = None
    status: str
    criticality: str
    owner: str | None = None


class Task(_Base):
    task_id: str
    project_id: str
    milestone_id: str
    task_name: str
    owner: str | None = None
    status: str
    planned_end_date: date
    forecast_end_date: date
    completion_percent: int = Field(ge=0, le=100)
    is_blocked: bool
    last_updated_date: date | None = None
    # Carried from persistence so scenario propagation can evidence free float. CSV data omits it.
    planned_start_date: date | None = None
    # Carried from persistence so account-based ownership survives into answers. CSV omits it.
    owner_user_id: int | None = None


class DeliveryMilestone(Milestone):
    """A persisted milestone with actual completion and deterministic variance facts."""

    actual_date: date | None = None

    @property
    def forecast_variance_days(self) -> int | None:
        """Signed forecast movement from baseline in calendar days."""
        if self.baseline_date is None or self.forecast_date is None:
            return None
        return (self.forecast_date - self.baseline_date).days

    @property
    def actual_variance_days(self) -> int | None:
        """Signed actual movement from baseline in calendar days."""
        if self.baseline_date is None or self.actual_date is None:
            return None
        return (self.actual_date - self.baseline_date).days


class DeliveryTask(Task):
    """A persisted task with planned, forecast, and actual schedule facts."""

    planned_start_date: date | None = None
    forecast_start_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    deliverable_id: str | None = None
    parent_task_id: str | None = None

    @model_validator(mode="after")
    def validate_schedule_order(self) -> Self:
        """Reject inverted planned, forecast, or actual date ranges."""
        date_ranges = (
            ("planned", self.planned_start_date, self.planned_end_date),
            ("forecast", self.forecast_start_date, self.forecast_end_date),
            ("actual", self.actual_start_date, self.actual_end_date),
        )
        for label, start, end in date_ranges:
            if start is not None and end is not None and end < start:
                raise ValueError(f"{label} end date cannot precede its start date")
        if self.actual_end_date is not None and self.actual_start_date is None:
            raise ValueError("actual end date requires an actual start date")
        return self

    @property
    def forecast_start_variance_days(self) -> int | None:
        """Signed forecast-start movement from plan in calendar days."""
        if self.planned_start_date is None or self.forecast_start_date is None:
            return None
        return (self.forecast_start_date - self.planned_start_date).days

    @property
    def forecast_finish_variance_days(self) -> int:
        """Signed forecast-finish movement from plan in calendar days."""
        return (self.forecast_end_date - self.planned_end_date).days

    @property
    def actual_start_variance_days(self) -> int | None:
        """Signed actual-start movement from plan in calendar days."""
        if self.planned_start_date is None or self.actual_start_date is None:
            return None
        return (self.actual_start_date - self.planned_start_date).days

    @property
    def actual_finish_variance_days(self) -> int | None:
        """Signed actual-finish movement from plan in calendar days."""
        if self.actual_end_date is None:
            return None
        return (self.actual_end_date - self.planned_end_date).days


class Risk(_Base):
    risk_id: str
    project_id: str
    risk_name: str
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    status: str
    mitigation_owner: str | None = None
    mitigation_status: str | None = None
    due_date: date

    @property
    def severity_score(self) -> int:
        """Deterministic risk severity in 1–25 (probability × impact)."""
        return self.probability * self.impact


class Dependency(_Base):
    dependency_id: str
    project_id: str
    predecessor_type: str
    predecessor_id: str
    successor_type: str
    successor_id: str
    dependency_name: str
    status: str
    delay_days: int = Field(ge=0)
    criticality: str
    # Carried from persistence so scenario propagation can honour lag. CSV data omits both.
    relationship_type: str | None = None
    lag_days: int | None = None


class GovernedDependency(Dependency):
    """A persisted dependency with explicit schedule relationship evidence."""

    predecessor_type: DependencyEndpointType
    successor_type: DependencyEndpointType
    relationship_type: DependencyRelationshipType | None = None
    lag_days: int | None = None

    @property
    def edge(self) -> DependencyEdge:
        """Return the normalized graph edge used by deterministic validation."""
        return DependencyEdge(
            dependency_id=self.dependency_id,
            predecessor_type=self.predecessor_type,
            predecessor_id=self.predecessor_id,
            successor_type=self.successor_type,
            successor_id=self.successor_id,
        )

    @model_validator(mode="after")
    def validate_relationship_metadata(self) -> Self:
        """Keep legacy incompleteness visible but reject contradictory metadata."""
        if self.successor_type not in SCHEDULABLE_ENDPOINT_TYPES:
            raise ValueError("dependency successor must be a Task or Milestone")
        try:
            ensure_dependency_metadata(
                self.edge,
                self.relationship_type,
                self.lag_days,
                require_complete=False,
            )
        except DeliveryNetworkError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @property
    def schedule_data_complete(self) -> bool:
        """True only when an internal edge has type and lag evidence."""
        return (
            self.predecessor_type in SCHEDULABLE_ENDPOINT_TYPES
            and self.successor_type in SCHEDULABLE_ENDPOINT_TYPES
            and self.relationship_type is not None
            and self.lag_days is not None
        )


class Action(_Base):
    action_id: str
    project_id: str
    action_description: str
    owner: str | None = None
    due_date: date
    status: str
    priority: str
    source_reference: str | None = None


class Resource(_Base):
    resource_id: str
    resource_name: str
    project_id: str
    allocated_hours: int = Field(ge=0)
    capacity_hours: int = Field(gt=0)
    week_start_date: date

    @property
    def is_overallocated(self) -> bool:
        """True when allocated hours exceed capacity for the week."""
        return self.allocated_hours > self.capacity_hours


class Requirement(_Base):
    requirement_id: str
    project_id: str
    requirement_text: str
    requirement_type: str
    priority: str
    status: str
    owner: str | None = None
    last_updated_date: date | None = None


class TestCase(_Base):
    test_case_id: str
    project_id: str
    test_case_name: str
    status: str
    owner: str | None = None
    verification_evidence: str | None = None
    last_updated_date: date | None = None

    # Prevent pytest from collecting this model as a test class.
    __test__ = False

    @property
    def has_verification_evidence(self) -> bool:
        """True when the test case records verification evidence."""
        return self.verification_evidence is not None


class TraceLink(_Base):
    trace_link_id: str
    project_id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    link_type: str


class ChangeRequest(_Base):
    change_request_id: str
    project_id: str
    requirement_id: str
    change_description: str
    reason: str
    priority: str
    status: str
    requested_by: str | None = None
    requested_date: date


# --------------------------------------------------------------------------- results
class CriticalDriver(BaseModel):
    """A structured, factual explanation of a factor that materially reduced health."""

    factor_name: str
    severity: Severity
    message: str
    source_ids: list[str]
    score_impact_description: str


class DataQualityIssue(BaseModel):
    """A structured description of a data-quality problem affecting confidence."""

    issue_type: str
    severity: Severity
    message: str
    source_ids: list[str]
    remediation_hint: str


class HealthResult(BaseModel):
    project_id: str
    overall_score: float
    health_band: HealthBand
    factor_scores: dict[str, float]
    factor_weights: dict[str, float]
    factor_explanations: dict[str, list[str]]
    critical_drivers: list[CriticalDriver]
    source_ids: list[str]
    as_of_date: date
    calculated_at: datetime
    assumptions_or_limitations: list[str]


class ConfidenceResult(BaseModel):
    project_id: str
    overall_score: float
    confidence_band: ConfidenceBand
    factor_scores: dict[str, float]
    factor_weights: dict[str, float]
    factor_explanations: dict[str, list[str]]
    data_quality_issues: list[DataQualityIssue]
    source_ids: list[str]
    as_of_date: date
    calculated_at: datetime
    assumptions_or_limitations: list[str]


class EarlyWarningAlert(BaseModel):
    """A deterministic project-control alert with evidence and a human-review action."""

    alert_id: str
    project_id: str
    severity: Severity
    alert_type: str
    title: str
    explanation: str
    source_ids: list[str]
    recommended_next_step: str
    as_of_date: date
    detected_at: datetime


class ChangeImpactResult(BaseModel):
    change_request_id: str
    requirement_id: str
    affected_task_ids: list[str]
    affected_test_case_ids: list[str]
    affected_dependency_ids: list[str]
    affected_milestone_ids: list[str]
    estimated_schedule_impact_days: int
    risk_level: Severity
    deterministic_explanation: str
    source_ids: list[str]
    as_of_date: date
    calculated_at: datetime
    assumptions_or_limitations: list[str]
    # "Insufficient evidence" when nothing downstream is traced: the Low level is then unassessed.
    evidence_status: Literal["Assessed", "Insufficient evidence"] = "Assessed"


class ScenarioIntervention(BaseModel):
    """One deterministic change a scenario applies to its own copy of the portfolio.

    ``target_id`` names an existing record; ``value`` carries the change in that intervention's
    documented unit. Nothing here is free text, so no model-authored content can reach the engines.
    """

    model_config = ConfigDict(extra="forbid")

    intervention_type: ScenarioInterventionType
    target_id: str
    value: int
    note: str | None = None

    @property
    def unit(self) -> str:
        return SCENARIO_INTERVENTION_UNITS[self.intervention_type]

    @property
    def describe(self) -> str:
        return f"{self.intervention_type.value} on {self.target_id} of {self.value} {self.unit}"


class ScheduleMovement(BaseModel):
    """One evidenced record movement, and the dependency that controlled it."""

    record_type: str
    record_id: str
    original_date: date
    scenario_date: date
    shift_days: int
    controlling_dependency_id: str | None = None
    controlling_predecessor_id: str | None = None
    propagation_hop: int


class ScenarioFactorDelta(BaseModel):
    """How one health factor contributed to the overall score movement."""

    factor: str
    baseline_score: float
    scenario_score: float
    score_delta: float
    weight: float
    weighted_contribution: float


class ScenarioProjectComparison(BaseModel):
    """Baseline versus scenario outcome for one project."""

    project_id: str
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
    baseline_alert_counts: dict[str, int]
    scenario_alert_counts: dict[str, int]
    new_alert_ids: list[str]
    resolved_alert_ids: list[str]
    changed_alert_ids: list[str]
    baseline_forecast_end_date: date | None = None
    scenario_forecast_end_date: date | None = None
    forecast_end_shift_days: int = 0
    factor_deltas: list[ScenarioFactorDelta] = Field(default_factory=list)


class ScenarioInsight(BaseModel):
    """A deterministic interpretation with the records needed to review it."""

    kind: Literal["schedule", "score", "coverage", "review"]
    headline: str
    detail: str
    source_ids: list[str]
    project_id: str | None = None


class ScenarioResult(BaseModel):
    """A non-mutating what-if simulation compared against the baseline."""

    scenario_type: str
    dependency_id: str
    additional_delay_days: int
    baseline_delay_days: int
    scenario_delay_days: int
    affected_projects: list[ScenarioProjectComparison]
    deterministic_explanation: str
    source_ids: list[str]
    as_of_date: date
    calculated_at: datetime
    assumptions_or_limitations: list[str]
    interventions: list[ScenarioIntervention] = Field(default_factory=list)
    schedule_movements: list[ScheduleMovement] = Field(default_factory=list)
    decision_brief: list[ScenarioInsight] = Field(default_factory=list)
    calculation_version: str = SCENARIO_CALCULATION_VERSION


class ScenarioThreshold(BaseModel):
    """The smallest tested input at which a named outcome first occurs."""

    outcome: str
    occurs_at_value: int | None
    unit: str
    tested_values: list[int]
    observed_scores: list[float]
    explanation: str


class ScenarioSensitivity(BaseModel):
    """Deterministic response of one project to a range of values for one intervention."""

    intervention_type: ScenarioInterventionType
    target_id: str
    project_id: str
    unit: str
    tested_values: list[int]
    health_scores: list[float]
    forecast_shift_days: list[int]
    is_responsive: bool
    saturated_at_value: int | None
    thresholds: list[ScenarioThreshold]
    assumptions_or_limitations: list[str]


class EvidenceRecord(BaseModel):
    """One structured record included in an AI evidence package."""

    record_type: str
    record_id: str
    fields: dict[str, str]


class EvidencePackage(BaseModel):
    """The selected, validated evidence sent to the AI layer for one question."""

    question_type: str
    as_of_date: date
    context: dict[str, str]
    records: list[EvidenceRecord]
    source_ids: list[str]


class CopilotResponse(BaseModel):
    """Strict structured contract for every GPT-4o response.

    The model authors only the six content fields; ``status`` and ``warnings`` are set by the
    application and are never requested from the model.
    """

    model_config = ConfigDict(extra="forbid")

    executive_summary: str
    key_findings: list[str]
    recommended_actions: list[str]
    source_ids: list[str]
    human_review_required: bool
    disclaimer: str
    status: CopilotStatus = "ok"
    warnings: list[str] = Field(default_factory=list)

    @field_validator("executive_summary", mode="after")
    @classmethod
    def _clean_summary(cls, value: str) -> str:
        return strip_citation_markup(value)

    @field_validator("key_findings", "recommended_actions", mode="after")
    @classmethod
    def _clean_items(cls, values: list[str]) -> list[str]:
        return [strip_citation_markup(value) for value in values]


# Models sometimes echo the request's citation field into their prose, e.g. "(valid_source_ids:
# A-1, B-2)". Citations belong in ``source_ids`` only, so the echo is removed from what people read.
_CITATION_MARKUP = re.compile(
    r"\s*[\(\[]\s*(?:valid_)?source_ids?\s*:[^\)\]]*[\)\]]|\s*\b(?:valid_)?source_ids?\s*:\s*[\w\-, ]+$",
    re.IGNORECASE,
)


def strip_citation_markup(text: str) -> str:
    """Remove echoed citation fields from model-written prose."""
    cleaned = _CITATION_MARKUP.sub("", text)
    return re.sub(r"\s+([.,;:])", r"\1", cleaned).strip()
