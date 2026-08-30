"""Ask EPOS: free-text questions answered from evidence in the workspace."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response, status
from sqlmodel import Session, SQLModel

from api.crud import list_rows
from api.dependencies import AsOfDateDep, PortfolioDep, SessionDep
from api.models import (
    AssumptionTable,
    DecisionTable,
    GateCriterionTable,
    GateReviewTable,
    GateTable,
    IssueTable,
    UserTable,
)
from api.schemas import (
    ConversationDetail,
    ConversationSummary,
    CopilotAnswer,
    CopilotAskRequest,
    SupportedQuestion,
)
from api.security.dependencies import AssistantQuota, CopilotUser
from api.security.permissions import Permission, has_permission, permissions_for, role_label
from api.security.project_scope import project_ids_for, require_project_access, scope_rows
from api.services import conversation_service, copilot_agent, copilot_service, delta_service
from src import ai_trace

router = APIRouter(prefix="/copilot", tags=["copilot"])

# Correlates one answer with its content-free timing log line; the ID is random, never derived.
TRACE_HEADER = "X-EPOS-Trace-Id"

# Governed records the engines do not read, which the assistant may look up.
_ASSISTANT_REGISTERS: dict[str, type[SQLModel]] = {
    "gate": GateTable,
    "gate_criterion": GateCriterionTable,
    "gate_review": GateReviewTable,
    "issue": IssueTable,
    "assumption": AssumptionTable,
}


def _assistant_registers(session: Session, actor: UserTable) -> dict[str, list]:
    """The governed registers, limited to the projects the caller may see."""
    return {
        kind: scope_rows(session, actor, list_rows(session, table, None))
        for kind, table in _ASSISTANT_REGISTERS.items()
    }


def _change_reader(session: Session) -> copilot_agent.ChangeReader:
    """Read change history for projects the assistant has already limited to the caller's."""

    def read(project_ids: tuple[str, ...], since: datetime) -> list:
        return list(delta_service.build_many(session, list(project_ids), since).values())

    return read


@router.get("/questions", response_model=list[SupportedQuestion])
def list_supported_questions(_: CopilotUser) -> list[SupportedQuestion]:
    """List the analyses Ask EPOS can perform, offered as prompt suggestions."""
    return copilot_service.supported_questions()


@router.post("/ask", response_model=CopilotAnswer, dependencies=[AssistantQuota])
def ask(
    payload: CopilotAskRequest,
    portfolio: PortfolioDep,
    as_of_date: AsOfDateDep,
    session: SessionDep,
    actor: CopilotUser,
    response: Response,
) -> CopilotAnswer:
    """Answer a free-text question, or ask for clarification when it cannot be routed.

    The question may be sent to the approved Azure deployment for classification. It is never
    executed as a query and can never cause a write.
    """
    if payload.project_id is not None:
        require_project_access(session, actor, payload.project_id)
    routing_history = conversation_service.routing_history(session, actor, payload.conversation_id)
    assistant = copilot_agent.enabled()
    assistant_history = (
        conversation_service.assistant_history(session, actor, payload.conversation_id)
        if assistant and not payload.reset_context
        else []
    )
    decisions = scope_rows(session, actor, list_rows(session, DecisionTable, None))
    with ai_trace.request_trace() as trace:
        answer = copilot_service.ask(
            payload.question,
            portfolio,
            as_of_date,
            project_id=payload.project_id,
            owner_name=actor.full_name,
            owner_user_id=actor.id,
            # Decisions are not engine input, so they are supplied separately.
            decisions=decisions,
            conversation_context=[] if payload.reset_context else routing_history,
            can_run_scenarios=has_permission(actor.role, Permission.SCENARIO_RUN),
            can_read_reports=has_permission(actor.role, Permission.REPORT_READ),
            role_label=role_label(actor.role),
            permissions=frozenset(permission.value for permission in permissions_for(actor.role)),
            assistant_history=assistant_history,
            registers=_assistant_registers(session, actor) if assistant else None,
            changes_since=_change_reader(session) if assistant else None,
            sees_all_projects=assistant and project_ids_for(session, actor) is None,
        )
    response.headers[TRACE_HEADER] = trace.trace_id
    answer.conversation_id = conversation_service.append_turn(
        session,
        user=actor,
        conversation_id=payload.conversation_id,
        question=payload.question,
        answer=answer,
        project_id=answer.resolved_project_id or payload.project_id,
    )
    return answer


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(session: SessionDep, actor: CopilotUser) -> list[ConversationSummary]:
    """List the signed-in user's own conversations."""
    return conversation_service.list_conversations(session, actor)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int, session: SessionDep, actor: CopilotUser
) -> ConversationDetail:
    """Return one conversation with its full history and saved evidence."""
    return conversation_service.get_conversation(session, actor, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, session: SessionDep, actor: CopilotUser) -> None:
    """Clear one of the signed-in user's own conversations."""
    conversation_service.delete_conversation(session, actor, conversation_id)
