"""Reading delivery follow-ups out of meeting notes.

Extraction here is deterministic pattern matching, not generation. Every proposal names the exact
line it came from and the cue that matched, so a reader can judge it in a second and reject it just
as quickly. Nothing is created from a note until a person confirms it: the notes are evidence, and
turning evidence into a record is a decision only a human makes.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import NamedTuple

from api.schemas import MeetingNoteExtraction, MeetingNoteProposal

ACTION = "action"
RISK = "risk"
DECISION = "decision"

_MAX_TEXT = 240


class _Cue(NamedTuple):
    """A phrase that marks a line as worth proposing, and what it proposes."""

    kind: str
    pattern: re.Pattern[str]
    phrase: str


# Ordered by how strongly the cue commits the writer. A decision beats a risk, a risk beats an
# action, so a line saying "we agreed to accept the risk" is proposed once, as a decision.
_CUES: tuple[_Cue, ...] = (
    _Cue(DECISION, re.compile(r"\bdecision\b\s*:", re.I), "decision:"),
    _Cue(DECISION, re.compile(r"\bwe\s+(?:have\s+)?decided\b", re.I), "we decided"),
    _Cue(DECISION, re.compile(r"\bdecided\s+(?:to|that|against)\b", re.I), "decided to"),
    _Cue(DECISION, re.compile(r"\bagreed\s+(?:to|that|on)\b", re.I), "agreed to"),
    _Cue(DECISION, re.compile(r"\bsigned\s+off\b", re.I), "signed off"),
    _Cue(RISK, re.compile(r"\brisk\b\s*:", re.I), "risk:"),
    _Cue(RISK, re.compile(r"\bat\s+risk\b", re.I), "at risk"),
    _Cue(RISK, re.compile(r"\bconcern(?:ed|s)?\s+(?:that|about)\b", re.I), "concern that"),
    _Cue(RISK, re.compile(r"\bmight\s+(?:slip|miss|fail)\b", re.I), "might slip"),
    _Cue(RISK, re.compile(r"\bcould\s+(?:slip|miss|fail|delay)\b", re.I), "could slip"),
    _Cue(RISK, re.compile(r"\bblocked\s+by\b", re.I), "blocked by"),
    _Cue(ACTION, re.compile(r"\baction\b\s*:", re.I), "action:"),
    _Cue(ACTION, re.compile(r"\bto\s+do\b\s*:", re.I), "to do:"),
    _Cue(ACTION, re.compile(r"\bfollow(?:s|ing)?\s+up\b", re.I), "follow up"),
    _Cue(
        ACTION,
        re.compile(
            r"\b(?:will|to)\s+(?:confirm|chase|raise|send|review|check|book|draft|prepare|update|circulate|schedule)\b",
            re.I,
        ),
        "will confirm",
    ),
    _Cue(ACTION, re.compile(r"\bnext\s+step\b", re.I), "next step"),
)

# "Alex Morgan to confirm ...", "Alex to chase ...", "Owner: Alex Morgan"
_OWNER_LEAD = re.compile(r"^(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:will|to)\s+", re.M)
_OWNER_LABEL = re.compile(r"\bowner\s*:\s*(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", re.I)

_ISO_DATE = re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b")

_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s*")


def _clean(line: str) -> str:
    """Strip bullet markers and collapse whitespace, leaving the sentence a person wrote."""
    return " ".join(_BULLET.sub("", line).split())


def _owner(text: str) -> str | None:
    """The name the line makes responsible, when it names one."""
    labelled = _OWNER_LABEL.search(text)
    if labelled:
        return labelled.group("name")
    lead = _OWNER_LEAD.search(text)
    return lead.group("name") if lead else None


def _due_date(text: str) -> date | None:
    """An explicit ISO date on the line. Nothing is inferred from words like "next week"."""
    found = _ISO_DATE.search(text)
    if not found:
        return None
    try:
        return datetime.strptime(found.group("date"), "%Y-%m-%d").date()
    except ValueError:
        return None


def _first_cue(text: str) -> tuple[_Cue, str] | None:
    """The strongest cue on the line and the words that matched it, or None for narrative."""
    for cue in _CUES:
        match = cue.pattern.search(text)
        if match:
            return cue, " ".join(match.group(0).lower().split())
    return None


def extract(note_id: str, project_id: str, body: str) -> MeetingNoteExtraction:
    """Read follow-ups out of a note.

    Returns proposals only. Each one names its source line and the cue that matched, and none of
    them exists as a record until a person promotes it.
    """
    proposals: list[MeetingNoteProposal] = []
    for index, raw in enumerate(body.splitlines(), start=1):
        text = _clean(raw)
        if len(text) < 8:
            continue
        found = _first_cue(text)
        if found is None:
            continue
        cue, matched = found

        proposals.append(
            MeetingNoteProposal(
                proposal_id=f"{note_id}-L{index}",
                kind=cue.kind,
                text=text[:_MAX_TEXT],
                source_line_number=index,
                source_line=text,
                matched_phrase=matched,
                suggested_owner=_owner(text),
                suggested_due_date=_due_date(text),
            )
        )

    return MeetingNoteExtraction(
        note_id=note_id,
        project_id=project_id,
        line_count=len(body.splitlines()),
        proposals=proposals,
        action_count=sum(1 for item in proposals if item.kind == ACTION),
        risk_count=sum(1 for item in proposals if item.kind == RISK),
        decision_count=sum(1 for item in proposals if item.kind == DECISION),
    )
