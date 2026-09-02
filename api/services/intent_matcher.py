"""Recognise what a question is about and what it asks for.

Ask EPOS previously matched whole phrases, so a question only worked if it was worded close to the
way a rule happened to be written. This module replaces that with two smaller judgements that
compose: what **subject** the question concerns, and what **operation** it wants performed on that
subject. "Which initiatives are struggling?" and "what's on fire?" reach the same place because
both resolve to (project, problems), without either phrasing being listed anywhere.

Three properties are deliberate:

- **Nothing here decides an answer.** The matcher returns an intent name. Every figure still comes
  from the deterministic engines or from records.
- **Unmatched is a valid outcome.** A question about the weather scores nothing and is reported as
  out of scope rather than forced into the nearest intent.
- **Mutation and secret-seeking text is refused before scoring.** Ask EPOS is read-only, and that
  is enforced here rather than left as a consequence of no rule happening to match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Final

from api.services import copilot_answers as answers
from src.ai_assistant import (
    QUESTION_CHANGE_REQUEST_IMPACT,
    QUESTION_MILESTONES_AT_RISK,
    QUESTION_PROJECTS_NEEDING_ATTENTION,
    QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION,
    QUESTION_RISKS_WITHOUT_OWNER,
    QUESTION_WEEKLY_EXECUTIVE_UPDATE,
    QUESTION_WHY_PROJECT_BAND,
)

# --------------------------------------------------------------------------- subjects
PROJECT = "project"
RISK = "risk"
MILESTONE = "milestone"
DEPENDENCY = "dependency"
REQUIREMENT = "requirement"
CHANGE = "change"
DECISION = "decision"
WORK = "work"
PEOPLE = "people"
PRODUCT = "product"

# --------------------------------------------------------------------------- operations
LIST = "list"
PROBLEMS = "problems"
EXPLAIN = "explain"
REPORT = "report"
IMPACT = "impact"
UNOWNED = "unowned"
UNVERIFIED = "unverified"
BLOCKED = "blocked"
MINE = "mine"
PENDING = "pending"
CAPABILITY = "capability"
METHODOLOGY = "methodology"
TRUST = "trust"
STATUS = "status"
KNOWLEDGE = "knowledge"

EPOS_KNOWLEDGE = "epos_knowledge"
SCENARIO_ANALYSIS = "scenario_analysis"


@dataclass(frozen=True)
class Term:
    """One recognisable phrase and what it is worth.

    Longer phrases score higher because they are less likely to appear by accident, so "at risk"
    outweighs a bare "risk" without either weight being tuned by hand. Matching is on whole words:
    without that, "translate" contains "late" and "working" contains "work", and both would drag a
    question into the wrong intent.
    """

    text: str
    weight: int
    pattern: re.Pattern[str]

    @staticmethod
    def of(text: str, bonus: int = 0) -> Term:
        return Term(
            text,
            len(text.split()) + bonus,
            re.compile(rf"(?<!\w){re.escape(text)}(?!\w)"),
        )


def _terms(*phrases: str) -> tuple[Term, ...]:
    return tuple(Term.of(phrase) for phrase in phrases)


@dataclass(frozen=True)
class Category:
    """A subject or an operation, with the wording that identifies it.

    ``precedence`` settles ties. A specific operation such as "blocked" beats a generic one such as
    "list" when both appear, because "show blocked tasks" is a question about blocked work rather
    than a request for a list.
    """

    name: str
    terms: tuple[Term, ...]
    # Applied when this category wins and nothing else was found.
    default_partner: str | None = None
    precedence: int = 0
    bonus: int = 0


_SUBJECTS: Final[tuple[Category, ...]] = (
    Category(
        PROJECT,
        _terms(
            "project",
            "projects",
            "portfolio",
            "initiative",
            "initiatives",
            "programme",
            "programmes",
            "program",
            "programs",
            "workstream",
            "workstreams",
            "engagement",
            "engagements",
            "effort",
            "efforts",
            "delivery",
        ),
        default_partner=LIST,
    ),
    Category(
        RISK,
        _terms("risk", "risks", "threat", "threats", "exposure"),
        default_partner=UNOWNED,
        # "at risk" appears in questions about milestones, projects and work, so a bare mention of
        # risk must never win a tie against a subject the user named outright.
        precedence=-1,
    ),
    Category(
        MILESTONE,
        _terms(
            "milestone",
            "milestones",
            "deadline",
            "deadlines",
            "gate",
            "gates",
            "date",
            "dates",
        ),
        default_partner=PROBLEMS,
    ),
    Category(
        DEPENDENCY,
        _terms("dependency", "dependencies"),
        default_partner=IMPACT,
    ),
    Category(
        REQUIREMENT,
        _terms(
            "requirement",
            "requirements",
            "verification",
            "verified",
            "traceability",
            "trace",
            "test coverage",
            "test case",
            "test cases",
        ),
        default_partner=UNVERIFIED,
    ),
    Category(
        CHANGE,
        _terms(
            "change request",
            "change requests",
            "change control",
            # Singular: "what needs a decision?" asks which change requests await a call, while
            # the plural "which decisions..." asks about the decision log. Folding turns the
            # former into "pending decision", so it is recognised here rather than as a decision.
            "pending decision",
        ),
        default_partner=IMPACT,
    ),
    Category(
        DECISION,
        _terms("decision", "decisions", "decision log", "sign off", "sign-off"),
        default_partner=PENDING,
    ),
    Category(
        WORK,
        _terms("task", "tasks", "work", "workload", "activity", "activities", "item", "items"),
        default_partner=LIST,
    ),
    Category(
        PEOPLE,
        _terms(
            "capacity",
            "resource",
            "resources",
            "utilisation",
            "utilization",
            "allocation",
            "allocated",
            "headcount",
            "team",
            "people",
            "staff",
            "overloaded",
            "stretched",
            "stretched too thin",
            "spread thin",
        ),
        default_partner=LIST,
    ),
    Category(
        PRODUCT,
        _terms("epos", "this app", "this tool", "this system", "this dashboard", "the ai"),
        default_partner=CAPABILITY,
    ),
)

_OPERATIONS: Final[tuple[Category, ...]] = (
    Category(
        LIST,
        _terms(
            "list",
            "inventory",
            "overview",
            "exist",
            "exists",
            "everything",
            "all project",
            "all projects",
            "every project",
            "working on",
            "do we have",
            "are there",
        ),
        default_partner=PROJECT,
    ),
    Category(
        PROBLEMS,
        _terms(
            "at risk",
            "attention",
            "concerning",
            "concerned",
            "concern",
            "worry",
            "worried",
            "trouble",
            "troubled",
            "broken",
            "on fire",
            "suffering",
            "struggling",
            "focus on",
            "focus",
            "priority",
            "priorities",
            "escalate",
            "escalation",
            "worst",
            "late",
            "slip",
            "slipping",
            "delayed",
            "going wrong",
            "gone wrong",
            "bad",
            "important",
            "highlight",
            "highlights",
            "headline",
            "act on",
            "should i know",
            "need to know",
            "miss",
            "off track",
            "track",
            "wrong",
            "missing our dates",
            "hit our dates",
            "danger",
        ),
        default_partner=PROJECT,
        precedence=1,
    ),
    Category(
        EXPLAIN,
        _terms(
            "why",
            "explain",
            "reason",
            "driving",
            "drives",
            "cause",
            "break down",
            "breakdown",
            "what factors",
            "which factor",
            "contributes",
            "pulling down",
            "how come",
        ),
        default_partner=PROJECT,
        precedence=1,
    ),
    Category(
        REPORT,
        _terms(
            "draft",
            "write up",
            "write the report",
            "write the update",
            "prepare",
            "summary",
            "summarise",
            "summarize",
            "report",
            "weekly",
            "executive",
            "steering",
            "steering committee",
            "board update",
            "put together",
        ),
        default_partner=PROJECT,
        precedence=1,
    ),
    Category(
        IMPACT,
        _terms(
            "impact",
            "affect",
            "affects",
            "affected",
            "downstream",
            "ripple",
            "knock on",
            "what breaks",
            "happens if",
            "if we approve",
            "if we accept",
            "touch",
            "touches",
        ),
        default_partner=CHANGE,
        precedence=2,
    ),
    Category(
        UNOWNED,
        _terms(
            "no owner",
            "without an owner",
            "without owner",
            "unowned",
            "unassigned",
            "nobody",
            "no one",
            "not assigned",
            "missing owner",
            "needs an owner",
            "need an owner",
            "owner assigning",
            "owner",
            "owners",
        ),
        default_partner=RISK,
        precedence=2,
    ),
    Category(
        UNVERIFIED,
        _terms(
            "unverified",
            "without verification",
            "lack verification",
            "no verification",
            "no test coverage",
            "not traced",
            "verification gap",
            "verification gaps",
            "trace gap",
            "trace gaps",
            "coverage",
            "lack",
            "lacks",
        ),
        default_partner=REQUIREMENT,
        precedence=2,
    ),
    Category(
        BLOCKED,
        _terms(
            "blocked",
            "blocker",
            "blockers",
            "stuck",
            "impediment",
            "impediments",
            "held up",
            "waiting on someone",
        ),
        default_partner=WORK,
        precedence=3,
        bonus=2,
    ),
    Category(
        MINE,
        _terms(
            "my task",
            "my tasks",
            "my work",
            "my open",
            "my item",
            "my items",
            "my plate",
            "my list",
            "assigned to me",
            "due from me",
            "responsible for",
            "i responsible",
            "i need to do",
            "waiting on me",
        ),
        default_partner=WORK,
        precedence=2,
    ),
    Category(
        PENDING,
        _terms(
            "pending",
            "awaiting",
            "waiting",
            "outstanding",
            "needs approval",
            "need approval",
            "needs a decision",
            "need a decision",
            "still open",
            "to decide",
            "require sign off",
            "requires sign off",
        ),
        default_partner=DECISION,
        precedence=3,
    ),
    Category(
        CAPABILITY,
        _terms(
            "what can you",
            "what can epos",
            "what can this",
            "help me with",
            "help with",
            "capability",
            "capabilities",
            "how do i use",
            "what does this do",
            "what does this app",
            "what is epos",
            "where do i start",
            "what questions",
            "what should i ask",
            "new here",
            "what this tool is for",
            "help",
        ),
        default_partner=PRODUCT,
        precedence=4,
        bonus=2,
    ),
    Category(
        METHODOLOGY,
        _terms(
            "how does epos calculate",
            "how do you calculate",
            "how do you compute",
            "how do you work out",
            "methodology",
            "formula",
            "weights",
            "weighting",
            "calculated",
            "calculate",
            "computed",
            "scoring",
            "goes into",
            "made up of",
            "factors make up",
            "determined",
        ),
        default_partner=PRODUCT,
        precedence=4,
        bonus=2,
    ),
    Category(
        TRUST,
        _terms(
            "trust",
            "believe",
            "trustworthy",
            "accurate",
            "accuracy",
            "reliable",
            "reliability",
            "assumption",
            "assumptions",
            "limitation",
            "limitations",
            "weakness",
            "weaknesses",
            "production ready",
            "make up",
            "makes up",
            "made up numbers",
            "hallucinate",
            "hallucination",
            "is the data real",
            "how do i know",
        ),
        default_partner=PRODUCT,
        precedence=4,
        bonus=2,
    ),
    Category(
        STATUS,
        _terms(
            "status of",
            "status",
            "update on",
            "doing",
            "going on",
            "how healthy",
            "progress",
        ),
        default_partner=PROJECT,
    ),
    Category(
        KNOWLEDGE,
        _terms(
            "architecture",
            "roadmap",
            "technology",
            "tech stack",
            "implementation",
            "implemented",
            "testing approach",
            "test strategy",
            "test suite",
            "test suites",
            "how many tests",
            "tests exist",
            "tests passed",
            "test count",
            "security model",
            "future scope",
            "future plan",
        ),
        default_partner=PRODUCT,
        precedence=4,
        bonus=2,
    ),
)

# Which intent each (subject, operation) pair resolves to. Pairs that are not listed fall back to
# the subject's own default, which is why an unusual combination still lands somewhere sensible.
_PAIRS: Final[dict[tuple[str, str], str]] = {
    (PROJECT, LIST): answers.LIST_PROJECTS,
    (PROJECT, PROBLEMS): QUESTION_PROJECTS_NEEDING_ATTENTION,
    (PROJECT, EXPLAIN): QUESTION_WHY_PROJECT_BAND,
    (PROJECT, STATUS): QUESTION_WHY_PROJECT_BAND,
    (PROJECT, REPORT): QUESTION_WEEKLY_EXECUTIVE_UPDATE,
    (PROJECT, BLOCKED): answers.BLOCKED_WORK,
    (PROJECT, MINE): answers.MY_TASKS,
    (PROJECT, UNOWNED): QUESTION_RISKS_WITHOUT_OWNER,
    (PROJECT, UNVERIFIED): QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION,
    (PROJECT, IMPACT): QUESTION_CHANGE_REQUEST_IMPACT,
    (PROJECT, PENDING): answers.PENDING_CHANGE_DECISIONS,
    (PROJECT, METHODOLOGY): answers.EPOS_METHODOLOGY,
    (PROJECT, TRUST): answers.EPOS_TRUST,
    (PROJECT, CAPABILITY): answers.APPLICATION_CAPABILITIES,
    (RISK, LIST): QUESTION_RISKS_WITHOUT_OWNER,
    (RISK, UNOWNED): QUESTION_RISKS_WITHOUT_OWNER,
    (RISK, PROBLEMS): QUESTION_PROJECTS_NEEDING_ATTENTION,
    (RISK, EXPLAIN): QUESTION_WHY_PROJECT_BAND,
    (RISK, REPORT): QUESTION_WEEKLY_EXECUTIVE_UPDATE,
    (MILESTONE, LIST): QUESTION_MILESTONES_AT_RISK,
    (MILESTONE, PROBLEMS): QUESTION_MILESTONES_AT_RISK,
    (MILESTONE, EXPLAIN): QUESTION_MILESTONES_AT_RISK,
    (MILESTONE, STATUS): QUESTION_MILESTONES_AT_RISK,
    (MILESTONE, REPORT): QUESTION_MILESTONES_AT_RISK,
    (DEPENDENCY, IMPACT): SCENARIO_ANALYSIS,
    (DEPENDENCY, PROBLEMS): SCENARIO_ANALYSIS,
    (WORK, STATUS): answers.BLOCKED_WORK,
    (PEOPLE, STATUS): answers.PORTFOLIO_CAPACITY,
    (RISK, STATUS): QUESTION_PROJECTS_NEEDING_ATTENTION,
    (DECISION, STATUS): answers.PENDING_DECISIONS,
    (CHANGE, STATUS): answers.PENDING_CHANGE_DECISIONS,
    (REQUIREMENT, STATUS): QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION,
    (REQUIREMENT, LIST): QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION,
    (REQUIREMENT, UNVERIFIED): QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION,
    (REQUIREMENT, PROBLEMS): QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION,
    (REQUIREMENT, IMPACT): QUESTION_CHANGE_REQUEST_IMPACT,
    (CHANGE, IMPACT): QUESTION_CHANGE_REQUEST_IMPACT,
    (CHANGE, LIST): answers.PENDING_CHANGE_DECISIONS,
    (CHANGE, PENDING): answers.PENDING_CHANGE_DECISIONS,
    (CHANGE, PROBLEMS): answers.PENDING_CHANGE_DECISIONS,
    (DECISION, PENDING): answers.PENDING_DECISIONS,
    (DECISION, LIST): answers.PENDING_DECISIONS,
    (DECISION, MINE): answers.PENDING_DECISIONS,
    (DECISION, IMPACT): answers.PROJECT_DECISIONS,
    (WORK, BLOCKED): answers.BLOCKED_WORK,
    (WORK, MINE): answers.MY_TASKS,
    (WORK, LIST): answers.MY_TASKS,
    (WORK, PROBLEMS): answers.BLOCKED_WORK,
    (WORK, PENDING): answers.MY_TASKS,
    (PEOPLE, LIST): answers.PORTFOLIO_CAPACITY,
    (PEOPLE, PROBLEMS): answers.PORTFOLIO_CAPACITY,
    (PEOPLE, EXPLAIN): answers.PORTFOLIO_CAPACITY,
    (PEOPLE, MINE): answers.MY_TASKS,
    (PRODUCT, CAPABILITY): answers.APPLICATION_CAPABILITIES,
    (PRODUCT, METHODOLOGY): answers.EPOS_METHODOLOGY,
    (PRODUCT, TRUST): answers.EPOS_TRUST,
    (PRODUCT, KNOWLEDGE): EPOS_KNOWLEDGE,
    (PRODUCT, LIST): answers.APPLICATION_CAPABILITIES,
    (PRODUCT, EXPLAIN): answers.EPOS_METHODOLOGY,
}

# The subject is only ever the product itself when the question is about the product.
_PRODUCT_OPERATIONS: Final[frozenset[str]] = frozenset({CAPABILITY, METHODOLOGY, TRUST, KNOWLEDGE})

# Ask EPOS reads; it never writes and never discloses configuration. Text that asks for either is
# refused here, before any scoring, so a mutation verb can never ride in on an otherwise valid
# sentence such as "delete all projects".
_REFUSED: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern)
    for pattern in (
        # "drop" only means destruction next to a database noun. A health score can drop too.
        r"\b(delete|truncate|erase|purge|wipe)\b",
        r"\bdrop\b.*\b(table|database|schema)\b",
        r"\bdrop\s+all\b",
        r"\b(insert into|create table|grant|revoke)\b",
        # A mutation verb only counts when it is aimed at a record. Without this, "weekly update"
        # and "give me an update on P-002" would be refused as attempts to write.
        r"\b(update|set|change|modify|edit|overwrite|remove)\s+(the\s+|all\s+|my\s+)?"
        r"(p-\d|cr-\d|project|risk|task|milestone|requirement|decision|score|health|band|status|data|record|user|role)",
        r"\bselect\b.*\bfrom\b",
        r"\b(api[ _-]?key|access[ _-]?token|password|passwords|credential|credentials|secret|secrets)\b",
        # Matches both ".env" and the cleaned "env", so the guard holds wherever it is applied.
        r"(?<!\w)\.?env\b",
        r"\bignore (all )?(previous|prior|above)\b",
        r"\b(system prompt|your instructions|your prompt)\b",
        r"\breveal\b",
    )
)

_PUNCTUATION: Final[re.Pattern[str]] = re.compile(r"[^\w\s-]")
_TOKEN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z-]*")

_CONTRACTIONS: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(rf"\b(?:{pattern})\b"), replacement)
    for pattern, replacement in (
        (r"what's|whats", "what is"),
        (r"who's|whos", "who is"),
        (r"how's|hows", "how is"),
        (r"where's|wheres", "where is"),
        (r"it's|its", "it is"),
        (r"we're|were", "we are"),
        (r"i'm|im", "i am"),
        (r"don't|dont", "do not"),
        (r"isn't|isnt", "is not"),
        (r"aren't|arent", "are not"),
        (r"can't|cant", "can not"),
        (r"let's|lets", "let us"),
        (r"i've|ive", "i have"),
        (r"you're|youre", "you are"),
        (r"pls|plz", "please"),
        (r"u", "you"),
        (r"r", "are"),
        (r"wat|wht", "what"),
        (r"wch", "which"),
        (r"wrk", "work"),
        (r"hw", "how"),
        (r"abt", "about"),
        (r"thx", "thanks"),
    )
)

# Typo correction only ever maps onto words the matcher already knows, so it can introduce
# vocabulary but never invent meaning.
_VOCABULARY: Final[frozenset[str]] = frozenset(
    word
    for category in (*_SUBJECTS, *_OPERATIONS)
    for term in category.terms
    for word in term.text.split()
    if len(word) >= 4
)

# The words the matcher reads as delivery vocabulary. A project name that happens to contain one
# ("requirements", "test", "data") must not be identified by that word alone.
DOMAIN_VOCABULARY: Final[frozenset[str]] = _VOCABULARY

_TYPO_CUTOFF: Final[float] = 0.72
_TYPO_MIN_LENGTH: Final[int] = 4
_TYPO_MAX_LENGTH_DELTA: Final[int] = 2


def _edit_distance(left: str, right: str) -> int:
    """Return the number of single-character edits separating two words."""
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def clean(text: str) -> str:
    """Lowercase, expand everyday contractions and drop punctuation that carries no meaning."""
    lowered = " ".join(text.lower().split())
    for pattern, replacement in _CONTRACTIONS:
        lowered = pattern.sub(replacement, lowered)
    return " ".join(_PUNCTUATION.sub(" ", lowered).split())


def _nearest(token: str) -> str:
    """The vocabulary word a mistyped token most likely meant, or the token unchanged.

    Three guards keep this from inventing meaning: the first letter must match, the lengths must be
    close, and the similarity must be high. Together they correct "projets" to "projects" while
    leaving "world" alone rather than pulling it towards "workload".
    """
    if len(token) < _TYPO_MIN_LENGTH or token in _VOCABULARY:
        return token

    best_word, best_ratio = token, _TYPO_CUTOFF
    for candidate in _VOCABULARY:
        if candidate[0] != token[0] or abs(len(candidate) - len(token)) > _TYPO_MAX_LENGTH_DELTA:
            continue
        max_edits = 1 if len(token) <= 6 else 2
        if _edit_distance(token, candidate) > max_edits:
            continue
        ratio = SequenceMatcher(None, token, candidate).ratio()
        if ratio > best_ratio:
            best_word, best_ratio = candidate, ratio
    return best_word


def correct_typos(text: str) -> str:
    """Map mistyped words onto the vocabulary the matcher understands."""
    return _TOKEN.sub(lambda match: _nearest(match.group(0)), text)


def is_refused(text: str) -> bool:
    """True when the text asks EPOS to change data or disclose configuration."""
    return any(pattern.search(text) for pattern in _REFUSED)


def _score(category: Category, text: str) -> int:
    """Total weight of the category's terms present in the text.

    The category bonus is applied per matched term rather than once, so a category earns its
    advantage from how much of it the question actually contains.
    """
    return sum(term.weight + category.bonus for term in category.terms if term.pattern.search(text))


def _best(categories: tuple[Category, ...], text: str) -> tuple[Category | None, int]:
    """The highest scoring category, with ties settled by precedence then declaration order."""
    ranked = sorted(
        ((category, _score(category, text)) for category in categories),
        key=lambda item: (-item[1], -item[0].precedence),
    )
    top, score = ranked[0]
    return (top, score) if score > 0 else (None, 0)


def _default_partner(categories: tuple[Category, ...], name: str) -> str | None:
    """The partner a named category falls back to.

    Looked up by name rather than taken from the matched object, because a category can be
    rewritten after matching and the rewritten one must supply the default.
    """
    found = next((category for category in categories if category.name == name), None)
    return found.default_partner if found else None


@dataclass(frozen=True)
class Match:
    """What the question was understood to be about.

    ``intent`` is None when nothing was recognised. ``subject`` and ``operation`` are kept even
    then, because a question that named a subject but no operation can still be answered with a
    useful suggestion rather than a blank refusal.
    """

    intent: str | None
    subject: str | None
    operation: str | None
    confidence: int


def match(text: str, names_a_project: bool = False) -> Match:
    """Resolve prepared text to an intent, or to nothing when it is out of scope.

    ``names_a_project`` tells the matcher that the question identified a specific project, which
    supplies the subject for questions such as "how is P-002 doing?" that name no subject noun.
    """
    if is_refused(text):
        return Match(None, None, None, 0)

    subject, subject_score = _best(_SUBJECTS, text)
    operation, operation_score = _best(_OPERATIONS, text)

    if subject is None and operation is None and not names_a_project:
        return Match(None, None, None, 0)

    subject_name = subject.name if subject else None
    operation_name = operation.name if operation else None

    # A question about the product is only ever recognised through a product operation, so naming
    # EPOS while asking about projects does not turn it into a question about the tool. Naming a
    # specific project does the reverse: "break down the health calculation for P-002" asks about
    # that project, not about how scoring works in general.
    if operation_name in _PRODUCT_OPERATIONS:
        if names_a_project:
            operation_name = EXPLAIN
        else:
            subject_name = PRODUCT
    elif subject_name == PRODUCT:
        subject_name = None
        subject_score = 0

    if subject_name is None and operation_name is not None:
        subject_name = _default_partner(_OPERATIONS, operation_name)
    if subject_name is None and names_a_project:
        subject_name = PROJECT
    if operation_name is None and subject_name is not None:
        operation_name = _default_partner(_SUBJECTS, subject_name)
    if operation_name is None and names_a_project:
        operation_name = EXPLAIN

    if subject_name is None or operation_name is None:
        return Match(None, subject_name, operation_name, 0)

    intent = _PAIRS.get((subject_name, operation_name))
    if intent is None:
        fallback = next((item for item in _SUBJECTS if item.name == subject_name), None)
        default_operation = fallback.default_partner if fallback else None
        intent = _PAIRS.get((subject_name, default_operation or LIST))

    return Match(intent, subject_name, operation_name, subject_score + operation_score)


def prepare(question: str) -> str:
    """Clean and typo-correct a raw question, ready for synonym folding and matching."""
    return correct_typos(clean(question))


def subject_names() -> tuple[str, ...]:
    """Every subject the matcher recognises, for explaining scope to a user."""
    return tuple(category.name for category in _SUBJECTS)
