"""How a question narrows the project list, resolved only onto recorded project attributes.

Enterprise assistants translate "only tech projects" into a structured query and show that query
back (a search filter, a query plan, or generated JQL) so the reader can check it. This module is
the deterministic half: it recognises constraints on the project list, maps each onto values that
are actually recorded, and reports anything it could not map instead of widening the answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal, get_args

from src.data_loader import PortfolioData
from src.health_engine import calculate_project_health
from src.schemas import Project
from src.scoring_rules import CRITICALITY_LEVELS

FieldName = Literal["domain", "phase", "priority", "manager", "health_band", "name"]
SortOrder = Literal["health_worst_first", "health_best_first", "priority"]

FIELD_LABELS: Final[dict[str, str]] = {
    "domain": "Domain",
    "phase": "Phase",
    "priority": "Business priority",
    "manager": "Project manager",
    "health_band": "Health band",
    "name": "Name contains",
}
SORT_LABELS: Final[dict[str, str]] = {
    "health_worst_first": "lowest health first",
    "health_best_first": "highest health first",
    "priority": "business priority, most critical first",
}
HEALTH_BAND_NAMES: Final[tuple[str, ...]] = ("Green", "Amber", "Red")
MAX_LIMIT: Final[int] = 50
_MAX_PHRASE_LENGTH: Final[int] = 60

# Everyday umbrella words mapped onto tokens of stored domain names. Only domains that actually
# contain one of these tokens can be selected, and the answer always says it was an interpretation.
_UMBRELLA_TERMS: Final[dict[str, frozenset[str]]] = {
    **dict.fromkeys(
        ("tech", "technology", "technologies", "technical", "technological", "ict"),
        frozenset({"software", "digital", "it", "systems", "data", "cyber", "cloud"}),
    ),
    **dict.fromkeys(
        ("environmental", "esg", "climate", "sustainable", "decarbonisation", "decarbonization"),
        frozenset({"sustainability"}),
    ),
    **dict.fromkeys(("regulatory", "legal"), frozenset({"compliance"})),
    **dict.fromkeys(("production", "factory", "fab", "plant"), frozenset({"manufacturing"})),
    **dict.fromkeys(("testing", "verification"), frozenset({"test"})),
}

# Words that shape a request without constraining it.
_FILLER: Final[frozenset[str]] = frozenset(
    [
        "a",
        "all",
        "an",
        "and",
        "any",
        "are",
        "as",
        "available",
        "be",
        "can",
        "current",
        "currently",
        "different",
        "display",
        "do",
        "does",
        "domain",
        "domains",
        "down",
        "enumerate",
        "every",
        "existing",
        "few",
        "find",
        "for",
        "from",
        "get",
        "give",
        "have",
        "how",
        "i",
        "in",
        "is",
        "just",
        "kind",
        "kinds",
        "list",
        "many",
        "me",
        "more",
        "most",
        "much",
        "my",
        "name",
        "of",
        "on",
        "only",
        "open",
        "ongoing",
        "or",
        "other",
        "our",
        "please",
        "portfolio",
        "project",
        "projects",
        "recorded",
        "running",
        "show",
        "some",
        "sort",
        "sorts",
        "that",
        "the",
        "their",
        "them",
        "there",
        "these",
        "they",
        "this",
        "those",
        "total",
        "type",
        "types",
        "various",
        "we",
        "what",
        "which",
        "with",
        "you",
        "your",
        "area",
        "areas",
        "sector",
        "sectors",
        "field",
        "fields",
        "category",
        "categories",
        "team",
        "teams",
        "active",
        "whole",
        "entire",
    ]
)
_FILLER_TYPO_MIN_LENGTH: Final[int] = 5

# Vocabulary the intent matcher reads. A word such as "late" or "blocked" describes the analysis
# wanted, not a filter, so it is left for routing rather than reported as unrecognised.
_ANALYSIS_WORDS: Final[frozenset[str]] = frozenset(
    [
        "late",
        "delayed",
        "slipping",
        "behind",
        "risky",
        "struggling",
        "troubled",
        "failing",
        "overdue",
        "blocked",
        "stuck",
        "attention",
        "concerning",
        "worrying",
        "worst",
        "best",
        "healthiest",
        "weakest",
        "strongest",
        "riskiest",
        "status",
        "health",
        "healthy",
        "unhealthy",
        "important",
        "urgent",
        "priorities",
    ]
)

# A record attribute such as priority describes a project only when it is attached to the word
# "projects"; "high priority risks" is about the risks' own priority and is left to routing.
_BEFORE_PROJECTS: Final[str] = r"(?=\s+(?:[a-z][a-z'-]*\s+){0,2}projects?\b)"
_PRIORITY_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"\b(critical|high|medium|low)(?:[- ]|\s+business\s+)priority{_BEFORE_PROJECTS}"
    r"|\bprojects?\s+(?:with|of|at|having|that\s+are|which\s+are|are)\s+(?:a\s+)?"
    r"(critical|high|medium|low)\s+(?:business\s+)?priority\b"
    r"|\bprojects?\s+(?:with|where)\s+(?:business\s+)?priority\s+(?:is\s+|of\s+)?"
    r"(critical|high|medium|low)\b"
    rf"|\b(?:business|mission)[- ](critical){_BEFORE_PROJECTS}"
)
_BARE_CRITICAL_PATTERN: Final[re.Pattern[str]] = re.compile(rf"\bcritical{_BEFORE_PROJECTS}")
_BAND_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(green|amber|yellow|red)(?:\s+(?:or|and)\s+(green|amber|yellow|red))?"
    rf"(?:\s+(?:rated|health|band))?{_BEFORE_PROJECTS}"
    r"|(?<=projects\s)(?:that\s+are\s+|which\s+are\s+|are\s+|rated\s+|in\s+the\s+)"
    r"(green|amber|yellow|red)(?:\s+(?:or|and)\s+(green|amber|yellow|red))?\b"
    r"|(?<=project\s)(?:that\s+is\s+|is\s+|rated\s+|in\s+the\s+)(green|amber|yellow|red)\b"
    r"|(?<=projects\s)(?:with|in)\s+(?:a\s+|the\s+)?(green|amber|red)\s+(?:health|band|status)\b"
)
_HEALTHY_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"\b(unhealthy|not\s+healthy|healthy){_BEFORE_PROJECTS}"
    r"|(?<=projects\s)(?:that\s+are\s+|which\s+are\s+|are\s+)(unhealthy|not\s+healthy|healthy)\b"
)
_ABOUT_PROJECTS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bprojects\b|\bdomains?\b|\bportfolio\b"
)
_OTHER_SUBJECTS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:risks?|tasks?|milestones?|actions?|requirements?|dependenc(?:y|ies)|change requests?"
    r"|decisions?|test cases?|issues?|blockers?|blocked|work|deliverables?|gates?|assumptions?"
    r"|resources?|people|capacity|workload)\b"
)
_PROJECT_NOUN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:(?:in|for|across|of|from|within|on)\s+)?(?:(?:the|our|all)\s+)?projects?\b"
)
_LIMIT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:top|first|bottom)\s+(\d{1,2})\b|\b(\d{1,2})\s+(?=(?:worst|best|riskiest|healthiest|"
    r"weakest|strongest|least\s+healthy|most\s+critical)\b)"
)
_SORT_PATTERNS: Final[tuple[tuple[re.Pattern[str], SortOrder], ...]] = (
    (
        re.compile(
            r"\b(worst|riskiest|weakest|least\s+healthy|lowest\s+health|unhealthiest)\b"
            r"|\b(?:sorted|ordered|ranked)\s+by\s+(?:lowest\s+)?health\b"
        ),
        "health_worst_first",
    ),
    (
        re.compile(r"\b(best|healthiest|strongest|highest\s+health)\b"),
        "health_best_first",
    ),
    (
        re.compile(r"\b(most\s+critical|(?:sorted|ordered|ranked)\s+by\s+priority)\b"),
        "priority",
    ),
)
_EXCLUSION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:except(?:\s+for)?|excluding|exclude|other\s+than|apart\s+from|but\s+not|not\s+in"
    r"|outside(?:\s+of)?|leaving\s+out|without(?=\s+(?:the\s+)?[a-z]+\s+(?:domain|projects?)))"
    r"\s+(?:the\s+)?(?:projects?\s+(?:in|from|of)\s+(?:the\s+)?)?"
    r"(?P<phrase>[a-z][a-z' -]*?)(?=\s*(?:$|[,;?.!]|\s(?:and\s+(?:also|show|list)|please)\b))"
)
_MANAGER_CUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<negated>not\s+)?(?:managed|led|run|owned|headed|handled)\s+by\s+"
    r"(?P<name>[a-z][a-z'-]*(?:\s+[a-z][a-z'-]*)?)"
)
_POSSESSIVE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<name>[a-z][a-z-]+)'s\s+projects?\b"
)
_MODIFIER_BEFORE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?P<phrase>(?:[a-z][a-z'-]*\s+){1,4}?)projects\b"
)
_MODIFIER_AFTER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bprojects?\s+(?:in|from|within|under|for|across|about|involving|mentioning|named|called"
    r"|related\s+to|belonging\s+to|of)\s+(?:the\s+)?"
    r"(?P<phrase>[a-z][a-z' -]*?)(?=\s*(?:$|[,;?.!]|\s(?:and|with|that|which|managed|led|run|"
    r"owned|except|excluding|sorted|ordered|please|phase|stage)\b))"
)
_DOMAIN_CUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:in|within|from)\s+(?:the\s+)?(?P<phrase>[a-z][a-z' -]*?)\s+(?:domain|area|sector)\b"
    r"|\bdomain\s+(?:of\s+|is\s+|=\s*)?(?P<after>[a-z][a-z' -]*?)(?=\s*(?:$|[,;?.!]|\s(?:and|with|"
    r"only|please)\b))"
)
_DOMAIN_WORD_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(?:domain|domains|sector|area)\b")
_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
_BAND_ALIASES: Final[dict[str, str]] = {
    "green": "Green",
    "amber": "Amber",
    "yellow": "Amber",
    "red": "Red",
}


@dataclass(frozen=True)
class Term:
    """One constraint on the project list, expressed only in recorded values."""

    field: FieldName
    values: tuple[str, ...]
    phrase: str
    excluded: bool = False
    interpreted: bool = False


@dataclass(frozen=True)
class ProjectQuery:
    """The validated constraints a question places on the project list."""

    terms: tuple[Term, ...] = ()
    unmatched: tuple[str, ...] = ()
    sort: SortOrder | None = None
    limit: int | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.terms or self.unmatched or self.sort or self.limit)

    @property
    def narrows(self) -> bool:
        """True when the question restricts which projects count, not only their order."""
        return bool(self.terms or self.unmatched or self.limit)

    @property
    def needs_interpretation(self) -> bool:
        return bool(self.unmatched) or any(term.interpreted for term in self.terms)

    def to_json(self) -> str:
        return json.dumps(
            {
                "terms": [
                    {
                        "field": term.field,
                        "values": list(term.values),
                        "phrase": term.phrase,
                        "excluded": term.excluded,
                        "interpreted": term.interpreted,
                    }
                    for term in self.terms
                ],
                "unmatched": list(self.unmatched),
                "sort": self.sort,
                "limit": self.limit,
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str | None, portfolio: PortfolioData) -> ProjectQuery:
        """Restore a saved query, keeping only values still recorded in the portfolio."""
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        vocabulary = Vocabulary.of(portfolio)
        terms = []
        for item in data.get("terms") or []:
            if not isinstance(item, dict) or item.get("field") not in get_args(FieldName):
                continue
            values = vocabulary.valid(item["field"], item.get("values") or [])
            if values:
                terms.append(
                    Term(
                        field=item["field"],
                        values=values,
                        phrase=str(item.get("phrase") or "")[:_MAX_PHRASE_LENGTH],
                        excluded=bool(item.get("excluded")),
                        interpreted=bool(item.get("interpreted")),
                    )
                )
        unmatched = tuple(
            str(value)[:_MAX_PHRASE_LENGTH]
            for value in data.get("unmatched") or []
            if isinstance(value, str) and value.strip()
        )
        sort = data.get("sort") if data.get("sort") in get_args(SortOrder) else None
        limit = data.get("limit")
        return cls(
            terms=tuple(terms),
            unmatched=unmatched[:3],
            sort=sort,
            limit=limit if isinstance(limit, int) and 1 <= limit <= MAX_LIMIT else None,
        )


@dataclass(frozen=True)
class Vocabulary:
    """Every value a filter may take, read from the authorised portfolio snapshot."""

    domains: tuple[str, ...]
    phases: tuple[str, ...]
    priorities: tuple[str, ...]
    managers: tuple[str, ...]
    name_tokens: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def of(cls, portfolio: PortfolioData) -> Vocabulary:
        projects = portfolio.projects
        name_tokens: dict[str, set[str]] = {}
        for project in projects:
            for token in _tokens(project.project_name):
                if len(token) >= 4 and token not in _FILLER:
                    name_tokens.setdefault(token, set()).add(project.project_id)
        return cls(
            domains=tuple(sorted({project.domain for project in projects})),
            phases=tuple(sorted({project.project_phase for project in projects})),
            priorities=tuple(reversed(CRITICALITY_LEVELS)),
            managers=tuple(sorted({project.project_manager for project in projects})),
            name_tokens={token: tuple(sorted(ids)) for token, ids in name_tokens.items()},
        )

    def values_for(self, field_name: str) -> tuple[str, ...]:
        return {
            "domain": self.domains,
            "phase": self.phases,
            "priority": self.priorities,
            "manager": self.managers,
            "health_band": HEALTH_BAND_NAMES,
        }.get(field_name, ())

    def valid(self, field_name: str, values: list[object] | tuple[object, ...]) -> tuple[str, ...]:
        """Keep only recorded values; name keywords must occur in a recorded project name."""
        if field_name == "name":
            return tuple(
                dict.fromkeys(
                    keyword
                    for value in values
                    if isinstance(value, str)
                    and (keyword := value.strip().lower())
                    and self.name_matches(keyword)
                )
            )
        allowed = {value.lower(): value for value in self.values_for(field_name)}
        return tuple(
            dict.fromkeys(
                allowed[value.strip().lower()]
                for value in values
                if isinstance(value, str) and value.strip().lower() in allowed
            )
        )

    def name_matches(self, keyword: str) -> tuple[str, ...]:
        """Project IDs whose name contains the keyword, tolerating plural and stem variants."""
        stem = keyword[:5] if len(keyword) >= 6 else keyword
        return tuple(
            sorted(
                {
                    project_id
                    for token, ids in self.name_tokens.items()
                    if token == keyword or (len(stem) >= 5 and token.startswith(stem))
                    for project_id in ids
                }
            )
        )


@dataclass(frozen=True)
class ParsedQuestion:
    query: ProjectQuery
    residual: str
    """The question with its filter wording removed, for routing on what is actually asked."""


def _tokens(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _normalise(question: str) -> str:
    text = question.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9'\s-]", " ", text)
    return " ".join(text.split())


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for index, char in enumerate(left, start=1):
        current = [index]
        for position, other in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[position] + 1,
                    previous[position - 1] + (char != other),
                )
            )
        previous = current
    return previous[-1]


def _is_filler(token: str) -> bool:
    if token in _FILLER or token.isdigit():
        return True
    return len(token) >= _FILLER_TYPO_MIN_LENGTH and any(
        abs(len(word) - len(token)) <= 1 and _edit_distance(token, word) == 1
        for word in _FILLER
        if len(word) >= _FILLER_TYPO_MIN_LENGTH
    )


class _Parser:
    def __init__(self, question: str, portfolio: PortfolioData) -> None:
        self.original = question
        self.text = _normalise(question)
        self.vocabulary = Vocabulary.of(portfolio)
        self.consumed: list[tuple[int, int]] = []
        self.terms: list[Term] = []
        self.unmatched: list[str] = []
        self.sort: SortOrder | None = None
        self.limit: int | None = None
        self.domain_tokens = {domain: set(_tokens(domain)) for domain in self.vocabulary.domains}
        self.manager_tokens = {
            manager: set(_tokens(manager)) for manager in self.vocabulary.managers
        }
        # Unrecognised wording is reported only when the question is about the project list.
        self.about_projects = _ABOUT_PROJECTS_PATTERN.search(self.text) is not None

    # ------------------------------------------------------------------ bookkeeping
    def _free(self, start: int, end: int) -> bool:
        return all(end <= left or start >= right for left, right in self.consumed)

    def _consume(self, start: int, end: int) -> None:
        self.consumed.append((start, end))

    def _add(self, term: Term) -> None:
        if term.values and term not in self.terms:
            self.terms.append(term)

    def residual(self) -> str:
        kept = []
        position = 0
        for start, end in sorted(self.consumed):
            if start > position:
                kept.append(self.text[position:start])
            position = max(position, end)
        kept.append(self.text[position:])
        text = " ".join(" ".join(kept).split())
        if self.terms and _OTHER_SUBJECTS_PATTERN.search(text):
            # "risks in tech projects" asks about risks; the projects are only the filter.
            text = " ".join(_PROJECT_NOUN_PATTERN.sub(" ", text).split())
        return text

    # ------------------------------------------------------------------ recognisers
    def _limit_and_sort(self) -> None:
        if not self.about_projects:
            return
        match = _LIMIT_PATTERN.search(self.text)
        if match:
            value = int(match.group(1) or match.group(2))
            if 1 <= value <= MAX_LIMIT:
                self.limit = value
                self._consume(*match.span())
        for pattern, order in _SORT_PATTERNS:
            sort_match = pattern.search(self.text)
            explicit = sort_match is not None and "by" in sort_match.group(0)
            if sort_match and (self.limit is not None or explicit):
                self.sort = order
                self._consume(*sort_match.span())
                break
        if self.limit is not None and self.sort is None and re.search(r"\btop\b", self.text):
            self.sort = "priority"

    def _priorities(self) -> None:
        for match in _PRIORITY_PATTERN.finditer(self.text):
            level = next(group for group in match.groups() if group)
            self._add(Term("priority", (level.capitalize(),), match.group(0)))
            self._consume(*match.span())
        for match in _BARE_CRITICAL_PATTERN.finditer(self.text):
            if self._free(*match.span()):
                self._add(Term("priority", ("Critical",), "critical", interpreted=True))
                self._consume(*match.span())

    def _bands(self) -> None:
        for match in _BAND_PATTERN.finditer(self.text):
            bands = tuple(dict.fromkeys(_BAND_ALIASES[group] for group in match.groups() if group))
            self._add(Term("health_band", bands, match.group(0)))
            self._consume(*match.span())
        for match in _HEALTHY_PATTERN.finditer(self.text):
            word = next(group for group in match.groups() if group)
            bands = ("Green",) if word == "healthy" else ("Amber", "Red")
            self._add(Term("health_band", bands, word, interpreted=True))
            self._consume(*match.span(1 if match.group(1) else 2))

    def _phases(self) -> None:
        if not self.about_projects:
            return
        for phase in self.vocabulary.phases:
            name = re.escape(phase.lower())
            pattern = re.compile(
                rf"\b(?:in|during|at|within)\s+(?:the\s+)?{name}(?:\s+(?:phase|stage))?\b"
                rf"|\b{name}\s+(?:phase|stage)\b|\b{name}(?=\s+projects?\b)"
            )
            for match in pattern.finditer(self.text):
                if self._free(*match.span()):
                    self._add(Term("phase", (phase,), match.group(0)))
                    self._consume(*match.span())
        for match in re.finditer(r"\b([a-z]+)\s+(?:phase|stage)\b", self.text):
            if self._free(*match.span()) and not _is_filler(match.group(1)):
                self.unmatched.append(f"{match.group(1)} phase")
                self._consume(*match.span())

    def _match_manager(self, name: str) -> tuple[str, ...]:
        asked = set(_tokens(name)) - _FILLER
        if not asked:
            return ()
        full = [manager for manager in self.vocabulary.managers if manager.lower() == name]
        if full:
            return tuple(full)
        return tuple(
            manager
            for manager, tokens in self.manager_tokens.items()
            if asked <= tokens or (len(asked) == 1 and asked & tokens)
        )

    def _managers(self) -> None:
        for manager in self.vocabulary.managers if self.about_projects else ():
            for match in re.finditer(rf"\b{re.escape(manager.lower())}\b", self.text):
                if self._free(*match.span()):
                    cue = re.search(
                        r"\bnot\s+(?:managed|led|run|owned)\s+by\s+$", self.text[: match.start()]
                    )
                    self._add(Term("manager", (manager,), manager, excluded=bool(cue)))
                    self._consume(match.start() - (len(cue.group(0)) if cue else 0), match.end())
        for match in _MANAGER_CUE_PATTERN.finditer(self.text):
            if not self._free(*match.span("name")):
                continue
            name = match.group("name")
            managers = self._match_manager(name)
            if len(managers) == 1:
                self._add(Term("manager", managers, name, excluded=bool(match.group("negated"))))
            elif self.about_projects:
                self.unmatched.append(f"managed by {name}")
            else:
                continue
            self._consume(*match.span())
        for match in _POSSESSIVE_PATTERN.finditer(self.text):
            if not self._free(*match.span("name")):
                continue
            managers = self._match_manager(match.group("name"))
            if len(managers) == 1:
                self._add(Term("manager", managers, match.group("name")))
                self._consume(match.start("name"), match.end("name") + 2)

    def _full_domains(self) -> None:
        for domain in sorted(self.vocabulary.domains, key=len, reverse=True):
            for match in re.finditer(rf"\b{re.escape(domain.lower())}\b", self.text):
                if self._free(*match.span()):
                    self._add(Term("domain", (domain,), domain))
                    self._consume(*match.span())
        if re.search(r"\bIT\b", self.original):
            it_domains = tuple(
                domain for domain, tokens in self.domain_tokens.items() if "it" in tokens
            )
            for match in re.finditer(r"\bit\b(?=\s+(?:projects?|domain|systems?)\b)", self.text):
                if it_domains and self._free(*match.span()):
                    self._add(Term("domain", it_domains, "IT"))
                    self._consume(*match.span())

    def _resolve_phrase(self, phrase: str, excluded: bool, domain_cue: bool) -> bool:
        """Map a free modifier phrase onto recorded values; True when anything matched."""
        words = [word for word in _tokens(phrase) if not _is_filler(word)]
        words = [word for word in words if word not in _ANALYSIS_WORDS]
        if not words:
            return False
        matched_any = False
        unknown: list[str] = []
        for word in words:
            direct = tuple(
                domain
                for domain, tokens in self.domain_tokens.items()
                if word in tokens and not (word == "it" and not re.search(r"\bIT\b", self.original))
            )
            if direct:
                self._add(Term("domain", direct, word, excluded=excluded))
                matched_any = True
                continue
            umbrella = _UMBRELLA_TERMS.get(word)
            if umbrella:
                domains = tuple(
                    domain for domain, tokens in self.domain_tokens.items() if tokens & umbrella
                )
                if domains:
                    self._add(Term("domain", domains, word, excluded=excluded, interpreted=True))
                    matched_any = True
                    continue
            phase = next((value for value in self.vocabulary.phases if value.lower() == word), None)
            if phase:
                self._add(Term("phase", (phase,), word, excluded=excluded))
                matched_any = True
                continue
            if not domain_cue and self.vocabulary.name_matches(word):
                self._add(Term("name", (word,), word, excluded=excluded))
                matched_any = True
                continue
            unknown.append(word)
        if unknown and not matched_any and self.about_projects:
            self.unmatched.append(" ".join(unknown)[:_MAX_PHRASE_LENGTH])
        return matched_any or bool(unknown)

    def _exclusions(self) -> None:
        for match in _EXCLUSION_PATTERN.finditer(self.text):
            if not self._free(*match.span("phrase")):
                continue
            phrase = match.group("phrase")
            lowered = phrase.strip()
            managers = self._match_manager(lowered)
            priority = re.fullmatch(r"(critical|high|medium|low)(?:[- ]priority)?", lowered)
            band = _BAND_ALIASES.get(lowered.removesuffix(" projects").strip())
            if priority:
                self._add(Term("priority", (priority.group(1).capitalize(),), lowered, True))
            elif band:
                self._add(Term("health_band", (band,), lowered, True))
            elif len(managers) == 1 and not any(
                lowered in domain.lower() for domain in self.vocabulary.domains
            ):
                self._add(Term("manager", managers, lowered, True))
            else:
                full = [domain for domain in self.vocabulary.domains if domain.lower() in lowered]
                if full:
                    self._add(Term("domain", tuple(full), lowered, True))
                else:
                    self._resolve_phrase(lowered, excluded=True, domain_cue=False)
            self._consume(*match.span())

    def _modifiers(self) -> None:
        for match in _DOMAIN_CUE_PATTERN.finditer(self.text):
            group = "phrase" if match.group("phrase") else "after"
            if match.group(group) and self._free(*match.span(group)):
                self._resolve_phrase(match.group(group), excluded=False, domain_cue=True)
                self._consume(*match.span(group))
        for match in _MODIFIER_AFTER_PATTERN.finditer(self.text):
            if self._free(*match.span("phrase")):
                self._resolve_phrase(match.group("phrase"), excluded=False, domain_cue=False)
                self._consume(*match.span("phrase"))
        for match in _MODIFIER_BEFORE_PATTERN.finditer(self.text):
            start, end = match.span("phrase")
            words = self.text[start:end].split()
            # Only the run of words directly before the noun can describe it.
            trailing: list[str] = []
            for word in reversed(words):
                if _is_filler(word) or word in _ANALYSIS_WORDS:
                    break
                trailing.insert(0, word)
            if not trailing:
                continue
            phrase = " ".join(trailing)
            phrase_start = end - len(phrase) - 1
            if self._free(phrase_start, end):
                self._resolve_phrase(phrase, excluded=False, domain_cue=False)
                self._consume(phrase_start, end)

    def _unresolved_domain_cue(self) -> None:
        if (
            self.about_projects
            and _DOMAIN_WORD_PATTERN.search(self.text)
            and not any(term.field == "domain" for term in self.terms)
            and not self.unmatched
        ):
            self.unmatched.append("the domain you named")

    def parse(self) -> ParsedQuestion:
        self._limit_and_sort()
        self._exclusions()
        self._priorities()
        self._bands()
        self._phases()
        self._managers()
        self._full_domains()
        self._modifiers()
        self._unresolved_domain_cue()
        query = ProjectQuery(
            terms=tuple(self.terms),
            unmatched=tuple(dict.fromkeys(self.unmatched))[:3],
            sort=self.sort,
            limit=self.limit,
        )
        return ParsedQuestion(query=query, residual=self.residual())


def parse(question: str, portfolio: PortfolioData) -> ParsedQuestion:
    """Recognise how a question constrains the project list."""
    return _Parser(question, portfolio).parse()


def from_domains(domains: tuple[str, ...], phrase: str | None = None) -> ProjectQuery:
    """Express a legacy domain selector as a query."""
    if not domains:
        return ProjectQuery(unmatched=(phrase or "the domain you named",))
    return ProjectQuery(terms=(Term("domain", domains, phrase or " or ".join(domains)),))


def merge(local: ProjectQuery, model: ProjectQuery) -> ProjectQuery:
    """Combine a model interpretation with the deterministic one.

    Literal matches found in the text stay authoritative. The model may replace only terms that
    were interpretations or phrases that could not be matched. An empty model reply never removes
    an unmatched constraint, so a filter the user asked for is not silently dropped.
    """
    literal = [term for term in local.terms if not term.interpreted]
    literal_fields = {(term.field, term.excluded) for term in literal}
    adopted = [term for term in model.terms if (term.field, term.excluded) not in literal_fields]
    adopted_fields = {term.field for term in adopted}
    kept_interpretations = [
        term for term in local.terms if term.interpreted and term.field not in adopted_fields
    ]
    terms = [*literal, *kept_interpretations, *adopted]
    resolved = {term.phrase.lower() for term in terms}
    unmatched = [
        phrase
        for phrase in (*local.unmatched, *model.unmatched)
        if phrase.lower() not in resolved and not (terms and phrase.startswith("the "))
    ]
    return ProjectQuery(
        terms=tuple(terms),
        unmatched=tuple(dict.fromkeys(unmatched))[:3],
        sort=local.sort or model.sort,
        limit=local.limit or model.limit,
    )


@dataclass(frozen=True)
class Selection:
    """Projects that satisfy a query, in presentation order, with any health that was needed."""

    projects: tuple[Project, ...]
    health: dict[str, tuple[float, str]]
    total: int


def _value(project: Project, field_name: str, health: dict[str, tuple[float, str]]) -> str:
    if field_name == "domain":
        return project.domain
    if field_name == "phase":
        return project.project_phase
    if field_name == "priority":
        return project.business_priority
    if field_name == "manager":
        return project.project_manager
    if field_name == "health_band":
        return health[project.project_id][1]
    return project.project_name.lower()


def _satisfies(project: Project, term: Term, health: dict[str, tuple[float, str]]) -> bool:
    if term.field == "name":
        tokens = set(_tokens(project.project_name))
        found = any(
            keyword in tokens or any(token.startswith(keyword[:5]) for token in tokens)
            for keyword in term.values
        )
    else:
        found = _value(project, term.field, health) in term.values
    return not found if term.excluded else found


def select(query: ProjectQuery, portfolio: PortfolioData, as_of_date: date | None) -> Selection:
    """Apply a query to the authorised portfolio. Health comes only from the engine."""
    needs_health = query.sort in {"health_worst_first", "health_best_first"} or any(
        term.field == "health_band" for term in query.terms
    )
    health: dict[str, tuple[float, str]] = {}
    if needs_health:
        if as_of_date is None:
            raise ValueError("A health filter needs the analysis date.")
        for project in portfolio.projects:
            result = calculate_project_health(project.project_id, portfolio, as_of_date)
            health[project.project_id] = (result.overall_score, result.health_band)

    grouped: dict[tuple[str, bool], Term] = {}
    for term in query.terms:
        key = (term.field, term.excluded)
        existing = grouped.get(key)
        grouped[key] = (
            term
            if existing is None
            else Term(
                term.field,
                tuple(dict.fromkeys([*existing.values, *term.values])),
                f"{existing.phrase}, {term.phrase}",
                term.excluded,
                existing.interpreted or term.interpreted,
            )
        )
    matched = [
        project
        for project in portfolio.projects
        if all(_satisfies(project, term, health) for term in grouped.values())
    ]
    rank = {level: index for index, level in enumerate(reversed(CRITICALITY_LEVELS))}
    if query.sort == "health_worst_first":
        matched.sort(key=lambda item: (health[item.project_id][0], item.project_name))
    elif query.sort == "health_best_first":
        matched.sort(key=lambda item: (-health[item.project_id][0], item.project_name))
    elif query.sort == "priority":
        matched.sort(key=lambda item: (rank.get(item.business_priority, 99), item.project_name))
    else:
        matched.sort(key=lambda item: item.project_name)
    if query.limit is not None:
        matched = matched[: query.limit]
    return Selection(projects=tuple(matched), health=health, total=len(portfolio.projects))


def merged_terms(query: ProjectQuery) -> list[Term]:
    """One term per field and polarity, in a stable reading order."""
    order = list(FIELD_LABELS)
    grouped: dict[tuple[str, bool], Term] = {}
    for term in query.terms:
        key = (term.field, term.excluded)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = term
        else:
            grouped[key] = Term(
                term.field,
                tuple(dict.fromkeys([*existing.values, *term.values])),
                existing.phrase if existing.interpreted else term.phrase,
                term.excluded,
                existing.interpreted or term.interpreted,
            )
    return sorted(grouped.values(), key=lambda term: (order.index(term.field), term.excluded))


def _join(values: tuple[str, ...] | list[str], conjunction: str = "or") -> str:
    values = list(values)
    if len(values) <= 1:
        return "".join(values)
    return f"{', '.join(values[:-1])} {conjunction} {values[-1]}"


def describe(query: ProjectQuery) -> str:
    """Plain wording for the filters, e.g. 'domain Embedded Software and business priority High'."""
    parts = []
    for term in merged_terms(query):
        label = FIELD_LABELS[term.field].lower()
        quoted = [f"“{value}”" if term.field == "name" else value for value in term.values]
        if term.excluded:
            parts.append(f"{label} other than {_join(quoted, 'and')}")
        else:
            parts.append(f"{label} {_join(quoted)}")
    return _join(parts, "and")


def interpretation_notes(query: ProjectQuery) -> list[str]:
    """Say where a filter was read into the question rather than found in it verbatim."""
    notes = []
    for term in merged_terms(query):
        if not term.interpreted:
            continue
        label = FIELD_LABELS[term.field].lower()
        notes.append(
            f"“{term.phrase}” is not a recorded {label}, so it was read as "
            f"{_join(list(term.values), 'and')}."
        )
    return notes
