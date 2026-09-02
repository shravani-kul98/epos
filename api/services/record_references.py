"""Allocate readable references without modifying existing identifiers."""

import hashlib
from typing import Final

from sqlmodel import Session, SQLModel, select

from api.models import (
    ActionTable,
    AssumptionTable,
    ChangeRequestTable,
    DecisionTable,
    DeliverableTable,
    DependencyTable,
    GateCriterionTable,
    GateReviewTable,
    GateTable,
    IssueTable,
    MeetingNoteTable,
    MilestoneTable,
    ProjectTable,
    RequirementTable,
    ResourceTable,
    RiskTable,
    TaskTable,
    TestCaseTable,
    TraceLinkTable,
    WorkPackageTable,
)

# Reference prefix -> the table and identifier column it numbers.
_NUMBERED: Final[dict[str, tuple[type[SQLModel], str]]] = {
    "T": (TaskTable, "task_id"),
    "M": (MilestoneTable, "milestone_id"),
    "R": (RiskTable, "risk_id"),
    "A": (ActionTable, "action_id"),
    "DEC": (DecisionTable, "decision_id"),
    "REQ": (RequirementTable, "requirement_id"),
    "TL": (TraceLinkTable, "trace_link_id"),
    "ISS": (IssueTable, "issue_id"),
    "ASM": (AssumptionTable, "assumption_id"),
    "CR": (ChangeRequestTable, "change_request_id"),
    "G": (GateTable, "gate_id"),
    "GC": (GateCriterionTable, "criterion_id"),
    "GR": (GateReviewTable, "review_id"),
    "DEP": (DependencyTable, "dependency_id"),
    "WP": (WorkPackageTable, "work_package_id"),
    "DL": (DeliverableTable, "deliverable_id"),
    "TC": (TestCaseTable, "test_case_id"),
    "RES": (ResourceTable, "resource_id"),
    "MN": (MeetingNoteTable, "note_id"),
}


def next_reference(session: Session, project_id: str, kind: str) -> str:
    """Reserve the next project-local sequence within the caller's transaction."""
    session.exec(
        select(ProjectTable).where(ProjectTable.project_id == project_id).with_for_update()
    ).one()
    project_part = project_id
    if len(project_part) > 20:
        suffix = hashlib.sha256(project_id.encode()).hexdigest()[:6]
        project_part = f"{project_id[:12]}-{suffix}"
    prefix = f"{kind}-{project_part}-"
    table, id_field = _NUMBERED[kind]
    column = getattr(table, id_field)
    existing = session.exec(select(column).where(table.project_id == project_id)).all()
    numbers = [
        int(reference[len(prefix) :])
        for reference in existing
        if reference.startswith(prefix) and reference[len(prefix) :].isdigit()
    ]
    return f"{prefix}{max(numbers, default=0) + 1:03d}"
