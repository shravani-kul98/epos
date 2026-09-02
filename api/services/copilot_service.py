"""Free-text Ask EPOS routing.

Raw user text never reaches the database, the engines, or a SQL statement. It is first matched
against a fixed set of supported intents by deterministic rules. Only a matched intent, with
validated context ids, can produce an evidence package and reach the model.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Final

from api.schemas import CopilotAnswer, EvidenceRecordOut, SupportedQuestion
from api.services import (
    copilot_agent,
    copilot_context,
    copilot_knowledge,
    copilot_presentation,
    copilot_scenarios,
    intent_matcher,
    project_query,
    semantic_router,
    workspace_evidence,
)
from api.services import copilot_answers as answers
from src import ai_trace
from src.ai_assistant import (
    QUESTION_CHANGE_REQUEST_IMPACT,
    QUESTION_CONTEXT_KEYS,
    QUESTION_PROJECTS_NEEDING_ATTENTION,
    QUESTION_RISKS_WITHOUT_OWNER,
    QUESTION_TYPES,
    QUESTION_WEEKLY_EXECUTIVE_UPDATE,
    QUESTION_WHY_PROJECT_BAND,
    Transport,
    ask_epos,
    build_evidence_package,
)
from src.config import AI_DISCLAIMER
from src.data_loader import PortfolioData

_PROJECT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bP-\d{3,}\b", re.IGNORECASE)
_CHANGE_REQUEST_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bCR-\d{2,}\b", re.IGNORECASE)

_MAX_QUESTION_LENGTH: Final[int] = 1000

# Everyday wording mapped onto the vocabulary the rules below are written in, so a question does
# not have to be phrased the way the matcher happens to be written. The alternation is grouped:
# without ``(?:...)`` the word boundaries would bind only to the first and last branch, and
# "blockers" would be rewritten to "blockeds".
_SYNONYMS: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(rf"\b(?:{pattern})\b"), replacement)
    for pattern, replacement in (
        (r"show me|show|display|give me|tell me about|what are", "list"),
        (r"unhealthy|behind schedule|behind|off track|struggling|in trouble", "at risk"),
        (
            r"workload|overloaded|over-allocated|overallocated|over capacity|too much work",
            "capacity",
        ),
        (r"blocker|blockers|impediment|impediments|stuck", "blocked"),
        (r"cr\b|change requests", "change request"),
        (r"deadline|deadlines|target date|target dates|gate|gates", "milestone"),
        (r"programme|program|initiative|initiatives", "project"),
        (r"who owns|responsible for|assigned to me|my work", "my tasks"),
        (r"needs approval|awaiting approval|needs sign-off|needs a decision", "pending decision"),
        (r"how is|how's", "status of"),
    )
)


def normalise(question: str) -> str:
    """Lowercase, collapse whitespace and fold everyday wording onto the matcher's vocabulary."""
    text = " ".join(question.lower().split())
    for pattern, replacement in _SYNONYMS:
        text = pattern.sub(replacement, text)
    return text


SUGGESTED_QUESTIONS: Final[tuple[str, ...]] = tuple(QUESTION_TYPES.values())


def _canonical_key(text: str) -> str:
    """Compare question wording without case, spacing, or punctuation."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


# The exact wording of every advertised question. When a user picks one and the local rules agree
# on its intent, a semantic classification can add nothing: the text carries no selector to extract.
_CANONICAL_INTENTS: Final[dict[str, str]] = {
    _canonical_key(question): intent
    for intent, question in {**QUESTION_TYPES, **answers.LOOKUP_QUESTIONS}.items()
}

_NO_EVIDENCE_NOTE: Final[str] = (
    "No records matched this question, so no AI explanation was requested."
)

_PLURAL_PROJECTS: Final[re.Pattern[str]] = re.compile(r"\bprojects\b", re.IGNORECASE)

# Naming one project answers a different question from the portfolio-wide version. "What is going
# wrong?" asks which projects need attention; "what is going wrong with P-002?" asks what is
# driving that project's band.
_NARROWS_TO_ONE_PROJECT: Final[frozenset[str]] = frozenset(
    {
        answers.LIST_PROJECTS,
        QUESTION_PROJECTS_NEEDING_ATTENTION,
    }
)

# Words that carry no distinguishing power when matching a project by name.
_NAME_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "for",
        "project",
        "programme",
        "program",
        "is",
        "at",
        "in",
        "on",
        "why",
        "how",
        "what",
        "which",
    }
)


def _significant_words(value: str) -> set[str]:
    """Lowercase words worth matching on, ignoring filler."""
    return {
        word
        for word in re.findall(r"[a-z0-9]+", value.lower())
        if len(word) > 2 and word not in _NAME_STOPWORDS
    }


def resolve_projects_by_name(question: str, portfolio: PortfolioData) -> list[str]:
    """Find projects whose name is recognisable in the question.

    Matching is on stored project names only. Nothing here reaches the database, and a name that
    does not exist in the portfolio can never be produced. A single distinctive word is enough,
    which is what makes a partial name such as "supplier" usable. A word the matcher already reads
    as delivery vocabulary is not distinctive: "requirements" in a portfolio question must not
    narrow it to a project that happens to be called Engineering Requirements Digitalisation.
    """
    asked = _significant_words(question)
    if not asked:
        return []
    distinctive = asked - intent_matcher.DOMAIN_VOCABULARY

    exact = [
        project.project_id
        for project in portfolio.projects
        if re.search(
            rf"(?<!\w){re.escape(project.project_name.strip())}(?!\w)", question, re.IGNORECASE
        )
    ]
    if exact:
        return exact
    matches: list[tuple[int, str]] = []
    for project in portfolio.projects:
        name_words = _significant_words(project.project_name)
        if not name_words:
            continue
        overlap = len(asked & name_words)
        if overlap > 0 and distinctive & name_words:
            matches.append((overlap, project.project_id))

    # Strongest name overlap first, so an exact phrase beats a single shared word.
    matches.sort(key=lambda item: (-item[0], item[1]))
    strongest = matches[0][0] if matches else 0
    return [project_id for overlap, project_id in matches if overlap == strongest]


def supported_questions() -> list[SupportedQuestion]:
    """Every question Ask EPOS can answer, with any context it requires.

    Both halves are listed: the analyses that reach the model, and the lookups answered straight
    from records. A user cannot ask for something they were never shown, so the record-based
    answers are advertised alongside the analytical ones.
    """
    catalogue = {
        **QUESTION_TYPES,
        **answers.LOOKUP_QUESTIONS,
        semantic_router.EPOS_KNOWLEDGE: "What are the architecture, roadmap, and limitations of EPOS?",
        semantic_router.SCENARIO_ANALYSIS: "What happens if dependency D-2001 slips by 10 days?",
    }
    context_keys = {**QUESTION_CONTEXT_KEYS, **answers.LOOKUP_CONTEXT_KEYS}
    return [
        SupportedQuestion(
            intent=intent,
            question=question,
            requires_context=context_keys.get(intent),
        )
        for intent, question in catalogue.items()
    ]


def route(question: str) -> tuple[str | None, dict[str, str], int]:
    """Map free text to one supported intent, any ids found, and local match strength.

    Returns intent ``None`` when the question is out of scope. Identifiers are read from the raw
    text so a typo in the surrounding words cannot corrupt them. The confidence is how much of the
    question the matcher actually recognised, so a defaulted guess can be sent for interpretation
    instead of being answered literally.
    """
    context: dict[str, str] = {}

    project_match = _PROJECT_ID_PATTERN.search(question)
    if project_match:
        context["project_id"] = project_match.group(0).upper()
    change_match = _CHANGE_REQUEST_ID_PATTERN.search(question)
    if change_match:
        context["change_request_id"] = change_match.group(0).upper()

    if intent_matcher.is_refused(intent_matcher.clean(question)):
        return None, {}, 0

    result = intent_matcher.match(
        normalise(intent_matcher.prepare(question)),
        names_a_project="project_id" in context,
    )

    # An explicit change-request id settles the question regardless of phrasing.
    if "change_request_id" in context:
        return QUESTION_CHANGE_REQUEST_IMPACT, context, result.confidence
    # Naming a project alongside a decision question narrows it to that project's decisions.
    if result.intent == answers.PENDING_DECISIONS and "project_id" in context:
        return answers.PROJECT_DECISIONS, context, result.confidence
    # Naming one project turns a portfolio-wide question into a question about that project.
    if "project_id" in context and result.intent in _NARROWS_TO_ONE_PROJECT:
        return QUESTION_WHY_PROJECT_BAND, context, result.confidence
    return result.intent, context, result.confidence


def route_intent(question: str) -> tuple[str | None, dict[str, str]]:
    """Map free text to one supported intent plus any ids found in the text."""
    intent, context, _ = route(question)
    return intent, context


def describe(question: str) -> intent_matcher.Match:
    """Expose what the matcher understood, for diagnostics and evaluation."""
    return intent_matcher.match(normalise(intent_matcher.prepare(question)))


def _clarification(message: str, warnings: list[str] | None = None) -> CopilotAnswer:
    """Return a safe, model-free response asking the user to be more specific."""
    return CopilotAnswer(
        status="clarification",
        matched_intent=None,
        matched_question=None,
        executive_summary=message,
        key_findings=[],
        recommended_actions=[],
        source_ids=[],
        human_review_required=True,
        disclaimer=AI_DISCLAIMER,
        warnings=warnings or [],
        evidence=[],
        suggested_questions=list(SUGGESTED_QUESTIONS),
    )


def _capabilities() -> CopilotAnswer:
    """Explain what can be asked, rather than reporting a routing failure."""
    return _clarification(
        "I can look at delivery status and what is driving it, milestones at risk, risks without "
        "an owner, requirements still needing verification, the impact of a change request, and "
        "portfolio summaries. Ask in your own words, or start with one of these."
    )


def _project_menu(portfolio: PortfolioData) -> str:
    """The projects a user can actually ask about, so a miss is answerable rather than a dead end."""
    return ", ".join(
        f"{project.project_name} ({project.project_id})"
        for project in sorted(portfolio.projects, key=lambda item: item.project_name)
    )


def _validate_context(
    intent: str, context: dict[str, str], portfolio: PortfolioData, default_project_id: str | None
) -> tuple[dict[str, str] | None, str | None]:
    """Ensure a context-requiring intent has a context id that actually exists.

    Returns ``(context, None)`` on success or ``(None, message)`` describing what is missing.
    """
    required_key = QUESTION_CONTEXT_KEYS.get(intent)
    if required_key is None:
        return ({"comparison": "true"} if context.get("comparison") == "true" else {}), None

    value = context.get(required_key)
    if value is None and required_key == "project_id" and default_project_id:
        value = default_project_id
    if value is None:
        if required_key == "project_id":
            return None, (
                "I could not tell which project you mean. The projects in this workspace are: "
                f"{_project_menu(portfolio)}."
            )
        return None, "Name the change request you mean, for example by including its identifier."

    known = (
        portfolio.project_ids
        if required_key == "project_id"
        else {change.change_request_id for change in portfolio.change_requests}
    )
    if value not in known:
        if required_key == "project_id":
            return None, (
                f"{value} is not a project in this workspace. The projects recorded here are: "
                f"{_project_menu(portfolio)}."
            )
        return None, f"{value} was not found in the current portfolio."
    return {required_key: value}, None


def _evidence(intent: str, portfolio: PortfolioData, as_of_date: date, context: dict[str, str]):
    """Build the evidence package once; it is both displayed and sent for explanation."""
    with ai_trace.stage("evidence_build"):
        return build_evidence_package(intent, portfolio, as_of_date, context or None)


def _answer_deterministically(
    intent: str,
    portfolio: PortfolioData,
    as_of_date: date,
    context: dict[str, str],
    owner_name: str | None,
    decisions: list | None,
    owner_user_id: int | None = None,
) -> CopilotAnswer:
    """Dispatch a lookup intent to its record-based answer."""
    if intent == answers.LIST_PROJECTS:
        return answers.list_projects(
            portfolio,
            query=project_query.ProjectQuery.from_json(context.get("project_query"), portfolio),
            as_of_date=as_of_date,
        )
    if intent == answers.PORTFOLIO_CAPACITY:
        return answers.portfolio_capacity(portfolio)
    if intent == answers.BLOCKED_WORK:
        return answers.blocked_work(portfolio, context.get("project_id"))
    if intent == answers.PENDING_CHANGE_DECISIONS:
        return answers.pending_change_decisions(portfolio)
    if intent == answers.PENDING_DECISIONS:
        return answers.pending_decisions(decisions or [])
    if intent == answers.PROJECT_DECISIONS:
        project_id = context.get("project_id")
        if not project_id:
            return answers.pending_decisions(decisions or [])
        return answers.project_decisions(decisions or [], project_id)
    if intent == answers.MY_TASKS:
        if not owner_name:
            return _clarification("Sign in to see the work assigned to you.")
        return answers.my_tasks(portfolio, owner_name, as_of_date, owner_user_id=owner_user_id)
    if intent == answers.EPOS_METHODOLOGY:
        return answers.methodology()
    if intent == answers.EPOS_TRUST:
        return answers.trust()
    return answers.capabilities()


def _answer_intent(
    intent: str,
    question: str,
    portfolio: PortfolioData,
    as_of_date: date,
    context: dict[str, str],
    project_id: str | None,
    transport: Transport | None,
    owner_name: str | None,
    decisions: list | None,
    can_run_scenarios: bool,
    can_read_reports: bool,
    conversation_context: list[dict[str, str | None]] | None = None,
    owner_user_id: int | None = None,
) -> CopilotAnswer:
    """Answer one validated intent through its existing authoritative path."""
    if intent == QUESTION_WEEKLY_EXECUTIVE_UPDATE and not can_read_reports:
        return _clarification("Your role does not allow executive report access.")

    if intent == semantic_router.EPOS_KNOWLEDGE:
        return copilot_knowledge.answer(question, transport)

    if context.get("project_id") and context["project_id"] not in portfolio.project_ids:
        return _clarification(
            f"{context['project_id']} is not available in your current workspace. "
            f"The recorded projects are: {_project_menu(portfolio)}."
        )
    if intent != semantic_router.SCENARIO_ANALYSIS:
        query = project_query.ProjectQuery.from_json(context.get("project_query"), portfolio)
        scoped_ids = {context["project_id"]} if context.get("project_id") else set()
        if context.get("project_ids"):
            scoped_ids = set(json.loads(context["project_ids"])) & portfolio.project_ids
        if scoped_ids:
            portfolio = copilot_context.select_portfolio(portfolio, scoped_ids)
        if query.narrows and intent != answers.LIST_PROJECTS:
            # A restriction that cannot be applied is reported; it never widens to everything.
            if query.unmatched:
                return answers.unmatched_projects(portfolio, query)
            selected = project_query.select(query, portfolio, as_of_date).projects
            if not selected:
                return answers.list_projects(portfolio, query=query, as_of_date=as_of_date)
            portfolio = copilot_context.select_portfolio(
                portfolio, {project.project_id for project in selected}
            )

    if intent == workspace_evidence.WORKSPACE_EVIDENCE:
        record_type = context.get("record_type")
        if record_type not in workspace_evidence.RECORD_TYPES:
            return _clarification(
                "Name the kind of record you want: projects, milestones, tasks, risks, "
                "dependencies, actions, resources, requirements, test cases, trace links, or "
                "change requests."
            )
        domains = tuple(
            value
            for term in project_query.merged_terms(
                project_query.ProjectQuery.from_json(context.get("project_query"), portfolio)
            )
            if term.field == "domain" and not term.excluded
            for value in term.values
        )
        return workspace_evidence.answer(
            question,
            portfolio,
            workspace_evidence.Selection(
                record_type=record_type,
                project_id=context.get("project_id"),
                domains=domains,
                status=context.get("status_filter"),
            ),
            transport,
            conversation_context=conversation_context,
        )

    if intent == semantic_router.SCENARIO_ANALYSIS:
        return copilot_scenarios.answer(
            context.get("dependency_id"),
            int(context["additional_delay_days"]) if context.get("additional_delay_days") else None,
            portfolio,
            as_of_date,
            can_run_scenarios,
        )

    if intent in answers.DETERMINISTIC_INTENTS:
        return _answer_deterministically(
            intent, portfolio, as_of_date, context, owner_name, decisions, owner_user_id
        )

    resolved, problem = _validate_context(intent, context, portfolio, project_id)
    if resolved is None:
        return _clarification(problem or "More detail is needed to answer that.")

    evidence = _evidence(intent, portfolio, as_of_date, resolved)
    if not evidence.records:
        # Nothing to explain: asking a model to narrate an empty package invites invention.
        empty = copilot_presentation.from_calculated_evidence(intent, evidence, [])
        return empty.model_copy(update={"warnings": [_NO_EVIDENCE_NOTE]})
    response = ask_epos(
        intent,
        portfolio,
        as_of_date,
        resolved or None,
        transport=transport,
        user_question=question,
        conversation_context=conversation_context,
        evidence=evidence,
    )
    if response.status in {"unavailable", "error"}:
        return copilot_presentation.from_calculated_evidence(intent, evidence, response.warnings)
    return CopilotAnswer(
        status=response.status,
        matched_intent=intent,
        matched_question=QUESTION_TYPES[intent],
        executive_summary=response.executive_summary,
        key_findings=response.key_findings,
        recommended_actions=response.recommended_actions,
        source_ids=response.source_ids,
        human_review_required=response.human_review_required,
        disclaimer=response.disclaimer,
        warnings=response.warnings,
        evidence=[
            EvidenceRecordOut(
                record_type=record.record_type,
                record_id=record.record_id,
                fields=record.fields,
            )
            for record in evidence.records
        ],
        suggested_questions=[],
    )


def _unique(values: list[str]) -> list[str]:
    """Deduplicate while preserving the order a reader encountered."""
    return list(dict.fromkeys(values))


def _with_filters(answer: CopilotAnswer, query: project_query.ProjectQuery) -> CopilotAnswer:
    """Show the restrictions an answer used, so a reader can check and correct them."""
    if query.is_empty or answer.status == "clarification":
        return answer
    notes = [] if answer.applied_filters else project_query.interpretation_notes(query)
    summary = answer.executive_summary
    description = project_query.describe(query)
    if description:
        # The calculated attention summary counts the narrowed set; say which set it is.
        summary = summary.replace(
            " accessible projects need attention.",
            f" projects matching {description} need attention.",
        )
    return answer.model_copy(
        update={
            "executive_summary": summary,
            "applied_filters": answer.applied_filters or answers.applied_filters(query),
            "unapplied_filters": answer.unapplied_filters or list(query.unmatched),
            "warnings": _unique([*notes, *answer.warnings]),
        }
    )


def _combine_answers(primary: CopilotAnswer, secondary: CopilotAnswer) -> CopilotAnswer:
    """Combine two answers without asking a model to merge their facts."""
    evidence = list(
        {
            (record.record_type, record.record_id): record
            for record in [*primary.evidence, *secondary.evidence]
        }.values()
    )
    successful = [answer for answer in (primary, secondary) if answer.status == "ok"]
    status = "ok" if successful else primary.status
    intents = [
        intent
        for intent in (primary.matched_intent, secondary.matched_intent)
        if intent is not None
    ]
    return CopilotAnswer(
        status=status,
        matched_intent=" + ".join(intents) or None,
        matched_question="Combined answer",
        executive_summary="\n\n".join(answer.executive_summary for answer in (primary, secondary)),
        key_findings=_unique([*primary.key_findings, *secondary.key_findings]),
        recommended_actions=_unique([*primary.recommended_actions, *secondary.recommended_actions]),
        source_ids=_unique([*primary.source_ids, *secondary.source_ids]),
        human_review_required=(primary.human_review_required or secondary.human_review_required),
        disclaimer=AI_DISCLAIMER,
        warnings=_unique([*primary.warnings, *secondary.warnings]),
        evidence=evidence,
        suggested_questions=_unique([*primary.suggested_questions, *secondary.suggested_questions]),
    )


def ask(
    question: str,
    portfolio: PortfolioData,
    as_of_date: date,
    project_id: str | None = None,
    transport: Transport | None = None,
    owner_name: str | None = None,
    decisions: list | None = None,
    conversation_context: list[dict[str, str | None]] | None = None,
    can_run_scenarios: bool = False,
    can_read_reports: bool = False,
    owner_user_id: int | None = None,
    role_label: str | None = None,
    permissions: frozenset[str] = frozenset(),
    assistant_history: list[dict[str, str]] | None = None,
    registers: dict[str, list] | None = None,
    changes_since: copilot_agent.ChangeReader | None = None,
    sees_all_projects: bool = False,
) -> CopilotAnswer:
    """Answer a free-text question, or ask for clarification if it cannot be routed safely."""
    text = question.strip()
    if not text:
        return _clarification("Enter a question to get started.")
    if len(text) > _MAX_QUESTION_LENGTH:
        return _clarification("That question is too long. Shorten it and try again.")

    if copilot_agent.enabled() and not copilot_agent.is_blocked(text):
        with ai_trace.stage("assistant"):
            reply = copilot_agent.respond(
                copilot_agent.AssistantRequest(
                    question=text,
                    portfolio=portfolio,
                    as_of_date=as_of_date,
                    user=copilot_agent.AssistantUser(
                        name=owner_name or "",
                        user_id=owner_user_id,
                        role_label=role_label or "",
                        permissions=permissions,
                        sees_all_projects=sees_all_projects,
                    ),
                    page_project_id=project_id,
                    registers={"decision": list(decisions or []), **(registers or {})},
                    history=list(assistant_history or []),
                    can_run_scenarios=can_run_scenarios,
                    can_read_reports=can_read_reports,
                    transport=transport,
                    changes_since=changes_since,
                )
            )
        if reply is not None:
            return reply

    if intent_matcher.is_refused(intent_matcher.clean(text)):
        # Saying why is more useful than a generic refusal, and it is honest about the boundary:
        # Ask EPOS reads records and never writes them or discloses configuration.
        return _clarification(
            "I can only read what is already recorded. I cannot change records, run queries "
            "against the database, or show configuration. Ask me about delivery instead."
        )

    intent, context, local_confidence = route(text)

    # Slot filling before intent matching: restrictions such as "tech", "high priority" or "in
    # execution" are read as filters, and routing sees only what is being asked for.
    parsed = project_query.parse(text, portfolio)
    query = parsed.query
    if not query.is_empty and parsed.residual:
        intent, context, local_confidence = route(parsed.residual)
        if intent is None and _PLURAL_PROJECTS.search(text):
            intent = answers.LIST_PROJECTS

    mentioned_ids = copilot_context.known_ids(text, sorted(portfolio.project_ids))
    if mentioned_ids:
        context["project_id"] = mentioned_ids[0]

    # A project named in words is as good as one named by identifier.
    selector_requested = semantic_router.has_selector_signal(text)
    named = (
        resolve_projects_by_name(text, portfolio)
        if "project_id" not in context
        and not query.narrows
        and not (intent == answers.LIST_PROJECTS and selector_requested)
        else []
    )
    if len(named) == 1:
        context["project_id"] = named[0]
    explicit_projects = mentioned_ids or named
    comparing = len(explicit_projects) > 1 and re.search(
        r"\b(compare|versus|vs|between)\b", text, re.I
    )
    if comparing:
        context.pop("project_id", None)
        context["project_ids"] = json.dumps(explicit_projects)
        context["comparison"] = "true"
        intent = QUESTION_PROJECTS_NEEDING_ATTENTION
    intent, context = copilot_context.apply_context(
        text, intent, context, conversation_context, portfolio, project_id
    )
    if query.is_empty and context.get("project_query"):
        query = project_query.ProjectQuery.from_json(context["project_query"], portfolio)
    elif query.is_empty and context.get("domain_filter"):
        # Conversations saved before structured filters carried a bare domain list.
        query = project_query.from_domains(tuple(filter(None, context["domain_filter"].split("|"))))
    if query.narrows and not mentioned_ids:
        # The restriction defines the project set, even when asked from one project's page.
        context.pop("project_id", None)
    if intent == QUESTION_RISKS_WITHOUT_OWNER and not re.search(
        r"\b(unowned|no\s+(?:mitigation\s+)?owner|without\s+(?:(?:a|an)\s+)?(?:mitigation\s+)?owner|missing\s+(?:mitigation\s+)?owner)\b",
        text,
        re.IGNORECASE,
    ):
        intent = workspace_evidence.WORKSPACE_EVIDENCE
        context["record_type"] = "risk"
    if context.get("project_id") and intent in _NARROWS_TO_ONE_PROJECT:
        intent = QUESTION_WHY_PROJECT_BAND
    if context.get("project_id") and intent == answers.PENDING_DECISIONS:
        intent = answers.PROJECT_DECISIONS

    secondary_intent: str | None = None
    required_context = QUESTION_CONTEXT_KEYS.get(intent or "")
    if required_context == "project_id" and project_id:
        context.setdefault("project_id", project_id)
    context_is_missing = required_context is not None and required_context not in context
    exact_supported_question = (
        intent is not None
        and not conversation_context
        and _CANONICAL_INTENTS.get(_canonical_key(text)) == intent
    )
    if not exact_supported_question and (
        semantic_router.should_interpret(text, intent, bool(conversation_context), local_confidence)
        or context_is_missing
        or query.needs_interpretation
    ):
        with ai_trace.stage("semantic_classification"):
            semantic = semantic_router.interpret(
                text,
                portfolio,
                intent,
                context,
                transport,
                conversation_context,
                local_filter=query,
            )
        if semantic.is_usable_with(intent):
            if semantic.intent == semantic_router.OUT_OF_SCOPE:
                return _clarification(
                    "That is outside EPOS. I can help with project delivery, portfolio health, "
                    "risks, milestones, requirements, decisions, capacity, and how EPOS works."
                )
            if semantic.intent == semantic_router.NEEDS_CLARIFICATION:
                return _clarification(
                    "I found more than one plausible meaning. Name the project or delivery "
                    "area you want to explore."
                )
            intent = semantic.intent
            if context.get("project_id") and intent in _NARROWS_TO_ONE_PROJECT:
                intent = QUESTION_WHY_PROJECT_BAND
            if comparing:
                intent = QUESTION_PROJECTS_NEEDING_ATTENTION
            secondary_intent = semantic.secondary_intent
            if "project_id" not in context and not comparing and semantic.project_id:
                context["project_id"] = semantic.project_id
            if "change_request_id" not in context and semantic.change_request_id:
                context["change_request_id"] = semantic.change_request_id
            if semantic.project_filter is not None:
                query = project_query.merge(query, semantic.project_filter)
            elif semantic.domain_filter:
                query = project_query.merge(
                    query, project_query.from_domains(tuple(semantic.domain_filter.split("|")))
                )
            elif semantic.domain_was_requested and not query.terms:
                query = project_query.merge(query, project_query.from_domains(()))
            if semantic.record_type:
                context["record_type"] = semantic.record_type
            if semantic.status_filter:
                context["status_filter"] = semantic.status_filter
            if semantic.dependency_id:
                context["dependency_id"] = semantic.dependency_id
            if semantic.additional_delay_days is not None:
                context["additional_delay_days"] = str(semantic.additional_delay_days)

    context.pop("domain_filter", None)
    context.pop("domain_filter_applied", None)
    context.pop("project_query", None)
    if not query.is_empty:
        context["project_query"] = query.to_json()
        if intent is None and _PLURAL_PROJECTS.search(text):
            intent = answers.LIST_PROJECTS
        if intent == QUESTION_WHY_PROJECT_BAND and not mentioned_ids and not named:
            # "Which red projects..." asks about a set, not the page's current project.
            intent = QUESTION_PROJECTS_NEEDING_ATTENTION
            context.pop("project_id", None)

    if len(named) > 1 and "project_id" not in context and not comparing:
        names = {project.project_id: project.project_name for project in portfolio.projects}
        options = ", ".join(names.get(pid, pid) for pid in named[:3])
        return _clarification(
            f"More than one project matches that. Did you mean {options}?",
        )

    if intent is None:
        # A clarification asserts nothing: it explains what can be asked and suggests a start.
        return _clarification(
            "I can help with project status and what is driving it, delivery risks, milestones, "
            "workload, requirements, change requests, scenarios and portfolio summaries. "
            "Ask in your own words, or start with one of these."
        )

    if (
        intent == QUESTION_WHY_PROJECT_BAND
        and "project_id" not in context
        and context.get("project_ids")
    ):
        return _clarification(
            "The conversation includes several projects. Which project should I explain? Choose it by name or use the scope selector."
        )

    with ai_trace.stage("answer"):
        primary = _answer_intent(
            intent,
            text,
            portfolio,
            as_of_date,
            context,
            project_id,
            transport,
            owner_name,
            decisions,
            can_run_scenarios,
            can_read_reports,
            conversation_context,
            owner_user_id=owner_user_id,
        )
    primary = _with_filters(primary, query)
    candidate_project_id = context.get("project_id")
    if context.get("project_ids"):
        candidate_project_id = None
    resolved_project_id = (
        candidate_project_id if candidate_project_id in portfolio.project_ids else None
    )
    if secondary_intent is None:
        presented = copilot_presentation.present(
            primary.model_copy(update={"resolved_project_id": resolved_project_id}), portfolio
        )
        reference_ids = [item.project_id for item in presented.project_references]
        saved_context = {**context, "intent": intent}
        if saved_context.get("project_id") not in portfolio.project_ids:
            saved_context.pop("project_id", None)
        if resolved_project_id:
            saved_context["project_id"] = resolved_project_id
        elif reference_ids:
            saved_context["project_ids"] = json.dumps(reference_ids)
        return presented.model_copy(update={"context": saved_context})

    with ai_trace.stage("answer"):
        secondary = _answer_intent(
            secondary_intent,
            text,
            portfolio,
            as_of_date,
            context,
            project_id,
            transport,
            owner_name,
            decisions,
            can_run_scenarios,
            can_read_reports,
            conversation_context,
            owner_user_id=owner_user_id,
        )
    return copilot_presentation.present(
        _with_filters(_combine_answers(primary, secondary), query).model_copy(
            update={
                "resolved_project_id": resolved_project_id,
                "context": {**context, "intent": intent},
            }
        ),
        portfolio,
    )
