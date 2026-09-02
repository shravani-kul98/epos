"""One search across every record type in the workspace.

Search is a read of records the signed-in user is already allowed to see, so it applies the same
soft-delete rule as every other read and never returns a record the product would otherwise hide.
Ranking is deterministic: an exact identifier beats a prefix, a prefix beats a leading name match,
and a leading name match beats a match anywhere in the text. Nothing here is scored by a model.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlmodel import Session, SQLModel, select

from api.models import (
    ActionTable,
    AssumptionTable,
    AuditMixin,
    ChangeRequestTable,
    DecisionTable,
    DeliverableTable,
    DependencyTable,
    GateCriterionTable,
    GateTable,
    IssueTable,
    MeetingNoteTable,
    MilestoneTable,
    ProjectTable,
    RequirementTable,
    RiskTable,
    TaskTable,
    TestCaseTable,
    WorkPackageTable,
)
from api.schemas import SearchHit, SearchResults

EXACT_ID = 0
ID_PREFIX = 1
TITLE_PREFIX = 2
TITLE_CONTAINS = 3
SUBTITLE_CONTAINS = 4


class _Source(NamedTuple):
    """One record type that can be searched."""

    table: type[SQLModel]
    record_type: str
    label: str
    id_field: str
    title_field: str
    subtitle_fields: tuple[str, ...]
    status_field: str | None
    tab: str | None


_SOURCES: tuple[_Source, ...] = (
    _Source(
        ProjectTable,
        "project",
        "Project",
        "project_id",
        "project_name",
        ("domain", "project_manager"),
        "project_phase",
        None,
    ),
    _Source(
        MilestoneTable,
        "milestone",
        "Milestone",
        "milestone_id",
        "milestone_name",
        ("owner",),
        "status",
        "overview",
    ),
    _Source(
        GateTable,
        "gate",
        "Gate",
        "gate_id",
        "gate_name",
        ("owner", "applicable_baseline"),
        "status",
        "gates",
    ),
    _Source(
        GateCriterionTable,
        "gate_criterion",
        "Gate criterion",
        "criterion_id",
        "criterion_name",
        ("criterion_type", "gate_id"),
        "status",
        "gates",
    ),
    _Source(
        WorkPackageTable,
        "work_package",
        "Work Package",
        "work_package_id",
        "work_package_name",
        ("owner", "accountable_owner"),
        "status",
        "work",
    ),
    _Source(
        DeliverableTable,
        "deliverable",
        "Deliverable",
        "deliverable_id",
        "deliverable_name",
        ("owner", "accountable_owner"),
        "status",
        "work",
    ),
    _Source(TaskTable, "task", "Task", "task_id", "task_name", ("owner",), "status", "work"),
    _Source(
        RiskTable, "risk", "Risk", "risk_id", "risk_name", ("mitigation_owner",), "status", "risks"
    ),
    _Source(
        ActionTable,
        "action",
        "Action",
        "action_id",
        "action_description",
        ("owner",),
        "status",
        "work",
    ),
    _Source(
        RequirementTable,
        "requirement",
        "Requirement",
        "requirement_id",
        "requirement_text",
        ("requirement_type", "owner"),
        "status",
        "requirements",
    ),
    _Source(
        TestCaseTable,
        "test_case",
        "Test case",
        "test_case_id",
        "test_case_name",
        ("owner",),
        "status",
        "requirements",
    ),
    _Source(
        ChangeRequestTable,
        "change_request",
        "Change request",
        "change_request_id",
        "change_description",
        ("reason", "requested_by"),
        "status",
        "changes",
    ),
    _Source(
        DecisionTable,
        "decision",
        "Decision",
        "decision_id",
        "title",
        ("category", "owner"),
        "status",
        "decisions",
    ),
    _Source(IssueTable, "issue", "Issue", "issue_id", "title", ("owner",), "status", "issues"),
    _Source(
        AssumptionTable,
        "assumption",
        "Assumption",
        "assumption_id",
        "assumption_text",
        ("owner",),
        "status",
        "assumptions",
    ),
    _Source(
        DependencyTable,
        "dependency",
        "Dependency",
        "dependency_id",
        "dependency_name",
        ("predecessor_id", "successor_id"),
        "status",
        "work",
    ),
    _Source(
        MeetingNoteTable,
        "meeting_note",
        "Meeting note",
        "note_id",
        "title",
        ("attendees",),
        None,
        "meetings",
    ),
)


def _rank(needle: str, record_id: str, title: str, subtitle: str) -> int | None:
    """Score one record against the query, or return None when it does not match."""
    identifier = record_id.lower()
    if identifier == needle:
        return EXACT_ID
    if identifier.startswith(needle):
        return ID_PREFIX

    name = title.lower()
    if name.startswith(needle):
        return TITLE_PREFIX
    if needle in name:
        return TITLE_CONTAINS
    if needle in subtitle.lower():
        return SUBTITLE_CONTAINS
    return None


def _subtitle(row: SQLModel, fields: tuple[str, ...]) -> str:
    """Join the supporting fields that help a reader tell two similar records apart."""
    values = [str(getattr(row, field)) for field in fields if getattr(row, field, None)]
    return " · ".join(values)


def _path(source: _Source, row: SQLModel, project_id: str) -> str:
    """Where the record lives in the interface, so a hit is one click from being useful."""
    if source.record_type == "project":
        return f"/projects/{project_id}"
    return f"/projects/{project_id}?tab={source.tab}"


def search(
    session: Session,
    query: str,
    limit: int = 20,
    project_ids: set[str] | None = None,
) -> SearchResults:
    """Return the records matching ``query``, best match first.

    An empty or single-character query returns nothing rather than the whole workspace, because a
    result list that long is noise rather than an answer.
    """
    needle = query.strip().lower()
    if len(needle) < 2:
        return SearchResults(query=query.strip(), total=0, hits=[])

    names = {
        row.project_id: row.project_name
        for row in session.exec(select(ProjectTable)).all()
        if row.deleted_at is None and (project_ids is None or row.project_id in project_ids)
    }

    ranked: list[tuple[int, str, str, SearchHit]] = []
    for source in _SOURCES:
        statement = select(source.table)
        if issubclass(source.table, AuditMixin):
            statement = statement.where(source.table.deleted_at.is_(None))  # type: ignore[attr-defined]
        if project_ids is not None:
            statement = statement.where(
                source.table.project_id.in_(sorted(project_ids))  # type: ignore[attr-defined]
            )
        for row in session.exec(statement).all():
            row_project_id = str(getattr(row, "project_id", getattr(row, source.id_field)))
            record_id = str(getattr(row, source.id_field))
            title = str(getattr(row, source.title_field, "") or record_id)
            subtitle = _subtitle(row, source.subtitle_fields)
            rank = _rank(needle, record_id, title, subtitle)
            if rank is None:
                continue

            project_id = row_project_id
            ranked.append(
                (
                    rank,
                    source.record_type,
                    record_id,
                    SearchHit(
                        record_type=source.record_type,
                        record_type_label=source.label,
                        record_id=record_id,
                        title=" ".join(title.split()),
                        subtitle=subtitle or None,
                        status=(
                            str(getattr(row, source.status_field))
                            if source.status_field and getattr(row, source.status_field, None)
                            else None
                        ),
                        project_id=project_id,
                        project_name=names.get(project_id, project_id),
                        path=_path(source, row, project_id),
                    ),
                )
            )

    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return SearchResults(
        query=query.strip(),
        total=len(ranked),
        hits=[hit for _, _, _, hit in ranked[:limit]],
    )
