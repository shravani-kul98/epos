"""Append-only activity log for every write performed through the API."""

from __future__ import annotations

import json

from fastapi.encoders import jsonable_encoder
from pydantic import TypeAdapter, ValidationError
from sqlmodel import Session, desc, select

from api.models import ActivityEventTable, UserTable
from api.schemas import ActivityEventOut, ActivityFieldChange, TaskProgressEntry

_CHANGE_LIST = TypeAdapter(list[ActivityFieldChange])
_SENSITIVE_FIELD_PARTS = frozenset(
    {"api_key", "credential", "password", "secret", "token", "password_hash"}
)
# Matches the longest text field any record stores, so a before/after value is never cut short.
_MAX_AUDIT_TEXT_LENGTH = 20_000
PROGRESS_NOTE_FIELD = "progress_note"
# Bookkeeping every report changes; listing it in a progress history would only repeat itself.
_UNREPORTED_TASK_FIELDS = frozenset({PROGRESS_NOTE_FIELD, "last_updated_date"})
_TASK_HISTORY_LIMIT = 100


def record(
    session: Session,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    project_id: str | None = None,
    detail: str | None = None,
    changes: list[ActivityFieldChange] | None = None,
    actor: UserTable | None = None,
) -> ActivityEventTable:
    """Append one audit row. The caller commits as part of its own transaction."""
    event = ActivityEventTable(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        summary=summary,
        detail=detail,
        changes_json=_encode_changes(changes),
        actor_email=actor.email if actor else None,
        actor_name=actor.full_name if actor else None,
    )
    session.add(event)
    return event


def list_events(
    session: Session,
    project_id: str | None = None,
    limit: int = 50,
    project_ids: set[str] | None = None,
    include_workspace_events: bool = False,
) -> list[ActivityEventOut]:
    """Return the most recent events, newest first."""
    statement = select(ActivityEventTable)
    if project_ids is not None:
        statement = statement.where(ActivityEventTable.project_id.in_(project_ids))
    elif not include_workspace_events:
        statement = statement.where(ActivityEventTable.project_id.is_not(None))
    if project_id is not None:
        statement = statement.where(ActivityEventTable.project_id == project_id)
    statement = statement.order_by(desc(ActivityEventTable.id)).limit(limit)

    return [
        ActivityEventOut(
            id=row.id or 0,
            occurred_at=row.occurred_at,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            project_id=row.project_id,
            summary=row.summary,
            detail=row.detail,
            changes=_decode_changes(row.changes_json),
            actor_name=row.actor_name,
            headline=_headline(row),
        )
        for row in session.exec(statement).all()
    ]


def _headline(row: ActivityEventTable) -> str:
    """Render an event as a sentence a person would read in a feed."""
    who = row.actor_name or "Someone"
    return f"{who} {row.summary[0].lower()}{row.summary[1:]}" if row.summary else who


def progress_note_change(note: str) -> ActivityFieldChange:
    """The reporter's own words, recorded with the field changes they explain."""
    return ActivityFieldChange(
        field=PROGRESS_NOTE_FIELD,
        label="Progress note",
        before=None,
        after=_audit_value(PROGRESS_NOTE_FIELD, note),
    )


def progress_before_completion(session: Session, task_id: str) -> int:
    """The progress an assignee reported just before completing, so returned work resumes there."""
    event = session.exec(
        select(ActivityEventTable)
        .where(
            ActivityEventTable.entity_type == "Task",
            ActivityEventTable.entity_id == task_id,
            ActivityEventTable.action == "completed",
        )
        .order_by(desc(ActivityEventTable.id))
        .limit(1)
    ).first()
    changes = _decode_changes(event.changes_json) if event else None
    for change in changes or []:
        if change.field == "completion_percent" and isinstance(change.before, int):
            return change.before if 0 <= change.before < 100 else 0
    return 0


def task_history(session: Session, task_id: str) -> list[TaskProgressEntry]:
    """Every recorded report on a task, newest first, with the note its author added."""
    statement = (
        select(ActivityEventTable)
        .where(ActivityEventTable.entity_type == "Task", ActivityEventTable.entity_id == task_id)
        .order_by(desc(ActivityEventTable.id))
        .limit(_TASK_HISTORY_LIMIT)
    )
    entries: list[TaskProgressEntry] = []
    for row in session.exec(statement).all():
        changes = _decode_changes(row.changes_json) or []
        note = next((c.after for c in changes if c.field == PROGRESS_NOTE_FIELD), None)
        entries.append(
            TaskProgressEntry(
                id=row.id or 0,
                occurred_at=row.occurred_at,
                action=row.action,
                actor_name=row.actor_name,
                note=note if isinstance(note, str) else None,
                changes=[c for c in changes if c.field not in _UNREPORTED_TASK_FIELDS],
            )
        )
    return entries


def describe_changes(before: dict[str, object], after: dict[str, object]) -> str | None:
    """Summarise which fields changed, for the audit detail column."""
    changed = [
        f"{change.label}: {change.before!r} -> {change.after!r}"
        for change in field_changes(before, after)
    ]
    return "; ".join(changed) if changed else None


def field_changes(before: dict[str, object], after: dict[str, object]) -> list[ActivityFieldChange]:
    """Build deterministic, JSON-safe and sanitized field-level differences."""
    return [
        ActivityFieldChange(
            field=field,
            label=field.replace("_", " ").capitalize(),
            before=_audit_value(field, before.get(field)),
            after=_audit_value(field, after.get(field)),
        )
        for field in after
        if field != "row_version" and before.get(field) != after.get(field)
    ]


def _audit_value(field: str, value: object) -> object:
    if any(part in field.lower() for part in _SENSITIVE_FIELD_PARTS):
        return "[redacted]"
    encoded = jsonable_encoder(value)
    if isinstance(encoded, str) and len(encoded) > _MAX_AUDIT_TEXT_LENGTH:
        return f"{encoded[:_MAX_AUDIT_TEXT_LENGTH]}..."
    return encoded


def _encode_changes(changes: list[ActivityFieldChange] | None) -> str | None:
    if changes is None:
        return None
    return json.dumps([change.model_dump(mode="json") for change in changes], separators=(",", ":"))


def _decode_changes(raw: str | None) -> list[ActivityFieldChange] | None:
    if raw is None:
        return None
    try:
        return _CHANGE_LIST.validate_json(raw)
    except ValidationError:
        return None
