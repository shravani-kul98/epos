"""Deterministic Data Confidence Score engine.

Calculates an explainable 0-100 Confidence score answering "can we trust the data behind the
Health score?" from validated synthetic portfolio data. All weights, thresholds and required-field
definitions come from ``src.scoring_rules`` (no duplicated constants). The engine reads
``PortfolioData`` as read-only, uses a caller-supplied ``as_of_date`` for all time-relative logic,
and performs no AI, network or file access.

Factor 4 is a "Prototype data-source availability assessment": it reports whether required tables
loaded, not a real integration-monitoring solution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src import scoring_rules as sr
from src.data_loader import PortfolioData, StatusAnomaly, find_status_anomaly_records
from src.schemas import (
    ConfidenceResult,
    DataQualityIssue,
    Severity,
)
from src.utils import clamp, confidence_band, days_between, reference_timestamp
from src.validators import DataValidationError, ensure_update_dates_not_future

_ACTION = sr.StatusDomain.ACTION
_REQUIREMENT = sr.StatusDomain.REQUIREMENT

# Ownership fields are scored only by Ownership Coverage, never by Data Completeness.
OWNERSHIP_FIELDS = frozenset({"owner", "mitigation_owner", "requested_by"})
# Completeness fields whose absence is treated as a High-severity data-quality issue.
CRITICAL_COMPLETENESS_FIELDS = frozenset(
    {
        "baseline_end_date",
        "forecast_end_date",
        "status_update_date",
        "baseline_date",
        "forecast_date",
        "probability",
        "impact",
    }
)


@dataclass
class _FactorOutcome:
    """The deterministic result of a single confidence factor."""

    score: float
    explanations: list[str]
    issues: list[DataQualityIssue] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)


def _issue(
    issue_type: str,
    severity: Severity,
    message: str,
    source_ids: list[str],
    remediation_hint: str,
) -> DataQualityIssue:
    return DataQualityIssue(
        issue_type=issue_type,
        severity=severity,
        message=message,
        source_ids=sorted(set(source_ids)),
        remediation_hint=remediation_hint,
    )


def _is_active_task(status: str) -> bool:
    return not sr.is_terminal_schedule_status(status)


def _is_active_requirement(status: str) -> bool:
    return sr.normalize_status(status, _REQUIREMENT) in sr.ACTIVE_REQUIREMENT_STATUSES


def _is_active_action(status: str) -> bool:
    return sr.normalize_status(status, _ACTION) not in sr.TERMINAL_ACTION_STATUSES


def _is_open_risk(status: str) -> bool:
    return sr.is_active_risk_status(status)


def _is_active_change_request(status: str) -> bool:
    return status.strip().lower() != "rejected"


def _record_is_stale(last_updated: date | None, as_of_date: date) -> bool:
    """A record is stale if its update date is missing or older than the stale-age threshold."""
    if last_updated is None:
        return True
    return days_between(last_updated, as_of_date) > sr.STALE_RECORD_AGE_DAYS


def _stale_percentage_penalty(percentage: float) -> int:
    for max_percentage, penalty in sr.STALE_RECORD_PENALTY_THRESHOLDS:
        if percentage <= max_percentage:
            return penalty
    return sr.STALE_RECORD_BEYOND_PENALTY


def _completeness_score(missing_percentage: float) -> int:
    for max_percentage, score in sr.COMPLETENESS_SCORE_THRESHOLDS:
        if missing_percentage <= max_percentage:
            return score
    return sr.COMPLETENESS_BEYOND_SCORE


def _data_freshness(project, tasks, requirements, test_cases, as_of_date: date) -> _FactorOutcome:
    score = float(sr.FACTOR_BASE_SCORE)
    explanations: list[str] = []
    issues: list[DataQualityIssue] = []
    source_ids: list[str] = []

    active_records: list[tuple[str, date | None]] = []
    active_records += [(t.task_id, t.last_updated_date) for t in tasks if _is_active_task(t.status)]
    active_records += [
        (r.requirement_id, r.last_updated_date)
        for r in requirements
        if _is_active_requirement(r.status)
    ]
    active_records += [(tc.test_case_id, tc.last_updated_date) for tc in test_cases]
    ensure_update_dates_not_future(
        [(project.project_id, project.status_update_date), *active_records], as_of_date
    )

    updated = project.status_update_date
    if updated is None:
        score -= sr.PROJECT_STATUS_MISSING_PENALTY
        source_ids.append(project.project_id)
        issues.append(
            _issue(
                "missing_status_update",
                "Critical",
                f"Project {project.project_id} has no recorded status update date.",
                [project.project_id],
                "Record a current project status update date.",
            )
        )
        explanations.append(
            f"Project {project.project_id} has no status update date "
            f"(-{sr.PROJECT_STATUS_MISSING_PENALTY})."
        )
    else:
        age = days_between(updated, as_of_date)
        band = sr.classify_freshness(age)
        penalty = 0
        severity: Severity = "Low"
        if band == sr.FRESHNESS_STALE:
            penalty, severity = sr.PROJECT_STATUS_STALE_PENALTY, "Low"
        elif band == sr.FRESHNESS_SIGNIFICANTLY_STALE:
            penalty, severity = sr.PROJECT_STATUS_SIGNIFICANT_PENALTY, "Medium"
        elif band == sr.FRESHNESS_CRITICALLY_STALE:
            penalty, severity = sr.PROJECT_STATUS_CRITICAL_PENALTY, "High"
        if penalty > 0:
            score -= penalty
            source_ids.append(project.project_id)
            issues.append(
                _issue(
                    "stale_status_update",
                    severity,
                    f"Project {project.project_id} status was last updated {age} calendar "
                    "days ago.",
                    [project.project_id],
                    "Request a current project status update.",
                )
            )
            explanations.append(
                f"Project {project.project_id} status is {age} calendar days old (-{penalty})."
            )
        else:
            explanations.append(
                f"Project {project.project_id} status is {age} calendar days old (fresh)."
            )

    if active_records:
        stale = [
            (rid, updated_at)
            for rid, updated_at in active_records
            if _record_is_stale(updated_at, as_of_date)
        ]
        percentage = len(stale) / len(active_records) * 100
        penalty = _stale_percentage_penalty(percentage)
        if penalty > 0:
            score -= penalty
        for rid, updated_at in stale:
            source_ids.append(rid)
            if updated_at is None:
                issues.append(
                    _issue(
                        "missing_last_updated",
                        "Medium",
                        f"Active record {rid} has no last updated date.",
                        [rid],
                        "Record a current last-updated date for the record.",
                    )
                )
            else:
                issues.append(
                    _issue(
                        "stale_record",
                        "Low",
                        f"Active record {rid} was last updated "
                        f"{days_between(updated_at, as_of_date)} calendar days ago.",
                        [rid],
                        "Refresh the record so it is updated within 7 days.",
                    )
                )
        explanations.append(
            f"{len(stale)} of {len(active_records)} active records are stale "
            f"({percentage:.1f}%) (-{penalty})."
        )
    else:
        explanations.append("No active task, requirement or test-case records to assess freshness.")

    return _FactorOutcome(clamp(score), explanations, issues, source_ids)


def _required_non_ownership_fields(entity_key: str) -> tuple[str, ...]:
    return tuple(f for f in sr.REQUIRED_FIELDS[entity_key] if f not in OWNERSHIP_FIELDS)


def _data_completeness(
    project,
    milestones,
    tasks,
    risks,
    actions,
    requirements,
    test_cases,
    status_anomalies: list[StatusAnomaly],
) -> _FactorOutcome:
    explanations: list[str] = []
    issues: list[DataQualityIssue] = []
    source_ids: list[str] = []

    groups: list[tuple[str, str, str, list, str]] = [
        ("project", "projects", "project_id", [project], "Project"),
        ("milestone", "milestones", "milestone_id", list(milestones), "Milestone"),
        ("task", "tasks", "task_id", [t for t in tasks if _is_active_task(t.status)], "Task"),
        ("risk", "risks", "risk_id", [r for r in risks if _is_open_risk(r.status)], "Risk"),
        (
            "action",
            "actions",
            "action_id",
            [a for a in actions if _is_active_action(a.status)],
            "Action",
        ),
        (
            "requirement",
            "requirements",
            "requirement_id",
            [r for r in requirements if _is_active_requirement(r.status)],
            "Requirement",
        ),
        ("test_case", "test_cases", "test_case_id", list(test_cases), "Test case"),
    ]

    anomaly_by_field = {
        (anomaly.source, anomaly.record_id, anomaly.field_name): anomaly
        for anomaly in status_anomalies
    }
    evaluated_fields: set[tuple[str, str, str]] = set()
    total = 0
    missing = 0
    for entity_key, source, id_attr, records, label in groups:
        fields = _required_non_ownership_fields(entity_key)
        for record in records:
            record_id = getattr(record, id_attr)
            for field_name in fields:
                total += 1
                field_key = (source, record_id, field_name)
                evaluated_fields.add(field_key)
                anomaly = anomaly_by_field.get(field_key)
                if getattr(record, field_name) is None or anomaly is not None:
                    missing += 1
                    source_ids.append(record_id)
                    if anomaly is not None:
                        issues.append(
                            _issue(
                                "unrecognised_status",
                                "Medium",
                                f"{label} {record_id} has unrecognised {field_name} "
                                f"'{anomaly.value}'.",
                                [record_id],
                                f"Use a supported {field_name} for {label.lower()} {record_id}.",
                            )
                        )
                        continue
                    severity: Severity = (
                        "High" if field_name in CRITICAL_COMPLETENESS_FIELDS else "Medium"
                    )
                    issues.append(
                        _issue(
                            "missing_field",
                            severity,
                            f"{label} {record_id} is missing {field_name}.",
                            [record_id],
                            f"Populate {field_name} for {label.lower()} {record_id}.",
                        )
                    )

    for anomaly in status_anomalies:
        field_key = (anomaly.source, anomaly.record_id, anomaly.field_name)
        if field_key in evaluated_fields:
            continue
        total += 1
        missing += 1
        source_ids.append(anomaly.record_id)
        issues.append(
            _issue(
                "unrecognised_status",
                "Medium",
                f"{anomaly.source} record {anomaly.record_id} has unrecognised "
                f"{anomaly.field_name} '{anomaly.value}'.",
                [anomaly.record_id],
                f"Use a supported {anomaly.field_name} for record {anomaly.record_id}.",
            )
        )

    if total == 0:
        score = sr.FACTOR_BASE_SCORE
        explanations.append("No records to assess completeness.")
    else:
        missing_percentage = missing / total * 100
        score = _completeness_score(missing_percentage)
        explanations.append(
            f"{missing} of {total} required decision-support fields are missing "
            f"({missing_percentage:.1f}%); completeness score {score}."
        )

    # A plan with no tasks or milestones is scored from fallbacks, so it cannot be well evidenced.
    project_id = project.project_id
    for record_type, records in (("tasks", tasks), ("milestones", milestones), ("risks", risks)):
        if records:
            continue
        cap = sr.RECORD_COVERAGE_COMPLETENESS_CAPS[record_type]
        score = min(score, cap)
        explanations.append(
            f"No {record_type} are recorded for this project, so completeness is capped at {cap}."
        )
        issues.append(
            _issue(
                "record_type_missing",
                "High" if record_type != "risks" else "Medium",
                f"Project {project_id} has no {record_type} recorded.",
                [project_id],
                f"Record the project's {record_type} so its scores rest on evidence.",
            )
        )
        source_ids.append(project_id)
    return _FactorOutcome(float(score), explanations, issues, source_ids)


def _apply_ownership_rule(
    records: list,
    id_attr: str,
    owner_attr: str,
    penalty: int,
    cap: int,
    label: str,
) -> tuple[int, list[DataQualityIssue], list[str], int]:
    """Return (penalty_applied, issues, source_ids, missing_count) for one ownership rule."""
    missing = [r for r in records if getattr(r, owner_attr) is None]
    applied = min(len(missing) * penalty, cap)
    issues = [
        _issue(
            "missing_ownership",
            "Medium",
            f"{label} {getattr(r, id_attr)} has no {owner_attr}.",
            [getattr(r, id_attr)],
            f"Assign a {owner_attr} to {label.lower()} {getattr(r, id_attr)}.",
        )
        for r in missing
    ]
    source_ids = [getattr(r, id_attr) for r in missing]
    return applied, issues, source_ids, len(missing)


def _ownership_coverage(tasks, risks, actions, requirements, change_requests) -> _FactorOutcome:
    score = float(sr.FACTOR_BASE_SCORE)
    explanations: list[str] = []
    issues: list[DataQualityIssue] = []
    source_ids: list[str] = []

    rules = [
        (
            [t for t in tasks if _is_active_task(t.status)],
            "task_id",
            "owner",
            sr.OWNERSHIP_TASK_PENALTY,
            sr.OWNERSHIP_TASK_CAP,
            "Task",
        ),
        (
            [r for r in risks if _is_open_risk(r.status)],
            "risk_id",
            "mitigation_owner",
            sr.OWNERSHIP_RISK_PENALTY,
            sr.OWNERSHIP_RISK_CAP,
            "Risk",
        ),
        (
            [a for a in actions if _is_active_action(a.status)],
            "action_id",
            "owner",
            sr.OWNERSHIP_ACTION_PENALTY,
            sr.OWNERSHIP_ACTION_CAP,
            "Action",
        ),
        (
            [r for r in requirements if _is_active_requirement(r.status)],
            "requirement_id",
            "owner",
            sr.OWNERSHIP_REQUIREMENT_PENALTY,
            sr.OWNERSHIP_REQUIREMENT_CAP,
            "Requirement",
        ),
        (
            [c for c in change_requests if _is_active_change_request(c.status)],
            "change_request_id",
            "requested_by",
            sr.OWNERSHIP_CHANGE_REQUEST_PENALTY,
            sr.OWNERSHIP_CHANGE_REQUEST_CAP,
            "Change request",
        ),
    ]

    for records, id_attr, owner_attr, penalty, cap, label in rules:
        applied, rule_issues, rule_sources, missing_count = _apply_ownership_rule(
            records, id_attr, owner_attr, penalty, cap, label
        )
        if missing_count > 0:
            score -= applied
            issues += rule_issues
            source_ids += rule_sources
            explanations.append(
                f"{missing_count} active {label.lower()}(s) lack {owner_attr} (-{applied})."
            )

    if not explanations:
        explanations.append("All active records have owners.")
    return _FactorOutcome(clamp(score), explanations, issues, source_ids)


def _source_reliability(project_id: str, portfolio: PortfolioData) -> _FactorOutcome:
    """Prototype data-source availability assessment (not real integration monitoring)."""
    missing_critical = [
        name for name in ("milestones", "tasks", "risks") if not getattr(portfolio, name)
    ]
    missing_optional = [name for name in sr.OPTIONAL_TABLES if not getattr(portfolio, name)]

    if missing_critical:
        return _FactorOutcome(
            float(sr.SOURCE_RELIABILITY_CRITICAL_MISSING),
            [
                f"{sr.SOURCE_AVAILABILITY_LABEL}: critical table(s) unavailable "
                f"({', '.join(missing_critical)}); source reliability "
                f"{sr.SOURCE_RELIABILITY_CRITICAL_MISSING}."
            ],
            [
                _issue(
                    "critical_source_unavailable",
                    "High",
                    f"Critical source table(s) unavailable: {', '.join(missing_critical)}.",
                    [project_id],
                    "Restore the missing critical source table(s) before relying on this data.",
                )
            ],
            [project_id],
        )
    if missing_optional:
        return _FactorOutcome(
            float(sr.SOURCE_RELIABILITY_OPTIONAL_MISSING),
            [
                f"{sr.SOURCE_AVAILABILITY_LABEL}: optional table(s) unavailable "
                f"({', '.join(missing_optional)}); source reliability "
                f"{sr.SOURCE_RELIABILITY_OPTIONAL_MISSING}."
            ],
            [
                _issue(
                    "optional_source_unavailable",
                    "Low",
                    f"Optional source table(s) unavailable: {', '.join(missing_optional)}.",
                    [project_id],
                    "Provide the optional source table(s) to improve source reliability.",
                )
            ],
            [project_id],
        )
    return _FactorOutcome(
        float(sr.SOURCE_RELIABILITY_ALL_OK),
        [f"{sr.SOURCE_AVAILABILITY_LABEL}: all source tables available; source reliability 100."],
    )


def weighted_confidence_score(factor_scores: dict[str, float]) -> float:
    """Combine four factor scores using the central confidence weights, clamped to [0, 100]."""
    if set(factor_scores) != set(sr.CONFIDENCE_FACTORS):
        raise ValueError(
            f"factor_scores keys {sorted(factor_scores)} must equal {sorted(sr.CONFIDENCE_FACTORS)}"
        )
    total = sum(
        sr.CONFIDENCE_WEIGHTS[factor] * factor_scores[factor] for factor in sr.CONFIDENCE_FACTORS
    )
    return clamp(total)


def _ordered_issues(issues: list[DataQualityIssue]) -> list[DataQualityIssue]:
    """Deduplicate and stably sort issues by severity, type, first source id and message."""
    seen: set[tuple[str, str, tuple[str, ...], str]] = set()
    unique: list[DataQualityIssue] = []
    for issue in issues:
        key = (issue.issue_type, issue.severity, tuple(issue.source_ids), issue.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    unique.sort(
        key=lambda i: (
            -sr.SEVERITY_ORDER[i.severity],
            i.issue_type,
            i.source_ids[0] if i.source_ids else "",
            i.message,
        )
    )
    return unique


def calculate_project_confidence(
    project_id: str, portfolio: PortfolioData, as_of_date: date
) -> ConfidenceResult:
    """Calculate the deterministic Data Confidence score for a single project.

    Raises:
        DataValidationError: If ``project_id`` is not present in the portfolio.
    """
    project = portfolio.get_project(project_id)
    if project is None:
        raise DataValidationError([f"unknown project_id '{project_id}'"])

    milestones = [m for m in portfolio.milestones if m.project_id == project_id]
    tasks = [t for t in portfolio.tasks if t.project_id == project_id]
    risks = [r for r in portfolio.risks if r.project_id == project_id]
    actions = [a for a in portfolio.actions if a.project_id == project_id]
    requirements = [r for r in portfolio.requirements if r.project_id == project_id]
    test_cases = [t for t in portfolio.test_cases if t.project_id == project_id]
    change_requests = [c for c in portfolio.change_requests if c.project_id == project_id]
    status_anomalies = [
        anomaly
        for anomaly in find_status_anomaly_records(portfolio)
        if anomaly.project_id == project_id
    ]

    outcomes: dict[str, _FactorOutcome] = {
        "data_freshness": _data_freshness(project, tasks, requirements, test_cases, as_of_date),
        "data_completeness": _data_completeness(
            project,
            milestones,
            tasks,
            risks,
            actions,
            requirements,
            test_cases,
            status_anomalies,
        ),
        "ownership_coverage": _ownership_coverage(
            tasks, risks, actions, requirements, change_requests
        ),
        "source_reliability": _source_reliability(project_id, portfolio),
    }

    factor_scores = {name: round(outcome.score, 2) for name, outcome in outcomes.items()}
    factor_explanations = {name: outcome.explanations for name, outcome in outcomes.items()}
    overall = round(weighted_confidence_score({n: o.score for n, o in outcomes.items()}), 2)

    issues = _ordered_issues([issue for outcome in outcomes.values() for issue in outcome.issues])
    source_ids = sorted(
        {project_id}
        | {sid for outcome in outcomes.values() for sid in outcome.source_ids}
        | {sid for issue in issues for sid in issue.source_ids}
    )
    limitations = [
        "Confidence is prototype data-quality logic, not a validated data-governance model.",
        f"Source reliability is a {sr.SOURCE_AVAILABILITY_LABEL.lower()}",
    ]

    return ConfidenceResult(
        project_id=project_id,
        overall_score=overall,
        confidence_band=confidence_band(overall),
        factor_scores=factor_scores,
        factor_weights=dict(sr.CONFIDENCE_WEIGHTS),
        factor_explanations=factor_explanations,
        data_quality_issues=issues,
        source_ids=source_ids,
        as_of_date=as_of_date,
        calculated_at=reference_timestamp(as_of_date),
        assumptions_or_limitations=limitations,
    )


def calculate_portfolio_confidence(
    portfolio: PortfolioData, as_of_date: date
) -> list[ConfidenceResult]:
    """Calculate Confidence for every project, ordered by project id."""
    return [
        calculate_project_confidence(project.project_id, portfolio, as_of_date)
        for project in sorted(portfolio.projects, key=lambda p: p.project_id)
    ]
