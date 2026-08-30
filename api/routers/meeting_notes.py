"""Meeting notes and the follow-ups read out of them.

A note is stored as written, with only surrounding whitespace trimmed. Proposals are derived on
request and create nothing. Promoting a proposal into an action, risk or decision is a separate,
explicit request, so a record only ever enters the project because a person put it there.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import Session, SQLModel, select

from api import clock
from api.crud import (
    apply_update,
    ensure_absent,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import ActionTable, ActivityEventTable, DecisionTable, MeetingNoteTable, RiskTable
from api.schemas import (
    ActionOut,
    DecisionOut,
    DecisionStatus,
    MeetingNoteCreate,
    MeetingNoteExtraction,
    MeetingNoteOut,
    MeetingNotePromotion,
    MeetingNoteUpdate,
    RiskOut,
)
from api.security.dependencies import CurrentUser, WorkManager, WorkUpdater
from api.security.permissions import Permission, has_permission
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import action_row_out, risk_row_out
from api.services import activity_service, meeting_note_service, notification_service, record_owners
from api.services.record_references import next_reference

router = APIRouter(prefix="/meeting-notes", tags=["meeting notes"])

_LABEL = "Meeting note"

# Defaults applied when a proposal becomes a record. They describe a follow-up that has been
# noticed but not yet worked, which is exactly what a meeting note produces.
_NEW_ACTION_STATUS = "Open"
_NEW_ACTION_PRIORITY = "Medium"
_NEW_RISK_STATUS = "Open"
_DEFAULT_DUE_DAYS = 14


def _origin_prefix(note_id: str) -> str:
    return f"Meeting note {note_id}, line "


def _has_promotions(session: Session, project_id: str, note_id: str) -> bool:
    """Whether the audit trail records any follow-up promoted from this note."""
    statement = select(ActivityEventTable).where(
        ActivityEventTable.project_id == project_id,
        ActivityEventTable.action == "promoted",
        ActivityEventTable.summary.startswith(
            f"Promoted {_origin_prefix(note_id)}", autoescape=True
        ),
    )
    return session.exec(statement).first() is not None


def _existing_promotion(session: Session, project_id: str, kind: str, text: str) -> str | None:
    """The identifier of a live record already created from the same wording, if any."""
    table, id_field, text_field = {
        meeting_note_service.ACTION: (ActionTable, "action_id", "action_description"),
        meeting_note_service.RISK: (RiskTable, "risk_id", "risk_name"),
        meeting_note_service.DECISION: (DecisionTable, "decision_id", "description"),
    }[kind]
    for row in list_rows(session, table, project_id):
        if getattr(row, text_field) == text:
            return str(getattr(row, id_field))
    return None


def _present(row: MeetingNoteTable) -> MeetingNoteOut:
    return MeetingNoteOut.model_validate(row, from_attributes=True)


@router.get("", response_model=list[MeetingNoteOut])
def list_meeting_notes(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
) -> list[MeetingNoteOut]:
    """Every meeting note, newest meeting first."""
    rows = list_rows(session, MeetingNoteTable, project_id)
    rows = scope_rows(session, actor, rows)
    rows.sort(key=lambda row: (row.meeting_date, row.note_id), reverse=True)
    return [_present(row) for row in rows]


@router.get("/{note_id}", response_model=MeetingNoteOut)
def read_meeting_note(note_id: str, session: SessionDep, actor: CurrentUser) -> MeetingNoteOut:
    row = get_or_404(session, MeetingNoteTable, note_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=MeetingNoteOut, status_code=status.HTTP_201_CREATED)
def create_meeting_note(
    payload: MeetingNoteCreate, session: SessionDep, actor: WorkUpdater
) -> MeetingNoteOut:
    """Store a note exactly as it was written."""
    require_project_access(session, actor, payload.project_id, write=True)
    note_id = payload.note_id or next_reference(session, payload.project_id, "MN")
    ensure_absent(session, MeetingNoteTable, note_id, _LABEL)

    row = MeetingNoteTable(**{**payload.model_dump(), "note_id": note_id})
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="captured",
        entity_type="Meeting note",
        entity_id=note_id,
        project_id=payload.project_id,
        summary=f"Captured meeting note {note_id}: {payload.title}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{note_id}", response_model=MeetingNoteOut)
def update_meeting_note(
    note_id: str, payload: MeetingNoteUpdate, session: SessionDep, actor: WorkUpdater
) -> MeetingNoteOut:
    """Correct a note. The stored text stays the record of what was written.

    Once a follow-up has been promoted from a note, its body is frozen so every "line N" reference
    keeps pointing at the words a reviewer approved.
    """
    row = get_or_404(session, MeetingNoteTable, note_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    if (
        payload.body is not None
        and payload.body != row.body
        and _has_promotions(session, row.project_id, note_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Follow-ups were promoted from meeting note {note_id}, so its text is kept as "
                "written. Capture a new note for the correction."
            ),
        )
    before = apply_update(row, payload, actor.email)
    after = payload.model_dump(exclude_unset=True)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type="Meeting note",
        entity_id=note_id,
        project_id=row.project_id,
        summary=f"Updated meeting note {note_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting_note(
    note_id: str, row_version: RowVersionDep, session: SessionDep, actor: WorkManager
) -> None:
    """Withdraw a note. Soft deleted, so anything promoted from it stays explainable."""
    row = get_or_404(session, MeetingNoteTable, note_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="withdrew",
        entity_type="Meeting note",
        entity_id=note_id,
        project_id=row.project_id,
        summary=f"Withdrew meeting note {note_id}",
        actor=actor,
    )
    session.commit()


@router.get("/{note_id}/extraction", response_model=MeetingNoteExtraction)
def read_extraction(note_id: str, session: SessionDep, actor: CurrentUser) -> MeetingNoteExtraction:
    """Read follow-ups out of a note. Creates nothing."""
    row = get_or_404(session, MeetingNoteTable, note_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return meeting_note_service.extract(row.note_id, row.project_id, row.body)


@router.post("/{note_id}/promote", status_code=status.HTTP_201_CREATED)
def promote_proposal(
    note_id: str,
    payload: MeetingNotePromotion,
    session: SessionDep,
    actor: CurrentUser,
) -> ActionOut | RiskOut | DecisionOut:
    """Turn one reviewed proposal into a real record.

    The values written are the ones the reviewer sent, not the ones extraction guessed, so the
    record always matches what a person actually approved.
    """
    _require_promotion_permission(actor, payload.kind)
    note = get_or_404(session, MeetingNoteTable, note_id, _LABEL)
    require_project_access(session, actor, note.project_id, write=True)
    if payload.source_line_number > len(note.body.splitlines()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Line {payload.source_line_number} is not part of meeting note {note_id}.",
        )
    if existing := _existing_promotion(session, note.project_id, payload.kind, payload.text):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This follow-up is already recorded as {existing}.",
        )

    origin = f"{_origin_prefix(note_id)}{payload.source_line_number}"
    due = payload.due_date or clock.utc_today() + timedelta(days=_DEFAULT_DUE_DAYS)
    owner_account = (
        record_owners.linked_owner(session, note.project_id, payload.owner_user_id)
        if payload.owner_user_id is not None and payload.kind != meeting_note_service.DECISION
        else None
    )
    owner_name = owner_account.full_name if owner_account is not None else payload.owner
    owner_id = owner_account.id if owner_account is not None else None

    if payload.kind == meeting_note_service.ACTION:
        record_id = next_reference(session, note.project_id, "A")
        ensure_absent(session, ActionTable, record_id, "Action")
        if owner_account is not None and not has_permission(
            owner_account.role, Permission.WORK_UPDATE
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Select a person whose role can update assigned work.",
            )
        row: SQLModel = ActionTable(
            action_id=record_id,
            project_id=note.project_id,
            action_description=payload.text,
            owner=owner_name,
            owner_user_id=owner_id,
            due_date=due,
            status=_NEW_ACTION_STATUS,
            priority=_NEW_ACTION_PRIORITY,
            source_reference=origin,
        )
        entity_type = "Action"
        assigned_kind = notification_service.ACTION_ASSIGNED
    elif payload.kind == meeting_note_service.RISK:
        record_id = next_reference(session, note.project_id, "R")
        ensure_absent(session, RiskTable, record_id, "Risk")
        row = RiskTable(
            risk_id=record_id,
            project_id=note.project_id,
            risk_name=payload.text,
            probability=payload.probability,
            impact=payload.impact,
            status=_NEW_RISK_STATUS,
            mitigation_owner=owner_name,
            mitigation_owner_user_id=owner_id,
            due_date=due,
        )
        entity_type = "Risk"
        assigned_kind = notification_service.RISK_ASSIGNED
    else:
        record_id = next_reference(session, note.project_id, "DEC")
        ensure_absent(session, DecisionTable, record_id, "Decision")
        row = DecisionTable(
            decision_id=record_id,
            project_id=note.project_id,
            title=payload.text[:200],
            description=payload.text,
            category="Delivery",
            decision_date=note.meeting_date,
            owner=payload.owner,
            status=DecisionStatus.PROPOSED.value,
            notes=origin,
        )
        entity_type = "Decision"
        assigned_kind = None

    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="promoted",
        entity_type=entity_type,
        entity_id=record_id,
        project_id=note.project_id,
        summary=f"Promoted {origin} into {entity_type.lower()} {record_id}",
        detail=payload.text,
        actor=actor,
    )
    if assigned_kind is not None:
        record_owners.notify_new_owner(
            session,
            owner_id=owner_id,
            previous_owner_id=None,
            kind=assigned_kind,
            title=f"You own {entity_type.lower()} {record_id} from a meeting note",
            detail=payload.text,
            project_id=note.project_id,
            entity_type=entity_type,
            entity_id=record_id,
            actor=actor,
        )
    session.commit()
    session.refresh(row)

    if isinstance(row, ActionTable):
        return action_row_out(row)
    if isinstance(row, RiskTable):
        return risk_row_out(row)
    return DecisionOut.model_validate(row, from_attributes=True)


def _require_promotion_permission(actor: CurrentUser, kind: str) -> None:
    permissions = {
        meeting_note_service.ACTION: Permission.ACTION_MANAGE,
        meeting_note_service.RISK: Permission.RISK_MANAGE,
        meeting_note_service.DECISION: Permission.CHANGE_CREATE,
    }
    permission = permissions[kind]
    if not has_permission(actor.role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role does not allow this action.",
        )
