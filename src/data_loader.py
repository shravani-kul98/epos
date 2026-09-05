"""Load and validate portfolio CSV data into typed Pydantic models.

The public entry point is :func:`load_portfolio`. Data access is deliberately hidden behind
the :class:`DataRepository` interface so a future SQLite/PostgreSQL backend can replace CSV
loading without changing any engine or UI code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ValidationError

from src import config
from src.delivery_rules import (
    SCHEDULABLE_ENDPOINT_TYPES,
    DeliveryNetworkError,
    DependencyEdge,
    DependencyEndpointType,
    ensure_acyclic_dependency_network,
)
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
from src.scoring_rules import StatusDomain, is_known_status
from src.validators import (
    DataValidationError,
    check_required_columns,
    find_duplicate_ids,
    validate_referential_integrity,
)


@dataclass(frozen=True)
class _CsvSpec:
    """Maps one CSV file to its model and primary-key column."""

    filename: str
    model: type[BaseModel]
    id_column: str


# Order matters: projects first so child referential checks can use its ids.
_CSV_SPECS: dict[str, _CsvSpec] = {
    "projects": _CsvSpec("projects.csv", Project, "project_id"),
    "milestones": _CsvSpec("milestones.csv", Milestone, "milestone_id"),
    "tasks": _CsvSpec("tasks.csv", Task, "task_id"),
    "risks": _CsvSpec("risks.csv", Risk, "risk_id"),
    "dependencies": _CsvSpec("dependencies.csv", Dependency, "dependency_id"),
    "actions": _CsvSpec("actions.csv", Action, "action_id"),
    "resources": _CsvSpec("resources.csv", Resource, "resource_id"),
    "requirements": _CsvSpec("requirements.csv", Requirement, "requirement_id"),
    "test_cases": _CsvSpec("test_cases.csv", TestCase, "test_case_id"),
    "trace_links": _CsvSpec("trace_links.csv", TraceLink, "trace_link_id"),
    "change_requests": _CsvSpec("change_requests.csv", ChangeRequest, "change_request_id"),
}


@dataclass
class PortfolioData:
    """In-memory, validated portfolio dataset."""

    projects: list[Project] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    trace_links: list[TraceLink] = field(default_factory=list)
    change_requests: list[ChangeRequest] = field(default_factory=list)
    # Data-quality metadata: status/priority values that did not map to canonical vocabulary.
    status_anomalies: list[str] = field(default_factory=list)

    @property
    def project_ids(self) -> set[str]:
        """Set of all known project ids."""
        return {project.project_id for project in self.projects}

    def get_project(self, project_id: str) -> Project | None:
        """Return the project with ``project_id`` or None if absent."""
        return next((p for p in self.projects if p.project_id == project_id), None)


@dataclass(frozen=True)
class StatusAnomaly:
    """One project-scoped controlled-vocabulary value that could not be normalized."""

    source: str
    project_id: str
    record_id: str
    field_name: str
    value: str

    @property
    def message(self) -> str:
        """Return the legacy human-readable anomaly text."""
        return (
            f"{self.source}: {self.record_id} has unrecognised {self.field_name} " f"'{self.value}'"
        )


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV as strings, keeping blanks as empty strings (not NaN)."""
    if not path.exists():
        raise DataValidationError([f"missing data file: {path.name}"])
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _parse_rows(df: pd.DataFrame, spec: _CsvSpec) -> list[BaseModel]:
    """Validate every row of ``df`` into ``spec.model``; aggregate row errors."""
    models: list[BaseModel] = []
    issues: list[str] = []
    for position, row in enumerate(df.to_dict(orient="records"), start=2):  # +2 for header/1-index
        try:
            models.append(spec.model.model_validate(row))
        except ValidationError as exc:
            issues.append(f"{spec.filename} row {position}: {exc.error_count()} error(s) - {exc}")
    if issues:
        raise DataValidationError(issues)
    return models


class DataRepository(ABC):
    """Abstract portfolio data source (CSV now, database later)."""

    @abstractmethod
    def load_portfolio(self) -> PortfolioData:
        """Load, validate and return the full portfolio dataset."""


class CsvDataRepository(DataRepository):
    """Load portfolio data from CSV files in a directory."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else config.DATA_DIR

    def load_portfolio(self) -> PortfolioData:
        """Read every CSV, validate structure and referential integrity, return typed data."""
        frames: dict[str, pd.DataFrame] = {}
        structural_issues: list[str] = []

        for key, spec in _CSV_SPECS.items():
            df = _read_csv(self.data_dir / spec.filename)
            # Only fields without a default are required columns. Optional fields carried from
            # persistence, such as recorded lag, are absent from CSV by design.
            required = [
                name for name, field in spec.model.model_fields.items() if field.is_required()
            ]
            structural_issues += check_required_columns(df, required, spec.filename)
            structural_issues += find_duplicate_ids(df, spec.id_column, spec.filename)
            frames[key] = df

        if structural_issues:
            raise DataValidationError(structural_issues)

        parsed = {key: _parse_rows(frames[key], _CSV_SPECS[key]) for key in _CSV_SPECS}
        portfolio = PortfolioData(**parsed)  # type: ignore[arg-type]

        self._check_referential_integrity(portfolio)
        portfolio.status_anomalies = find_status_anomalies(portfolio)
        return portfolio

    @staticmethod
    def _check_referential_integrity(portfolio: PortfolioData) -> None:
        """Ensure every child ``project_id`` and change-request requirement exists."""
        project_ids = portfolio.project_ids
        milestone_projects = {
            milestone.milestone_id: milestone.project_id for milestone in portfolio.milestones
        }
        task_projects = {task.task_id: task.project_id for task in portfolio.tasks}
        requirement_projects = {
            requirement.requirement_id: requirement.project_id
            for requirement in portfolio.requirements
        }
        issues: list[str] = []

        child_groups: list[tuple[str, list[str]]] = [
            ("milestones.csv", [m.project_id for m in portfolio.milestones]),
            ("tasks.csv", [t.project_id for t in portfolio.tasks]),
            ("risks.csv", [r.project_id for r in portfolio.risks]),
            ("dependencies.csv", [d.project_id for d in portfolio.dependencies]),
            ("actions.csv", [a.project_id for a in portfolio.actions]),
            ("resources.csv", [r.project_id for r in portfolio.resources]),
            ("requirements.csv", [r.project_id for r in portfolio.requirements]),
            ("test_cases.csv", [t.project_id for t in portfolio.test_cases]),
            ("trace_links.csv", [t.project_id for t in portfolio.trace_links]),
            ("change_requests.csv", [c.project_id for c in portfolio.change_requests]),
        ]
        for source_name, child_ids in child_groups:
            issues += validate_referential_integrity(
                child_ids, project_ids, source_name, "project_id"
            )

        issues += validate_referential_integrity(
            [c.requirement_id for c in portfolio.change_requests],
            set(requirement_projects),
            "change_requests.csv",
            "requirement_id",
        )
        issues += [
            (
                f"change_requests.csv: change request '{change_request.change_request_id}' "
                f"references requirement '{change_request.requirement_id}' outside project "
                f"'{change_request.project_id}'"
            )
            for change_request in portfolio.change_requests
            if change_request.requirement_id in requirement_projects
            and requirement_projects[change_request.requirement_id] != change_request.project_id
        ]
        issues += [
            (
                f"tasks.csv: task '{task.task_id}' references milestone "
                f"'{task.milestone_id}' outside project '{task.project_id}'"
            )
            for task in portfolio.tasks
            if milestone_projects.get(task.milestone_id) != task.project_id
        ]
        dependency_edges: dict[str, list[DependencyEdge]] = {}
        endpoint_projects = {
            DependencyEndpointType.TASK: task_projects,
            DependencyEndpointType.MILESTONE: milestone_projects,
        }
        for dependency in portfolio.dependencies:
            try:
                predecessor_type = DependencyEndpointType(dependency.predecessor_type)
                successor_type = DependencyEndpointType(dependency.successor_type)
            except ValueError:
                issues.append(
                    f"dependencies.csv: dependency '{dependency.dependency_id}' has an "
                    "unsupported endpoint type"
                )
                continue

            edge = DependencyEdge(
                dependency_id=dependency.dependency_id,
                predecessor_type=predecessor_type,
                predecessor_id=dependency.predecessor_id,
                successor_type=successor_type,
                successor_id=dependency.successor_id,
            )
            for endpoint_type, endpoint_id in (
                (predecessor_type, dependency.predecessor_id),
                (successor_type, dependency.successor_id),
            ):
                if (
                    endpoint_type in SCHEDULABLE_ENDPOINT_TYPES
                    and endpoint_projects[endpoint_type].get(endpoint_id) != dependency.project_id
                ):
                    issues.append(
                        f"dependencies.csv: dependency '{dependency.dependency_id}' references "
                        f"{endpoint_type.value} '{endpoint_id}' outside project "
                        f"'{dependency.project_id}'"
                    )
            dependency_edges.setdefault(dependency.project_id, []).append(edge)

        for project_id, edges in dependency_edges.items():
            try:
                ensure_acyclic_dependency_network(edges)
            except DeliveryNetworkError as exc:
                issues.append(f"dependencies.csv: project '{project_id}': {exc}")

        if issues:
            raise DataValidationError(issues)


def load_portfolio(data_dir: Path | str | None = None) -> PortfolioData:
    """Convenience loader using the CSV repository."""
    return CsvDataRepository(data_dir).load_portfolio()


def find_status_anomaly_records(portfolio: PortfolioData) -> list[StatusAnomaly]:
    """Return structured status/priority values outside the canonical vocabulary."""
    checks: list[tuple[str, list, str, str, StatusDomain]] = [
        ("projects", portfolio.projects, "project_id", "business_priority", StatusDomain.PRIORITY),
        ("milestones", portfolio.milestones, "milestone_id", "status", StatusDomain.SCHEDULE),
        ("milestones", portfolio.milestones, "milestone_id", "criticality", StatusDomain.PRIORITY),
        ("tasks", portfolio.tasks, "task_id", "status", StatusDomain.SCHEDULE),
        ("risks", portfolio.risks, "risk_id", "status", StatusDomain.RISK),
        ("risks", portfolio.risks, "risk_id", "mitigation_status", StatusDomain.MITIGATION),
        (
            "dependencies",
            portfolio.dependencies,
            "dependency_id",
            "status",
            StatusDomain.DEPENDENCY,
        ),
        (
            "dependencies",
            portfolio.dependencies,
            "dependency_id",
            "criticality",
            StatusDomain.PRIORITY,
        ),
        ("actions", portfolio.actions, "action_id", "status", StatusDomain.ACTION),
        ("actions", portfolio.actions, "action_id", "priority", StatusDomain.PRIORITY),
        (
            "requirements",
            portfolio.requirements,
            "requirement_id",
            "status",
            StatusDomain.REQUIREMENT,
        ),
        (
            "requirements",
            portfolio.requirements,
            "requirement_id",
            "priority",
            StatusDomain.PRIORITY,
        ),
        ("test_cases", portfolio.test_cases, "test_case_id", "status", StatusDomain.TEST_CASE),
    ]
    anomalies: list[StatusAnomaly] = []
    for source, records, id_attr, field_attr, domain in checks:
        for record in records:
            value = getattr(record, field_attr)
            if value is None or is_known_status(value, domain):
                continue
            anomalies.append(
                StatusAnomaly(
                    source=source,
                    project_id=record.project_id,
                    record_id=getattr(record, id_attr),
                    field_name=field_attr,
                    value=value,
                )
            )
    return anomalies


def find_status_anomalies(portfolio: PortfolioData) -> list[str]:
    """Return an issue for every status/priority value outside the canonical vocabulary.

    Original source values are preserved on the models; this only reports anomalies as
    data-quality metadata so unknown statuses are never silently treated as healthy.
    """
    return [anomaly.message for anomaly in find_status_anomaly_records(portfolio)]
