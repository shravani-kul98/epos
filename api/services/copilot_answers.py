"""Deterministic answers for questions that are lookups rather than analysis.

A request such as "list all projects" has one correct answer that already exists in the workspace.
Sending it to a language model adds latency and a hallucination risk for no benefit. These
responses are assembled directly from records the caller is authorised to see, and every one of
them cites the identifiers it used.
"""

from __future__ import annotations

from datetime import date
from difflib import get_close_matches

from api import labels
from api.schemas import AppliedFilterOut, CopilotAnswer, EvidenceRecordOut
from api.services import project_query
from src.data_loader import PortfolioData
from src.schemas import Task
from src.scoring_rules import (
    CONFIDENCE_WEIGHTS,
    HEALTH_BANDS,
    HEALTH_WEIGHTS,
    is_terminal_schedule_status,
)
from src.ui_formatting import format_score
from src.wording import count_of
from src.workflow_rules import is_change_request_decided

DETERMINISTIC_RESPONSE_NOTICE = (
    "Deterministic response from recorded evidence; no AI-generated text."
)

# Intent names handled here rather than by the model.
LIST_PROJECTS = "list_projects"
PORTFOLIO_CAPACITY = "portfolio_capacity"
MY_TASKS = "my_tasks"
BLOCKED_WORK = "blocked_work"
PENDING_CHANGE_DECISIONS = "pending_change_decisions"
PENDING_DECISIONS = "pending_decisions"
PROJECT_DECISIONS = "project_decisions"
APPLICATION_CAPABILITIES = "application_capabilities"
EPOS_METHODOLOGY = "epos_methodology"
EPOS_TRUST = "epos_trust"

DETERMINISTIC_INTENTS = frozenset(
    {
        LIST_PROJECTS,
        PORTFOLIO_CAPACITY,
        MY_TASKS,
        BLOCKED_WORK,
        PENDING_CHANGE_DECISIONS,
        PENDING_DECISIONS,
        PROJECT_DECISIONS,
        APPLICATION_CAPABILITIES,
        EPOS_METHODOLOGY,
        EPOS_TRUST,
    }
)

# Intents answered from how the product works rather than from portfolio records.
PRODUCT_INTENTS = frozenset({APPLICATION_CAPABILITIES, EPOS_METHODOLOGY, EPOS_TRUST})

# How each record-based intent is offered to the user. These sit alongside the analysis questions
# so the whole surface is discoverable, rather than only the parts that reach a model.
LOOKUP_QUESTIONS: dict[str, str] = {
    LIST_PROJECTS: "List every project in the portfolio.",
    PORTFOLIO_CAPACITY: "Who is over capacity?",
    MY_TASKS: "What is assigned to me?",
    BLOCKED_WORK: "What work is blocked?",
    PENDING_CHANGE_DECISIONS: "Which change requests are awaiting a decision?",
    PENDING_DECISIONS: "Which decisions are still waiting?",
    PROJECT_DECISIONS: "Which decisions affect this project?",
    APPLICATION_CAPABILITIES: "What can EPOS help me with?",
    EPOS_METHODOLOGY: "How does EPOS calculate health and confidence?",
    EPOS_TRUST: "How far can these numbers be trusted?",
}

# Context a lookup needs before it can be answered.
LOOKUP_CONTEXT_KEYS: dict[str, str] = {PROJECT_DECISIONS: "project_id"}

# Intents that read the decision log rather than the scored portfolio.
DECISION_INTENTS = frozenset({PENDING_DECISIONS, PROJECT_DECISIONS})


def _answer(
    intent: str,
    question: str,
    summary: str,
    findings: list[str],
    actions: list[str],
    source_ids: list[str],
    evidence: list[EvidenceRecordOut],
) -> CopilotAnswer:
    """Build a response that carries its own evidence and needs no review of generated prose."""
    return CopilotAnswer(
        status="ok",
        matched_intent=intent,
        matched_question=question,
        executive_summary=summary,
        key_findings=findings,
        recommended_actions=actions,
        source_ids=source_ids,
        # Nothing here is generated, so there is no drafted language to check.
        human_review_required=False,
        disclaimer=DETERMINISTIC_RESPONSE_NOTICE,
        warnings=[],
        evidence=evidence,
        suggested_questions=[],
    )


def _record(record_type: str, record_id: str, fields: dict[str, str]) -> EvidenceRecordOut:
    return EvidenceRecordOut(record_type=record_type, record_id=record_id, fields=fields)


def applied_filters(query: project_query.ProjectQuery) -> list[AppliedFilterOut]:
    """The restrictions an answer applied, in the form the interface shows back."""
    shown = [
        AppliedFilterOut(
            field=term.field,
            label=project_query.FIELD_LABELS[term.field],
            values=list(term.values),
            excluded=term.excluded,
            interpreted_from=term.phrase if term.interpreted else None,
        )
        for term in project_query.merged_terms(query)
    ]
    if query.sort:
        shown.append(
            AppliedFilterOut(
                field="order", label="Order", values=[project_query.SORT_LABELS[query.sort]]
            )
        )
    if query.limit:
        shown.append(
            AppliedFilterOut(field="limit", label="Showing", values=[f"up to {query.limit}"])
        )
    return shown


def _alternatives(portfolio: PortfolioData, phrases: tuple[str, ...]) -> list[str]:
    """Questions a reader can pick instead of an unrecognised filter."""
    domains = sorted({project.domain for project in portfolio.projects})
    close = [
        domain
        for phrase in phrases
        for domain in get_close_matches(phrase.title(), domains, n=2, cutoff=0.5)
    ]
    picks = list(dict.fromkeys([*close, *domains]))[:2]
    return [*(f"List {domain} projects" for domain in picks), "List all projects"]


def unmatched_projects(
    portfolio: PortfolioData, query: project_query.ProjectQuery
) -> CopilotAnswer:
    """Say which requested restriction is not recorded, instead of answering a wider question."""
    vocabulary = project_query.Vocabulary.of(portfolio)
    phrases = [phrase if phrase.startswith("the ") else f"“{phrase}”" for phrase in query.unmatched]
    scope = " or ".join(phrases) or "the category you asked for"
    answer = _answer(
        LIST_PROJECTS,
        "List all projects",
        # Naming the recorded values matters: the alternative is answering a narrower or wider
        # question than the user asked without saying that their category does not exist here.
        f"I couldn't match {scope} to a recorded domain, phase, business priority, project "
        "manager or health band, so no projects are listed. "
        f"The domains recorded in this workspace are: {', '.join(vocabulary.domains)}. "
        f"Recorded phases are {', '.join(vocabulary.phases)}; business priorities are "
        f"{', '.join(vocabulary.priorities)}; health bands are "
        f"{', '.join(project_query.HEALTH_BAND_NAMES)}.",
        [],
        [],
        [],
        [],
    )
    return answer.model_copy(
        update={
            "suggested_questions": _alternatives(portfolio, query.unmatched),
            "applied_filters": applied_filters(query),
            "unapplied_filters": list(query.unmatched),
        }
    )


def _project_finding(project, health: dict[str, tuple[float, str]]) -> str:
    finding = (
        f"{project.project_name} ({project.project_id}): {project.domain}, "
        f"{project.project_phase} phase, {project.business_priority} priority, "
        f"managed by {project.project_manager}"
    )
    if project.project_id in health:
        score, band = health[project.project_id]
        finding += f"; health {format_score(score)} ({band})"
    return finding + "."


def _selection_summary(query: project_query.ProjectQuery, count: int, total: int) -> str:
    description = project_query.describe(query)
    order = project_query.SORT_LABELS.get(query.sort or "")
    if not query.narrows and not order:
        noun = "project" if count == 1 else "projects"
        return f"There {'is' if count == 1 else 'are'} {count} {noun} in this workspace."
    if count == 0:
        return f"No projects match {description or 'those filters'}."
    if query.limit:
        summary = f"Showing {count} of {total} projects"
        summary += f" matching {description}" if description else ""
    elif description:
        summary = f"{count} of {total} projects {'matches' if count == 1 else 'match'} "
        summary += description
    else:
        summary = f"All {count} projects"
    return summary + (f", {order}" if order else "") + "."


def list_projects(
    portfolio: PortfolioData,
    domains: tuple[str, ...] = (),
    domain_filter_applied: bool = False,
    *,
    query: project_query.ProjectQuery | None = None,
    as_of_date: date | None = None,
) -> CopilotAnswer:
    """Projects in the workspace, restricted only by constraints resolved onto recorded values."""
    if query is None:
        query = (
            project_query.from_domains(domains)
            if domain_filter_applied
            else project_query.ProjectQuery()
        )
    if query.unmatched:
        return unmatched_projects(portfolio, query)
    selection = project_query.select(query, portfolio, as_of_date)
    projects = selection.projects
    evidence = [
        _record(
            "project",
            project.project_id,
            {
                "project_name": project.project_name,
                "domain": project.domain,
                "project_manager": project.project_manager,
                "project_phase": project.project_phase,
                "business_priority": project.business_priority,
                **(
                    {
                        "health_score": format_score(selection.health[project.project_id][0]),
                        "health_band": selection.health[project.project_id][1],
                    }
                    if project.project_id in selection.health
                    else {}
                ),
            },
        )
        for project in projects
    ]
    summary = " ".join(
        [
            _selection_summary(query, len(projects), selection.total),
            *project_query.interpretation_notes(query),
        ]
    )
    follow_ups = (
        ["Which of those projects need attention?", "What risks are recorded for those projects?"]
        if projects
        else []
    )
    if query.needs_interpretation or (query.narrows and not projects):
        follow_ups.append("List all projects")
    answer = _answer(
        LIST_PROJECTS,
        "List all projects",
        summary,
        [_project_finding(project, selection.health) for project in projects],
        [],
        [project.project_id for project in projects],
        evidence,
    )
    return answer.model_copy(
        update={"suggested_questions": follow_ups, "applied_filters": applied_filters(query)}
    )


def portfolio_capacity(portfolio: PortfolioData) -> CopilotAnswer:
    """People allocated beyond their recorded weekly capacity."""
    over = [resource for resource in portfolio.resources if resource.is_overallocated]
    if not over:
        return _answer(
            PORTFOLIO_CAPACITY,
            "Which people are overloaded?",
            "Nobody is allocated beyond their recorded capacity.",
            [],
            [],
            [],
            [],
        )

    def utilisation(resource) -> float:
        return resource.allocated_hours / resource.capacity_hours * 100

    over.sort(key=utilisation, reverse=True)
    findings = [
        f"{resource.resource_name} is allocated {resource.allocated_hours} hours against "
        f"{resource.capacity_hours} available on {resource.project_id} "
        f"({utilisation(resource):.0f}% of capacity)."
        for resource in over
    ]
    evidence = [
        _record(
            "resource",
            resource.resource_id,
            {
                "resource_name": resource.resource_name,
                "project_id": resource.project_id,
                "allocated_hours": str(resource.allocated_hours),
                "capacity_hours": str(resource.capacity_hours),
                "week_start_date": str(resource.week_start_date),
            },
        )
        for resource in over
    ]
    return _answer(
        PORTFOLIO_CAPACITY,
        "Which people are overloaded?",
        f"{len(over)} {'person is' if len(over) == 1 else 'people are'} allocated beyond capacity.",
        findings,
        ["Rebalance the allocation or adjust the plan with the accountable manager."],
        [resource.resource_id for resource in over],
        evidence,
    )


def blocked_work(portfolio: PortfolioData, project_id: str | None = None) -> CopilotAnswer:
    """Tasks recorded as blocked, optionally within one project."""
    tasks = [task for task in portfolio.tasks if task.is_blocked]
    if project_id:
        tasks = [task for task in tasks if task.project_id == project_id]

    scope = f" in {project_id}" if project_id else ""
    if not tasks:
        return _answer(
            BLOCKED_WORK,
            "What work is blocked?",
            f"No work is recorded as blocked{scope}.",
            [],
            [],
            [],
            [],
        )

    findings = [
        f"{task.task_name} ({task.task_id}) on {task.project_id} is blocked at "
        f"{task.completion_percent}% complete, owned by {task.owner or 'nobody'}."
        for task in tasks
    ]
    evidence = [
        _record(
            "task",
            task.task_id,
            {
                "task_name": task.task_name,
                "project_id": task.project_id,
                "owner": task.owner or "Unassigned",
                "status": task.status,
                "forecast_end_date": str(task.forecast_end_date),
            },
        )
        for task in tasks
    ]
    unowned = [task for task in tasks if not task.owner]
    actions = ["Confirm what each blocker is waiting on and who is clearing it."]
    if unowned:
        actions.append(
            f"Assign an owner to {count_of(len(unowned), 'blocked task')} that "
            f"{'has' if len(unowned) == 1 else 'have'} none."
        )

    return _answer(
        BLOCKED_WORK,
        "What work is blocked?",
        f"{len(tasks)} {'task is' if len(tasks) == 1 else 'tasks are'} blocked{scope}.",
        findings,
        actions,
        [task.task_id for task in tasks],
        evidence,
    )


def my_tasks(
    portfolio: PortfolioData,
    owner_name: str,
    as_of_date: date,
    owner_user_id: int | None = None,
) -> CopilotAnswer:
    """Work assigned to the signed-in user: by account, or by recorded name for legacy tasks."""
    needle = owner_name.strip().lower()

    def is_mine(task: Task) -> bool:
        if task.owner_user_id is not None:
            return task.owner_user_id == owner_user_id
        return (task.owner or "").strip().lower() == needle

    tasks = [
        task
        for task in portfolio.tasks
        if is_mine(task) and not is_terminal_schedule_status(task.status)
    ]
    if not tasks:
        return _answer(
            MY_TASKS,
            "What am I responsible for?",
            f"No open work is recorded against {owner_name}.",
            [],
            [],
            [],
            [],
        )

    tasks.sort(key=lambda task: task.forecast_end_date)
    overdue = [task for task in tasks if task.forecast_end_date < as_of_date]
    blocked = [task for task in tasks if task.is_blocked]

    findings = [
        f"{task.task_name} ({task.task_id}) on {task.project_id} is due "
        f"{task.forecast_end_date} at {task.completion_percent}% complete"
        f"{', and is blocked' if task.is_blocked else ''}."
        for task in tasks
    ]
    evidence = [
        _record(
            "task",
            task.task_id,
            {
                "task_name": task.task_name,
                "project_id": task.project_id,
                "status": task.status,
                "forecast_end_date": str(task.forecast_end_date),
            },
        )
        for task in tasks
    ]

    parts = [f"{len(tasks)} open {'item' if len(tasks) == 1 else 'items'}"]
    if overdue:
        parts.append(f"{len(overdue)} past its forecast date")
    if blocked:
        parts.append(f"{len(blocked)} blocked")

    return _answer(
        MY_TASKS,
        "What am I responsible for?",
        f"{owner_name} has {', '.join(parts)}.",
        findings,
        (
            ["Start with anything blocked or already past its forecast date."]
            if (overdue or blocked)
            else []
        ),
        [task.task_id for task in tasks],
        evidence,
    )


def pending_change_decisions(portfolio: PortfolioData) -> CopilotAnswer:
    """Change requests still awaiting a recorded decision."""
    pending = [
        change
        for change in portfolio.change_requests
        if not is_change_request_decided(change.status)
    ]
    if not pending:
        return _answer(
            PENDING_CHANGE_DECISIONS,
            "What needs a decision?",
            "Every change request has a recorded decision.",
            [],
            [],
            [],
            [],
        )

    findings = [
        f"{change.change_request_id} on {change.project_id} is {change.status} "
        f"({change.priority} priority): {change.change_description}"
        for change in pending
    ]
    evidence = [
        _record(
            "change_request",
            change.change_request_id,
            {
                "change_description": change.change_description,
                "project_id": change.project_id,
                "requirement_id": change.requirement_id,
                "status": change.status,
                "priority": change.priority,
            },
        )
        for change in pending
    ]
    return _answer(
        PENDING_CHANGE_DECISIONS,
        "What needs a decision?",
        f"{len(pending)} change {'request is' if len(pending) == 1 else 'requests are'} "
        "awaiting a decision.",
        findings,
        ["Review the calculated impact of each before recording an outcome."],
        [change.change_request_id for change in pending],
        evidence,
    )


def _decision_evidence(decision) -> EvidenceRecordOut:
    fields = {
        "title": decision.title,
        "project_id": decision.project_id,
        "category": decision.category,
        "owner": decision.owner,
        "status": decision.status,
        "decision_date": str(decision.decision_date),
    }
    if decision.related_change_request_id:
        fields["change_request"] = decision.related_change_request_id
    if decision.related_milestone_id:
        fields["milestone"] = decision.related_milestone_id
    return _record("decision", decision.decision_id, fields)


def pending_decisions(decisions) -> CopilotAnswer:
    """Decisions still waiting on an outcome."""
    waiting = [d for d in decisions if d.status.strip().lower() == "proposed"]
    if not waiting:
        return _answer(
            PENDING_DECISIONS,
            "Which decisions are waiting for approval?",
            "Every recorded decision has an outcome.",
            [],
            [],
            [],
            [],
        )

    waiting.sort(key=lambda d: d.decision_date)
    findings = [
        f"{d.title} ({d.decision_id}) on {d.project_id}, proposed by {d.owner} on {d.decision_date}."
        for d in waiting
    ]
    return _answer(
        PENDING_DECISIONS,
        "Which decisions are waiting for approval?",
        f"{len(waiting)} {'decision is' if len(waiting) == 1 else 'decisions are'} waiting for an outcome.",
        findings,
        ["Review the reasoning and record an outcome so the context is not lost."],
        [d.decision_id for d in waiting],
        [_decision_evidence(d) for d in waiting],
    )


def project_decisions(decisions, project_id: str) -> CopilotAnswer:
    """Every decision recorded against one project."""
    scoped = [d for d in decisions if d.project_id == project_id]
    if not scoped:
        return _answer(
            PROJECT_DECISIONS,
            "What has been decided on this project?",
            f"No decisions are recorded against {project_id}.",
            [],
            ["Record decisions as they are made so the reasoning survives the meeting."],
            [],
            [],
        )

    scoped.sort(key=lambda d: d.decision_date, reverse=True)
    findings = [
        f"{d.title} ({d.decision_id}) is {d.status}, owned by {d.owner}"
        + (f". {d.rationale}" if d.rationale else ".")
        for d in scoped
    ]
    return _answer(
        PROJECT_DECISIONS,
        "What has been decided on this project?",
        f"{len(scoped)} {'decision is' if len(scoped) == 1 else 'decisions are'} recorded against {project_id}.",
        findings,
        [],
        [d.decision_id for d in scoped],
        [_decision_evidence(d) for d in scoped],
    )


def capabilities() -> CopilotAnswer:
    return _answer(
        APPLICATION_CAPABILITIES,
        "What can EPOS help with?",
        "I can answer questions about delivery using the records in this workspace.",
        [
            "Portfolio: which projects need attention, overall health, risks, milestones and capacity.",
            "A project: its status, what is driving its health, milestones, blocked work and team.",
            "Your work: what you are responsible for, what is overdue and what is blocked.",
            "Requirements: what still needs verification evidence.",
            "Change control: what a change request affects and what awaits a decision.",
            "Scenarios: what happens if a dependency slips.",
        ],
        ["Ask in your own words, or pick one of the suggestions."],
        [],
        [],
    )


def methodology() -> CopilotAnswer:
    """How the scores are produced.

    Read from the configured weights and thresholds rather than described from memory, so this
    answer cannot drift away from what the engines actually do.
    """
    weights = ", ".join(
        f"{labels.humanise(key)} {value:.0%}" for key, value in HEALTH_WEIGHTS.items()
    )
    confidence = ", ".join(
        f"{labels.humanise(key)} {value:.0%}" for key, value in CONFIDENCE_WEIGHTS.items()
    )
    return _answer(
        EPOS_METHODOLOGY,
        "How does EPOS calculate its scores?",
        (
            "Every score is calculated in Python from your records. The model never computes one, "
            "and never changes one."
        ),
        [
            f"Project health is a weighted blend of {weights}.",
            f"Reporting confidence is a weighted blend of {confidence}.",
            (
                f"A health score of {HEALTH_BANDS['Green']:.0f} or above is Green, "
                f"{HEALTH_BANDS['Amber']:.0f} to {HEALTH_BANDS['Green']:.0f} is Amber, "
                f"and below {HEALTH_BANDS['Amber']:.0f} is Red."
            ),
            (
                "Risk severity is probability multiplied by impact, both recorded on a one to five "
                "scale, so the same two numbers always give the same severity."
            ),
            (
                "Reporting confidence answers a different question from health: it says how much "
                "the health score deserves to be trusted, given how complete and how fresh the "
                "underlying records are."
            ),
            (
                "Change impact and scenario results are traced through recorded dependency and "
                "trace links, not estimated."
            ),
        ],
        [
            "Open any score card to see its factor breakdown and the records behind it.",
        ],
        [],
        [],
    )


def trust() -> CopilotAnswer:
    """What this workspace is, what it is not, and where its numbers come from."""
    return _answer(
        EPOS_TRUST,
        "How far can these numbers be trusted?",
        (
            "Every number here is calculated from the records in this workspace and can be traced "
            "back to them. What the numbers cannot do is know about work that was never recorded."
        ),
        [
            (
                "Scores are deterministic. The same records and the same date always produce the "
                "same score, and the calculation is in version-controlled Python, not in a model."
            ),
            (
                "The AI layer only explains evidence that was already calculated. It is given a "
                "selected evidence package, never the whole workspace, and every identifier it "
                "returns is checked against what it was actually sent."
            ),
            (
                "Anything the AI drafts is marked as requiring human review. Lookups answered "
                "straight from records are not, because nothing was drafted."
            ),
            (
                "Reporting confidence is the honest limit: where records are incomplete, stale or "
                "unowned, confidence falls and the health score should carry less weight."
            ),
            (
                "The data in this workspace is synthetic and exists to demonstrate the method. "
                "This is a working prototype, not a system of record."
            ),
        ],
        [
            "Check reporting confidence before acting on a health score.",
            "Follow the record identifiers on any finding to see the evidence yourself.",
        ],
        [],
        [],
    )
