"""Ask EPOS conversation history.

Conversations belong to the user who created them. Every read and write checks ownership, so one
user can never see or delete another's history.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func
from sqlmodel import Session, desc, select

from api.models import ConversationMessageTable, ConversationTable, UserTable
from api.schemas import (
    ConversationDetail,
    ConversationMessageOut,
    ConversationSummary,
    CopilotAnswer,
    EvidenceRecordOut,
)
from api.security.project_scope import (
    has_project_access,
    project_ids_for,
    source_ids_are_authorized,
)
from src.config import AI_DISCLAIMER

_TITLE_LENGTH = 60
_ROUTING_HISTORY_LIMIT = 6
_ROUTING_QUESTION_LENGTH = 300
_ASSISTANT_HISTORY_LIMIT = 8
_ASSISTANT_SUMMARY_LENGTH = 240
_ASSISTANT_CITED_LIMIT = 8


def _title_from(question: str) -> str:
    """Use the opening question as the conversation title."""
    text = " ".join(question.split())
    return text if len(text) <= _TITLE_LENGTH else text[: _TITLE_LENGTH - 1] + "\u2026"


def _owned_conversation(
    session: Session, user: UserTable, conversation_id: int
) -> ConversationTable:
    """Return a conversation the user owns, or 404.

    A conversation belonging to someone else reports as not found rather than forbidden, so the
    endpoint cannot be used to discover that another user's conversation exists.
    """
    conversation = session.get(ConversationTable, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That conversation was not found."
        )
    if not _conversation_is_authorized(session, user, conversation):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That conversation was not found."
        )
    return conversation


def _conversation_is_authorized(
    session: Session, user: UserTable, conversation: ConversationTable
) -> bool:
    """Recheck project and persisted evidence access before exposing saved history."""
    if conversation.project_id and not has_project_access(session, user, conversation.project_id):
        return False
    statement = select(ConversationMessageTable).where(
        ConversationMessageTable.conversation_id == conversation.id
    )
    source_ids: set[str] = set()
    generated_source_ids: set[str] = set()
    evidence_project_ids: set[str] = set()
    legacy_global_scope = False
    try:
        for message in session.exec(statement).all():
            context = json.loads(message.context_json or "{}")
            if not isinstance(context, dict):
                return False
            if context.get("project_id"):
                evidence_project_ids.add(context["project_id"])
            if context.get("project_ids"):
                evidence_project_ids.update(json.loads(context["project_ids"]))
            source_ids.update(json.loads(message.source_ids_json or "[]"))
            for record in json.loads(message.evidence_json or "[]"):
                if record_id := record.get("record_id"):
                    source_ids.add(record_id)
                    generated_source_ids.add(record_id)
                fields = record.get("fields") or {}
                evidence_project_id = fields.get("project_id")
                if evidence_project_id == "all projects":
                    if "project_scope_ids" not in fields:
                        legacy_global_scope = True
                elif evidence_project_id:
                    evidence_project_ids.add(evidence_project_id)
                if raw_scope_ids := fields.get("project_scope_ids"):
                    scope_ids = json.loads(raw_scope_ids)
                    if not isinstance(scope_ids, list) or not all(
                        isinstance(project_id, str) and project_id for project_id in scope_ids
                    ):
                        return False
                    evidence_project_ids.update(scope_ids)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return False
    if legacy_global_scope and project_ids_for(session, user) is not None:
        return False
    if any(
        not has_project_access(session, user, project_id) for project_id in evidence_project_ids
    ):
        return False
    return source_ids_are_authorized(
        session, user, source_ids, generated_source_ids=generated_source_ids
    )


def append_turn(
    session: Session,
    user: UserTable,
    conversation_id: int | None,
    question: str,
    answer: CopilotAnswer,
    project_id: str | None,
) -> int:
    """Record a question and its answer, starting a conversation when needed."""
    if conversation_id is None:
        conversation = ConversationTable(
            user_id=user.id or 0, title=_title_from(question), project_id=project_id
        )
        session.add(conversation)
        session.flush()
    else:
        conversation = _owned_conversation(session, user, conversation_id)
        conversation.updated_at = datetime.now(UTC)
        conversation.project_id = project_id
        session.add(conversation)

    session.add(
        ConversationMessageTable(
            conversation_id=conversation.id or 0, role="user", content=question
        )
    )
    session.add(
        ConversationMessageTable(
            conversation_id=conversation.id or 0,
            role="assistant",
            content=answer.executive_summary,
            matched_intent=answer.matched_intent,
            status=answer.status,
            source_ids_json=json.dumps(answer.source_ids),
            evidence_json=json.dumps([record.model_dump() for record in answer.evidence]),
            answer_json=answer.model_dump_json(exclude={"conversation_id"}),
            context_json=json.dumps(answer.context),
        )
    )
    session.commit()
    return conversation.id or 0


def routing_history(
    session: Session, user: UserTable, conversation_id: int | None
) -> list[dict[str, str | None]]:
    """Return bounded context for interpreting a follow-up, after ownership is checked."""
    if conversation_id is None:
        return []
    conversation = _owned_conversation(session, user, conversation_id)
    statement = (
        select(ConversationMessageTable)
        .where(ConversationMessageTable.conversation_id == conversation_id)
        .order_by(desc(ConversationMessageTable.id))
        .limit(_ROUTING_HISTORY_LIMIT)
    )
    rows = list(reversed(session.exec(statement).all()))
    history: list[dict[str, str | None]] = []
    for row in rows:
        context = json.loads(row.context_json or "{}")
        if not context and conversation.project_id and row.role == "assistant":
            context["project_id"] = conversation.project_id
        source_ids = json.loads(row.source_ids_json) if row.source_ids_json else []
        if not source_ids and row.evidence_json:
            source_ids = [
                record["record_id"]
                for record in json.loads(row.evidence_json)
                if record.get("record_id")
            ]
        history.append(
            {
                **{key: value for key, value in context.items() if isinstance(value, str)},
                "role": row.role,
                # Model-authored assistant prose is not recycled as evidence.
                "content": (row.content[:_ROUTING_QUESTION_LENGTH] if row.role == "user" else None),
                "matched_intent": row.matched_intent,
                "source_ids": ",".join(source_ids[:10]) or None,
            }
        )
    return history


def assistant_history(
    session: Session, user: UserTable, conversation_id: int | None
) -> list[dict[str, str]]:
    """Recent turns for the assistant's planning step, after ownership is checked.

    Earlier replies are included only as short summaries, so a follow-up such as "and the second
    one?" can be resolved. They are never evidence: every answer is rebuilt from current records.
    """
    if conversation_id is None:
        return []
    _owned_conversation(session, user, conversation_id)
    statement = (
        select(ConversationMessageTable)
        .where(ConversationMessageTable.conversation_id == conversation_id)
        .order_by(desc(ConversationMessageTable.id))
        .limit(_ASSISTANT_HISTORY_LIMIT)
    )
    turns: list[dict[str, str]] = []
    for row in reversed(session.exec(statement).all()):
        if row.role == "user":
            turns.append({"role": "user", "text": row.content[:_ROUTING_QUESTION_LENGTH]})
            continue
        try:
            context = json.loads(row.context_json or "{}")
            cited = json.loads(row.source_ids_json or "[]")
        except json.JSONDecodeError:
            context, cited = {}, []
        context = context if isinstance(context, dict) else {}
        turns.append(
            {
                "role": "assistant",
                "text": row.content[:_ASSISTANT_SUMMARY_LENGTH],
                "tools": str(context.get("assistant_tools") or row.matched_intent or ""),
                "cited": ", ".join(str(item) for item in cited[:_ASSISTANT_CITED_LIMIT]),
                "project_id": str(context.get("project_id") or ""),
            }
        )
    return turns


def _saved_answer(row: ConversationMessageTable) -> CopilotAnswer | None:
    """Restore a saved answer; legacy messages remain explicitly incomplete snapshots."""
    if row.role != "assistant":
        return None
    if row.answer_json:
        try:
            return CopilotAnswer.model_validate_json(row.answer_json)
        except ValidationError:
            pass
    return CopilotAnswer(
        status=(
            row.status
            if row.status in {"ok", "error", "unavailable", "invalid_response", "clarification"}
            else "error"
        ),
        matched_intent=row.matched_intent,
        matched_question=None,
        executive_summary=row.content,
        key_findings=[],
        recommended_actions=[],
        source_ids=json.loads(row.source_ids_json or "[]"),
        evidence=[EvidenceRecordOut(**record) for record in json.loads(row.evidence_json or "[]")],
        human_review_required=True,
        disclaimer=AI_DISCLAIMER,
        warnings=[
            "Legacy saved answer: only its summary and source evidence were retained. Ask a follow-up for current details."
        ],
        suggested_questions=[],
    )


def list_conversations(session: Session, user: UserTable) -> list[ConversationSummary]:
    """Return the user's conversations, most recently used first."""
    statement = (
        select(ConversationTable)
        .where(ConversationTable.user_id == user.id)
        .order_by(desc(ConversationTable.updated_at))
    )
    conversations = session.exec(statement).all()
    conversations = [
        conversation
        for conversation in conversations
        if _conversation_is_authorized(session, user, conversation)
    ]

    summaries: list[ConversationSummary] = []
    for conversation in conversations:
        count = session.exec(
            select(func.count())
            .select_from(ConversationMessageTable)
            .where(ConversationMessageTable.conversation_id == conversation.id)
        ).one()
        summaries.append(
            ConversationSummary(
                id=conversation.id or 0,
                title=conversation.title,
                project_id=conversation.project_id,
                message_count=count,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
        )
    return summaries


def get_conversation(session: Session, user: UserTable, conversation_id: int) -> ConversationDetail:
    """Return one conversation with its messages and saved evidence."""
    conversation = _owned_conversation(session, user, conversation_id)
    statement = (
        select(ConversationMessageTable)
        .where(ConversationMessageTable.conversation_id == conversation_id)
        .order_by(ConversationMessageTable.id)
    )

    messages = [
        ConversationMessageOut(
            id=row.id or 0,
            role=row.role,
            content=row.content,
            matched_intent=row.matched_intent,
            status=row.status,
            source_ids=json.loads(row.source_ids_json) if row.source_ids_json else [],
            evidence=[
                EvidenceRecordOut(**record) for record in json.loads(row.evidence_json or "[]")
            ],
            created_at=row.created_at,
            answer=_saved_answer(row),
        )
        for row in session.exec(statement).all()
    ]

    return ConversationDetail(
        id=conversation.id or 0,
        title=conversation.title,
        project_id=conversation.project_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages,
        context=next(
            (
                message.answer.context
                for message in reversed(messages)
                if message.answer and message.answer.context
            ),
            {},
        ),
    )


def delete_conversation(session: Session, user: UserTable, conversation_id: int) -> None:
    """Delete one of the user's conversations and its messages."""
    conversation = _owned_conversation(session, user, conversation_id)
    statement = select(ConversationMessageTable).where(
        ConversationMessageTable.conversation_id == conversation_id
    )
    for message in session.exec(statement).all():
        session.delete(message)
    session.delete(conversation)
    session.commit()
