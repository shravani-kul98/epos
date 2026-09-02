"""What changed on a project since a chosen moment.

The delta is derived from the audit columns every business record already carries, enriched with
the activity trail for who made the change. Nothing new is stored: a delta is a reading of history,
not a snapshot taken on a schedule. That matters because a project's earliest audit timestamp is
the earliest point a delta can honestly describe, and the service says so rather than presenting an
empty result as "nothing changed".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

from sqlmodel import Session, SQLModel, select

from api import labels
from api.models import (
    ActionTable,
    ActivityEventTable,
    AssumptionTable,
    ChangeRequestTable,
    DecisionTable,
    DeliverableTable,
    DependencyTable,
    GateTable,
    IssueTable,
    MeetingNoteTable,
    MilestoneTable,
    ProjectTable,
    RequirementTable,
    RiskTable,
    TaskTable,
    WorkPackageTable,
)
from api.schemas import ProjectDelta, ProjectDeltaEntry, ProjectDeltaGroup

ADDED = "added"
UPDATED = "updated"
WITHDRAWN = "withdrawn"


class _Source(NamedTuple):
    """One record type that can appear in a delta."""

    table: type[SQLModel]
    group: str
    group_label: str
    entity_type: str
    id_field: str
    name_field: str
    status_field: str | None


_SOURCES: tuple[_Source, ...] = (
    _Source(
        MilestoneTable,
        "delivery",
        "Delivery",
        "milestone",
        "milestone_id",
        "milestone_name",
        "status",
    ),
    _Source(TaskTable, "work", "Work", "task", "task_id", "task_name", "status"),
    _Source(RiskTable, "risks", "Risks", "risk", "risk_id", "risk_name", "status"),
    _Source(ActionTable, "work", "Work", "action", "action_id", "action_description", "status"),
    _Source(
        DependencyTable,
        "delivery",
        "Delivery",
        "dependency",
        "dependency_id",
        "dependency_name",
        "status",
    ),
    _Source(
        RequirementTable,
        "requirements",
        "Requirements",
        "requirement",
        "requirement_id",
        "requirement_text",
        "status",
    ),
    _Source(
        ChangeRequestTable,
        "changes",
        "Change requests",
        "change request",
        "change_request_id",
        "change_description",
        "status",
    ),
    _Source(DecisionTable, "decisions", "Decisions", "decision", "decision_id", "title", "status"),
    _Source(GateTable, "gates", "Gates", "gate", "gate_id", "gate_name", "status"),
    _Source(IssueTable, "issues", "Issues", "issue", "issue_id", "title", "status"),
    _Source(
        AssumptionTable,
        "assumptions",
        "Assumptions",
        "assumption",
        "assumption_id",
        "assumption_text",
        "status",
    ),
    _Source(
        WorkPackageTable,
        "work",
        "Work",
        "work package",
        "work_package_id",
        "work_package_name",
        "status",
    ),
    _Source(
        DeliverableTable,
        "work",
        "Work",
        "deliverable",
        "deliverable_id",
        "deliverable_name",
        "status",
    ),
    _Source(
        MeetingNoteTable, "meetings", "Meeting notes", "meeting note", "note_id", "title", None
    ),
)

_GROUP_ORDER = (
    "delivery",
    "gates",
    "risks",
    "issues",
    "assumptions",
    "work",
    "requirements",
    "changes",
    "decisions",
    "meetings",
)

_CHANGE_ORDER = {ADDED: 0, UPDATED: 1, WITHDRAWN: 2}


def as_utc(value: datetime | None) -> datetime | None:
    """Compare stored timestamps safely.

    SQLite returns naive datetimes even though they were written as UTC, so every comparison that
    touches an audit column goes through here rather than risking an offset-naive error.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _shorten(text: str, limit: int = 90) -> str:
    """Trim a long free-text field down to something readable in a list."""
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else f"{clean[: limit - 1].rstrip()}…"


def _classify(row: SQLModel, since: datetime) -> str | None:
    """Decide whether a row was added, updated or withdrawn after ``since``."""
    deleted_at = as_utc(getattr(row, "deleted_at", None))
    if deleted_at is not None:
        return WITHDRAWN if deleted_at >= since else None

    created_at = as_utc(getattr(row, "created_at", None))
    if created_at is not None and created_at >= since:
        return ADDED

    updated_at = as_utc(getattr(row, "updated_at", None))
    if updated_at is not None and updated_at >= since:
        return UPDATED
    return None


def _epoch() -> datetime:
    """A stable fallback for rows with no usable timestamp."""
    return datetime.min.replace(tzinfo=UTC)


def _occurred_at(row: SQLModel, change_type: str) -> datetime:
    """The moment the change happened, used for ordering within a group."""
    field = {ADDED: "created_at", UPDATED: "updated_at", WITHDRAWN: "deleted_at"}[change_type]
    return as_utc(getattr(row, field, None)) or as_utc(getattr(row, "updated_at", None)) or _epoch()


def _headline(source: _Source, row: SQLModel, change_type: str) -> str:
    """A sentence a delivery lead can read without opening the record."""
    name = _shorten(str(getattr(row, source.name_field, "") or source.entity_type))
    verb = {ADDED: "was added", UPDATED: "was updated", WITHDRAWN: "was withdrawn"}[change_type]
    status = getattr(row, source.status_field, None) if source.status_field else None
    if change_type == UPDATED and status:
        return f"{name} {verb} and now stands at {labels.humanise(str(status))}."
    if change_type == ADDED and status:
        return f"{name} {verb} at {labels.humanise(str(status))}."
    return f"{name} {verb}."


def _credit_key(entity_type: str, entity_id: str) -> tuple[str, str]:
    """Match a record to its activity rows.

    The routers label events with their own display names ("Change request", "ChangeRequest"), so
    spacing and case are removed before comparing.
    """
    return (entity_type.replace(" ", "").lower(), entity_id)


def _actors(events: list[ActivityEventTable], since: datetime) -> dict[tuple[str, str], str]:
    """Map each changed record to the person the activity trail credits with the change."""
    credited: dict[tuple[str, str], str] = {}
    for event in sorted(events, key=lambda item: item.id or 0):
        occurred = as_utc(event.occurred_at)
        if occurred is None or occurred < since or not event.actor_name:
            continue
        credited[_credit_key(event.entity_type, event.entity_id)] = event.actor_name
    return credited


def build(session: Session, project_id: str, since: datetime) -> ProjectDelta:
    """Return everything that changed on a project since ``since``.

    ``since`` is treated as inclusive. A project whose records all predate the window returns an
    empty delta with ``has_history`` set, which lets the interface distinguish "nothing changed"
    from "we cannot see that far back".
    """
    return build_many(session, [project_id], since)[project_id]


def build_many(
    session: Session, project_ids: list[str], since: datetime
) -> dict[str, ProjectDelta]:
    """Deltas for several projects, reading each record table once rather than once per project."""
    since = as_utc(since) or _epoch()
    wanted = sorted(set(project_ids))
    projects = {
        row.project_id: row
        for row in session.exec(
            select(ProjectTable).where(ProjectTable.project_id.in_(wanted))  # type: ignore[attr-defined]
        ).all()
    }
    events_by_project: dict[str, list[ActivityEventTable]] = {}
    for event in session.exec(
        select(ActivityEventTable).where(ActivityEventTable.project_id.in_(wanted))  # type: ignore[union-attr]
    ).all():
        events_by_project.setdefault(str(event.project_id), []).append(event)
    rows_by_project: dict[str, list[tuple[_Source, SQLModel]]] = {}
    for source in _SOURCES:
        column = source.table.project_id  # type: ignore[attr-defined]
        for row in session.exec(select(source.table).where(column.in_(wanted))).all():
            rows_by_project.setdefault(str(row.project_id), []).append((source, row))  # type: ignore[attr-defined]
    return {
        project_id: _assemble(
            project_id,
            projects.get(project_id),
            events_by_project.get(project_id, []),
            rows_by_project.get(project_id, []),
            since,
        )
        for project_id in wanted
    }


def _assemble(
    project_id: str,
    project: ProjectTable | None,
    events: list[ActivityEventTable],
    rows: list[tuple[_Source, SQLModel]],
    since: datetime,
) -> ProjectDelta:
    project_name = project.project_name if project is not None else project_id
    credited = _actors(events, since)
    collected: dict[str, list[ProjectDeltaEntry]] = {}
    group_labels: dict[str, str] = {}

    for source, row in rows:
        change_type = _classify(row, since)
        if change_type is None:
            continue
        entity_id = str(getattr(row, source.id_field))
        group_labels[source.group] = source.group_label
        collected.setdefault(source.group, []).append(
            ProjectDeltaEntry(
                entity_type=source.entity_type,
                entity_id=entity_id,
                change_type=change_type,
                headline=_headline(source, row, change_type),
                status=(
                    labels.humanise(str(getattr(row, source.status_field)))
                    if source.status_field and getattr(row, source.status_field, None)
                    else None
                ),
                occurred_at=_occurred_at(row, change_type),
                actor_name=credited.get(_credit_key(source.entity_type, entity_id)),
            )
        )

    groups = [
        ProjectDeltaGroup(
            key=key,
            label=group_labels[key],
            added=sum(1 for entry in entries if entry.change_type == ADDED),
            updated=sum(1 for entry in entries if entry.change_type == UPDATED),
            withdrawn=sum(1 for entry in entries if entry.change_type == WITHDRAWN),
            entries=sorted(
                entries,
                key=lambda entry: (
                    _CHANGE_ORDER[entry.change_type],
                    -entry.occurred_at.timestamp(),
                ),
            ),
        )
        for key in _GROUP_ORDER
        if (entries := collected.get(key))
    ]

    earliest = as_utc(project.created_at) if project is not None else None
    return ProjectDelta(
        project_id=project_id,
        project_name=project_name,
        since=since,
        generated_at=datetime.now(UTC),
        total_changes=sum(len(group.entries) for group in groups),
        has_history=earliest is not None and earliest < since,
        earliest_record_at=earliest,
        groups=groups,
    )
