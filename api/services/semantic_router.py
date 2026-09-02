"""Azure-assisted interpretation for questions the local matcher cannot fully express.

The model may select an approved intent and extract selectors. It never receives permission to
answer, calculate, query storage, or invent an identifier. Every selector is validated against the
loaded synthetic portfolio before it can influence deterministic retrieval.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from api.services import copilot_answers as answers
from api.services import project_query
from api.services.workspace_evidence import RECORD_TYPES, WORKSPACE_EVIDENCE
from src.ai_assistant import CLASSIFICATION_MAX_TOKENS, Transport, complete_structured
from src.data_loader import PortfolioData
from src.scoring_rules import SCENARIO_MAX_DELAY_DAYS, SCENARIO_MIN_DELAY_DAYS

logger = logging.getLogger(__name__)

EPOS_KNOWLEDGE: Final[str] = "epos_knowledge"
OUT_OF_SCOPE: Final[str] = "out_of_scope"
NEEDS_CLARIFICATION: Final[str] = "needs_clarification"
SCENARIO_ANALYSIS: Final[str] = "scenario_analysis"

_ALLOWED_INTENTS: Final[tuple[str, ...]] = (
    "projects_needing_attention",
    "why_project_band",
    "risks_without_owner",
    "milestones_at_risk",
    "requirements_without_verification",
    "change_request_impact",
    "weekly_executive_update",
    answers.LIST_PROJECTS,
    answers.PORTFOLIO_CAPACITY,
    answers.MY_TASKS,
    answers.BLOCKED_WORK,
    answers.PENDING_CHANGE_DECISIONS,
    answers.PENDING_DECISIONS,
    answers.PROJECT_DECISIONS,
    answers.APPLICATION_CAPABILITIES,
    answers.EPOS_METHODOLOGY,
    answers.EPOS_TRUST,
    EPOS_KNOWLEDGE,
    WORKSPACE_EVIDENCE,
    SCENARIO_ANALYSIS,
    OUT_OF_SCOPE,
    NEEDS_CLARIFICATION,
)

_INTENT_GUIDE: Final[dict[str, str]] = {
    "projects_needing_attention": (
        "Portfolio position, highlights, priorities, biggest concerns, risk overview, or vague "
        "questions such as what is happening or what matters now. Questions asking which projects "
        "are late, behind schedule, struggling, or at risk belong here, not milestones_at_risk. "
        "Comparisons between the health, confidence, status, or risks of two or more projects also "
        "belong here. Portfolio-wide advisory questions belong here too: what should we do next, "
        "where should we focus, what should be reviewed or assessed first, and in what order."
    ),
    "why_project_band": (
        "Status, health, confidence, drivers, weaknesses, or explanation for one project, whether "
        "identified by ID, full or partial name, or wording such as this project. Advisory "
        "questions about one project belong here: what should I plan, what is my next step, what "
        "should I do about it. Classify the intent even when project context still needs "
        "validation."
    ),
    "risks_without_owner": "Risks missing a mitigation owner.",
    "milestones_at_risk": (
        "Late, slipping, blocked, or threatened milestones, deadlines, gates, or target dates. Use "
        "only when the question names that schedule object, not merely late projects."
    ),
    "requirements_without_verification": (
        "Requirements, traceability, verification coverage, test evidence, or verification gaps."
    ),
    "change_request_impact": "Downstream impact of one change request.",
    "weekly_executive_update": "A portfolio report, steering update, or executive summary.",
    answers.LIST_PROJECTS: (
        "List or filter projects. Use domain_filter when the user restricts the list by domain."
    ),
    answers.PORTFOLIO_CAPACITY: "Capacity, allocation, workload, or overloaded people.",
    answers.MY_TASKS: "Work assigned to the signed-in user.",
    answers.BLOCKED_WORK: "Blocked tasks, blockers, impediments, or stuck work.",
    answers.PENDING_CHANGE_DECISIONS: "Change requests awaiting a decision.",
    answers.PENDING_DECISIONS: (
        "The decision log, proposed decisions, or decisions awaiting an outcome when no specific "
        "project is named."
    ),
    answers.PROJECT_DECISIONS: (
        "Decisions recorded for one explicitly named or identified project. A known project ID is "
        "sufficient context."
    ),
    answers.APPLICATION_CAPABILITIES: "What EPOS does, how to use it, or what can be asked.",
    answers.EPOS_METHODOLOGY: "General scoring principles, factors, weights, or thresholds.",
    answers.EPOS_TRUST: (
        "Trust, explainability, governance, assumptions, weaknesses, system limitations, accuracy, "
        "or production readiness. Generic questions about weaknesses or limitations belong here "
        "unless they explicitly ask about a named project."
    ),
    EPOS_KNOWLEDGE: (
        "EPOS architecture, implementation, roadmap, testing approach, technology, features, "
        "security model, or user guidance not covered by the narrower product intents. General "
        "system limitations belong to epos_trust."
    ),
    WORKSPACE_EVIDENCE: (
        "Factual lookup over one workspace record type when no narrower intent fits: all risks, "
        "tasks, milestones, actions, dependencies, resources, requirements, test cases, trace "
        "links, changes, or projects; ownership and stored status questions; record details. "
        "Questions about stored lifecycle state, such as which records are completed, closed, "
        "cancelled, or in a named phase, belong here with status_filter set to the wording the "
        "user used. Set record_type and any project, domain, or status selector supplied by the "
        "user."
    ),
    SCENARIO_ANALYSIS: (
        "A what-if dependency-delay simulation. Use only when the user asks what happens if a "
        "dependency slips or explicitly asks to run a scenario. Extract dependency_id and "
        "additional_delay_days only when supplied."
    ),
    OUT_OF_SCOPE: "Not about EPOS, project delivery, or the records available in EPOS.",
    NEEDS_CLARIFICATION: "About EPOS, but too ambiguous to choose a useful answer safely.",
}

# Questions carrying one of these signals need more than a single local intent. Azure may extract a
# selector, but Python still validates and applies it.
_SELECTOR_SIGNALS: Final[re.Pattern[str]] = re.compile(
    r"\b(domain|only|except|excluding|within|under|managed by|owned by|from the)\b",
    re.IGNORECASE,
)
_MIXED_SIGNALS: Final[re.Pattern[str]] = re.compile(
    r"\b(and also|as well as|plus|and then)\b", re.IGNORECASE
)
_FOLLOW_UP_SIGNALS: Final[re.Pattern[str]] = re.compile(
    r"\b(what about|how about|and that|and those|the other|same one|that project|"
    r"those projects|it|them)\b",
    re.IGNORECASE,
)
_GENERIC_RECORD_SIGNALS: Final[re.Pattern[str]] = re.compile(
    r"\b(all|every|details? (?:of|for|about)|who owns|owner of|status of)\b.*"
    r"\b(projects?|milestones?|tasks?|risks?|dependencies?|actions?|resources?|"
    r"requirements?|test cases?|trace links?|change requests?)\b",
    re.IGNORECASE,
)
_SCENARIO_SIGNALS: Final[re.Pattern[str]] = re.compile(
    r"\b(what if|simulate|simulation|scenario|dependency .* slips?|slips? by \d+ days?)\b",
    re.IGNORECASE,
)
_COMPARISON_SIGNALS: Final[re.Pattern[str]] = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference between)\b", re.IGNORECASE
)

# A local match assembled from a single recognised word is a guess: the matcher defaulted the
# missing half of the (subject, operation) pair rather than recognising it. "What should I plan
# next?" scores only on "project" and would otherwise be answered as a request to list projects.
WEAK_LOCAL_MATCH: Final[int] = 2

_ROUTE_SYSTEM_PROMPT: Final[str] = (
    "You classify questions for EPOS, an engineering project-delivery application. "
    "Return only the strict JSON object requested. Do not answer the question. Do not calculate "
    "health, confidence, severity, change impact, dates, or scenarios. Choose exactly one allowed "
    "intent. Extract an identifier or domain phrase only when the user supplied or clearly named "
    "it. Never invent an identifier, project, domain, owner, date, or filter. Use out_of_scope for "
    "questions unrelated to EPOS or project delivery. Use needs_clarification only when the request "
    "is in scope but genuinely has no identifiable operation; do not use it merely because a "
    "project or change-request selector is missing. The application validates required context and "
    "will ask for it separately. Set secondary_intent only when the "
    "latest question asks a second independent EPOS question; otherwise set it to null. Recent "
    "conversation turns provide reference context only, and the latest question always controls. "
    "When the question restricts which projects count, express every restriction in "
    "project_filter using only values from the allowed lists: an umbrella word such as tech or "
    "green energy may select several recorded domains that it plainly covers. Put any restriction "
    "that no allowed value can express in unmatched_terms, in the user's own words; never drop a "
    "restriction silently. Leave project_filter lists empty when the question sets no restriction."
)

_ROUTE_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(_ALLOWED_INTENTS)},
        "secondary_intent": {
            "type": ["string", "null"],
            "enum": [None, *_ALLOWED_INTENTS],
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "project_id": {"type": ["string", "null"]},
        "project_name": {"type": ["string", "null"]},
        "change_request_id": {"type": ["string", "null"]},
        "domain_filter": {"type": ["string", "null"]},
        "record_type": {"type": ["string", "null"], "enum": [None, *RECORD_TYPES]},
        "status_filter": {"type": ["string", "null"]},
        "dependency_id": {"type": ["string", "null"]},
        "additional_delay_days": {"type": ["integer", "null"]},
        "clarification": {"type": ["string", "null"]},
    },
    "required": [
        "intent",
        "secondary_intent",
        "confidence",
        "project_id",
        "project_name",
        "change_request_id",
        "domain_filter",
        "record_type",
        "status_filter",
        "dependency_id",
        "additional_delay_days",
        "clarification",
    ],
    "additionalProperties": False,
}

_FILTER_LISTS: Final[tuple[tuple[str, str, bool], ...]] = (
    ("domains", "domain", False),
    ("excluded_domains", "domain", True),
    ("phases", "phase", False),
    ("priorities", "priority", False),
    ("managers", "manager", False),
    ("health_bands", "health_band", False),
)


def _enum_array(values: tuple[str, ...]) -> dict[str, object]:
    if not values:
        return {"type": "array", "items": {"type": "string"}, "maxItems": 0}
    return {"type": "array", "items": {"type": "string", "enum": list(values)}}


def route_schema(portfolio: PortfolioData) -> dict[str, object]:
    """The strict reply schema, with project filters limited to values recorded in the snapshot."""
    vocabulary = project_query.Vocabulary.of(portfolio)
    project_filter = {
        "type": "object",
        "properties": {
            **{
                name: _enum_array(vocabulary.values_for(field_name))
                for name, field_name, _ in _FILTER_LISTS
            },
            "name_keywords": {"type": "array", "items": {"type": "string"}},
            "unmatched_terms": {"type": "array", "items": {"type": "string"}},
            "sort": {
                "type": ["string", "null"],
                "enum": [None, *project_query.SORT_LABELS],
            },
            "limit": {"type": ["integer", "null"]},
        },
        "required": [
            *(name for name, _, _ in _FILTER_LISTS),
            "name_keywords",
            "unmatched_terms",
            "sort",
            "limit",
        ],
        "additionalProperties": False,
    }
    return {
        **_ROUTE_SCHEMA,
        "properties": {**_ROUTE_SCHEMA["properties"], "project_filter": project_filter},
        "required": [*_ROUTE_SCHEMA["required"], "project_filter"],
    }


class _ModelProjectFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[str]
    excluded_domains: list[str]
    phases: list[str]
    priorities: list[str]
    managers: list[str]
    health_bands: list[str]
    name_keywords: list[str]
    unmatched_terms: list[str]
    sort: str | None
    limit: int | None


class _ModelRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    secondary_intent: str | None
    confidence: Literal["high", "medium", "low"]
    project_id: str | None
    project_name: str | None
    change_request_id: str | None
    domain_filter: str | None
    record_type: str | None
    status_filter: str | None
    dependency_id: str | None
    additional_delay_days: int | None
    clarification: str | None
    # Optional so replies from older schema versions still validate.
    project_filter: _ModelProjectFilter | None = None


@dataclass(frozen=True)
class SemanticRoute:
    """A validated semantic interpretation, containing no model-authored facts."""

    status: Literal["ok", "unavailable", "error", "invalid_response"]
    intent: str | None = None
    secondary_intent: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    project_id: str | None = None
    change_request_id: str | None = None
    domain_filter: str | None = None
    domain_was_requested: bool = False
    record_type: str | None = None
    status_filter: str | None = None
    dependency_id: str | None = None
    additional_delay_days: int | None = None
    clarification: str | None = None
    project_filter: project_query.ProjectQuery | None = None
    warnings: tuple[str, ...] = ()

    @property
    def is_confident(self) -> bool:
        return self.status == "ok" and self.confidence == "high" and self.intent is not None

    def is_usable_with(self, local_intent: str | None) -> bool:
        """Accept high confidence, or medium confidence corroborated by local interpretation."""
        if self.status != "ok" or self.intent is None:
            return False
        return self.confidence == "high" or (
            self.confidence == "medium"
            and (
                self.intent == local_intent
                or self.domain_filter is not None
                or (self.project_filter is not None and not self.project_filter.is_empty)
            )
        )


def should_interpret(
    question: str,
    local_intent: str | None,
    has_conversation_context: bool = False,
    local_confidence: int | None = None,
) -> bool:
    """Use Azure for the long tail and for questions carrying retrieval modifiers."""
    return (
        local_intent is None
        or (local_confidence is not None and local_confidence < WEAK_LOCAL_MATCH)
        or _SELECTOR_SIGNALS.search(question) is not None
        or _MIXED_SIGNALS.search(question) is not None
        or _GENERIC_RECORD_SIGNALS.search(question) is not None
        or _SCENARIO_SIGNALS.search(question) is not None
        or _COMPARISON_SIGNALS.search(question) is not None
        or (has_conversation_context and _FOLLOW_UP_SIGNALS.search(question) is not None)
    )


def has_selector_signal(question: str) -> bool:
    """Return whether the question asks retrieval to be narrowed."""
    return _SELECTOR_SIGNALS.search(question) is not None


def build_route_payload(
    question: str,
    portfolio: PortfolioData,
    local_intent: str | None,
    local_context: dict[str, str],
    recent_turns: list[dict[str, str | None]] | None = None,
    local_filter: project_query.ProjectQuery | None = None,
) -> dict[str, object]:
    """Build the classifier request from approved intent and portfolio vocabularies."""
    projects = [
        {"project_id": item.project_id, "project_name": item.project_name, "domain": item.domain}
        for item in sorted(portfolio.projects, key=lambda project: project.project_id)
    ]
    vocabulary = project_query.Vocabulary.of(portfolio)
    user_content = json.dumps(
        {
            "question": question,
            "local_interpretation": {
                "intent": local_intent,
                "context": {
                    key: value for key, value in local_context.items() if key != "project_query"
                },
                "project_filter": (
                    project_query.describe(local_filter) or None if local_filter else None
                ),
                "unmatched_terms": list(local_filter.unmatched) if local_filter else [],
            },
            "recent_conversation": (recent_turns or [])[-6:],
            "allowed_intents": _INTENT_GUIDE,
            "known_projects": projects,
            "known_change_request_ids": sorted(
                change.change_request_id for change in portfolio.change_requests
            ),
            "known_dependencies": [
                {
                    "dependency_id": dependency.dependency_id,
                    "dependency_name": dependency.dependency_name,
                }
                for dependency in sorted(
                    portfolio.dependencies, key=lambda item: item.dependency_id
                )
            ],
            "scenario_delay_bounds": {
                "minimum_days": SCENARIO_MIN_DELAY_DAYS,
                "maximum_days": SCENARIO_MAX_DELAY_DAYS,
            },
            "known_domains": sorted({project.domain for project in portfolio.projects}),
            "known_phases": list(vocabulary.phases),
            "known_business_priorities": list(vocabulary.priorities),
            "known_project_managers": list(vocabulary.managers),
            "health_bands": list(project_query.HEALTH_BAND_NAMES),
        },
        sort_keys=True,
    )
    return {
        "messages": [
            {"role": "system", "content": _ROUTE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "epos_semantic_route",
                "strict": True,
                "schema": route_schema(portfolio),
            },
        },
    }


def _project_id(model: _ModelRoute, portfolio: PortfolioData) -> str | None:
    """Resolve only to a project that actually exists in the loaded portfolio."""
    known = {project.project_id.upper(): project.project_id for project in portfolio.projects}
    if model.project_id:
        matched = known.get(model.project_id.strip().upper())
        if matched:
            return matched

    if not model.project_name:
        return None
    asked = " ".join(model.project_name.lower().split())
    matches = [
        project.project_id
        for project in portfolio.projects
        if project.project_name.lower() == asked
    ]
    return matches[0] if len(matches) == 1 else None


def _change_request_id(model: _ModelRoute, portfolio: PortfolioData) -> str | None:
    known = {item.change_request_id.upper() for item in portfolio.change_requests}
    candidate = model.change_request_id.strip().upper() if model.change_request_id else None
    return candidate if candidate in known else None


def _dependency_id(model: _ModelRoute, portfolio: PortfolioData) -> str | None:
    known = {item.dependency_id.upper() for item in portfolio.dependencies}
    candidate = model.dependency_id.strip().upper() if model.dependency_id else None
    return candidate if candidate in known else None


def _delay_days(model: _ModelRoute) -> int | None:
    value = model.additional_delay_days
    if value is None or not SCENARIO_MIN_DELAY_DAYS <= value <= SCENARIO_MAX_DELAY_DAYS:
        return None
    return value


def matching_domains(requested: str | None, portfolio: PortfolioData) -> tuple[str, ...]:
    """Map a model-extracted phrase onto stored domain values without inventing a category."""
    if not requested:
        return ()
    tokens = set(re.findall(r"[a-z0-9]+", requested.lower()))
    if not tokens:
        return ()

    matches = []
    for domain in sorted({project.domain for project in portfolio.projects}):
        domain_tokens = set(re.findall(r"[a-z0-9]+", domain.lower()))
        if tokens <= domain_tokens or domain_tokens <= tokens or tokens & domain_tokens:
            matches.append(domain)
    return tuple(matches)


def _project_filter(
    model: _ModelRoute, portfolio: PortfolioData
) -> tuple[project_query.ProjectQuery | None, list[str]]:
    """Turn the model's filter into a query holding only recorded values."""
    reply = model.project_filter
    if reply is None:
        return None, []
    vocabulary = project_query.Vocabulary.of(portfolio)
    phrase = (model.domain_filter or "").strip()[:60] or "your wording"
    terms: list[project_query.Term] = []
    warnings: list[str] = []
    rejected: list[str] = []
    for name, field_name, excluded in _FILTER_LISTS:
        requested = getattr(reply, name)
        values = vocabulary.valid(field_name, requested)
        if len(values) < len(requested):
            warnings.append("The semantic route named a filter value outside the portfolio.")
            if not values:
                # The user asked for a restriction; an invalid value must not turn into "all".
                rejected.append(model.domain_filter or str(requested[0]))
        if values:
            terms.append(
                project_query.Term(field_name, values, phrase, excluded, interpreted=True)  # type: ignore[arg-type]
            )
    keywords = vocabulary.valid("name", reply.name_keywords)
    if keywords:
        terms.append(project_query.Term("name", keywords, ", ".join(keywords), interpreted=True))
    rejected_keywords = [
        keyword for keyword in reply.name_keywords if keyword.strip().lower() not in keywords
    ]
    unmatched = [
        term.strip()[:60]
        for term in [*reply.unmatched_terms, *rejected_keywords, *rejected]
        if isinstance(term, str) and term.strip()
    ]
    sort = reply.sort if reply.sort in project_query.SORT_LABELS else None
    limit = (
        reply.limit
        if reply.limit is not None and 1 <= reply.limit <= project_query.MAX_LIMIT
        else None
    )
    query = project_query.ProjectQuery(
        terms=tuple(terms),
        unmatched=tuple(dict.fromkeys(unmatched))[:3],
        sort=sort,  # type: ignore[arg-type]
        limit=limit,
    )
    return query, list(dict.fromkeys(warnings))


def interpret(
    question: str,
    portfolio: PortfolioData,
    local_intent: str | None,
    local_context: dict[str, str],
    transport: Transport | None = None,
    recent_turns: list[dict[str, str | None]] | None = None,
    local_filter: project_query.ProjectQuery | None = None,
) -> SemanticRoute:
    """Classify a question and reject every selector not present in the portfolio."""
    completion = complete_structured(
        build_route_payload(
            question, portfolio, local_intent, local_context, recent_turns, local_filter
        ),
        transport,
        max_tokens=CLASSIFICATION_MAX_TOKENS,
    )
    if completion.status != "ok" or completion.content is None:
        return SemanticRoute(completion.status, warnings=completion.warnings)

    try:
        model = _ModelRoute.model_validate_json(completion.content)
        if model.intent not in _ALLOWED_INTENTS:
            raise ValueError("model returned an intent outside the allowlist")
        if model.secondary_intent and model.secondary_intent not in _ALLOWED_INTENTS:
            raise ValueError("model returned a secondary intent outside the allowlist")
    except (ValidationError, ValueError) as exc:
        logger.warning("Semantic route was rejected: %s", type(exc).__name__)
        return SemanticRoute(
            "invalid_response",
            warnings=(f"Semantic route validation failed with {type(exc).__name__}.",),
        )

    domains = matching_domains(model.domain_filter, portfolio)
    domain_filter = "|".join(domains) if domains else None
    warnings: list[str] = []
    if model.project_id and _project_id(model, portfolio) is None:
        warnings.append("The semantic route named a project outside the current portfolio.")
    if model.change_request_id and _change_request_id(model, portfolio) is None:
        warnings.append("The semantic route named an unknown change request.")
    if model.domain_filter and not domains:
        warnings.append("The semantic route named a domain outside the current portfolio.")
    if model.dependency_id and _dependency_id(model, portfolio) is None:
        warnings.append("The semantic route named an unknown dependency.")
    if model.additional_delay_days is not None and _delay_days(model) is None:
        warnings.append("The semantic route named a delay outside the supported range.")
    project_filter, filter_warnings = _project_filter(model, portfolio)
    warnings.extend(filter_warnings)

    return SemanticRoute(
        status="ok",
        intent=model.intent,
        secondary_intent=(
            model.secondary_intent
            if model.secondary_intent not in {model.intent, OUT_OF_SCOPE, NEEDS_CLARIFICATION}
            else None
        ),
        confidence=model.confidence,
        project_id=_project_id(model, portfolio),
        change_request_id=_change_request_id(model, portfolio),
        domain_filter=domain_filter,
        domain_was_requested=model.domain_filter is not None,
        record_type=model.record_type,
        status_filter=model.status_filter,
        dependency_id=_dependency_id(model, portfolio),
        additional_delay_days=_delay_days(model),
        clarification=model.clarification,
        project_filter=project_filter,
        warnings=tuple(warnings),
    )
