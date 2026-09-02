"""Grounded answers about EPOS itself.

Only allowlisted documentation chunks and deterministic source-tree metadata are sent. The model
explains those sources; it cannot inspect arbitrary files, answer from hidden configuration, or
turn documentation into project-delivery facts.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from api.schemas import CopilotAnswer, EvidenceRecordOut
from api.services.semantic_router import EPOS_KNOWLEDGE
from src.ai_assistant import (
    RESPONSE_SCHEMA,
    Transport,
    citation_validation_warnings,
    complete_structured,
    unsupported_identifier_warnings,
)
from src.config import AI_DISCLAIMER, AI_UNAVAILABLE_MESSAGE
from src.schemas import CopilotResponse

logger = logging.getLogger(__name__)

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_MAX_CHUNKS: Final[int] = 6
_MAX_CHUNK_CHARS: Final[int] = 2400

# These files describe the product contract. Operational logs, environment files, source data, and
# arbitrary repository content are intentionally outside the retrieval boundary.
_DOCUMENTS: Final[tuple[tuple[str, str, str], ...]] = (
    ("user-guide", "EPOS user guide", "docs/user-guide.md"),
    ("access", "EPOS access by role", "docs/access-by-role.md"),
    ("architecture", "Architecture", "docs/architecture.md"),
    ("next-architecture", "EPOS Next architecture", "docs/epos-next-architecture.md"),
    ("ai-governance", "AI governance", "docs/ai-governance.md"),
    ("scoring", "Scoring methodology", "docs/scoring-methodology.md"),
    ("change-impact", "Change impact methodology", "docs/change-impact-methodology.md"),
    ("scenario", "Scenario methodology", "docs/scenario-methodology.md"),
    ("functional-requirements", "Functional requirements", "docs/functional-requirements.md"),
    (
        "non-functional-requirements",
        "Non-functional requirements",
        "docs/non-functional-requirements.md",
    ),
    ("roadmap", "Roadmap", "docs/roadmap.md"),
    ("local-guide", "Local usage guide", "docs/epos-next-local-guide.md"),
    ("ui-guide", "Interface design guide", "docs/ui-design-guide.md"),
)
# Written for people using EPOS rather than for the people building it. Help answers read these
# first; the technical documents are consulted only when these guides do not cover a question.
_USER_DOCUMENTS: Final[frozenset[str]] = frozenset({"docs/user-guide.md", "docs/access-by-role.md"})
_MIN_GUIDE_CHUNKS: Final[int] = 2
_MAX_TECHNICAL_CHUNKS: Final[int] = 2
# A word a guide section sets in bold, such as a glossary term, counts as much as a heading word.
_BOLD: Final[re.Pattern[str]] = re.compile(r"\*\*(.+?)\*\*")
_TERM_WEIGHT: Final[int] = 4

_KNOWLEDGE_SYSTEM_PROMPT: Final[str] = (
    "You explain EPOS using ONLY the supplied documentation and metadata records. Do not use prior "
    "knowledge. Do not invent implemented features, test outcomes, dates, roadmap commitments, "
    "production readiness, architecture, or limitations. Do not calculate health, confidence, risk "
    "severity, change impact, forecast dates, or scenario outcomes. If the sources do not answer the "
    "question, say what is missing. Distinguish a static test-source inventory from evidence that "
    "tests executed or passed. Cite every factual claim through source_ids, using only the supplied "
    "valid_source_ids. Set human_review_required to true and use the supplied disclaimer exactly."
)

_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "about",
        "and",
        "are",
        "can",
        "does",
        "for",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "of",
        "on",
        "the",
        "this",
        "to",
        "what",
        "which",
        "with",
        "you",
    }
)


@dataclass(frozen=True)
class _Chunk:
    source_id: str
    document: str
    path: str
    section: str
    content: str

    def evidence(self) -> EvidenceRecordOut:
        return EvidenceRecordOut(
            record_type="documentation",
            record_id=self.source_id,
            fields={
                "document": self.document,
                "path": self.path,
                "section": self.section,
                "content": self.content,
            },
        )


def _chunk(
    key: str,
    title: str,
    relative_path: str,
    heading: str,
    body: list[str],
    index: int,
) -> _Chunk | None:
    content = "\n".join(body).strip()
    if not content:
        return None
    return _Chunk(
        source_id=f"DOC-{key}-{index:02d}",
        document=title,
        path=relative_path,
        section=heading,
        content=content[:_MAX_CHUNK_CHARS],
    )


def _fingerprint(paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
    """Identify file contents cheaply, so a cache is rebuilt as soon as any file changes."""
    stamps = []
    for path in paths:
        stat = path.stat()
        stamps.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(stamps)


_chunk_cache: dict[str, tuple[tuple[tuple[str, int, int], ...], tuple[_Chunk, ...]]] = {}
_inventory_cache: dict[str, tuple[tuple[tuple[str, int, int], ...], tuple[int, int, int]]] = {}


def _chunks() -> list[_Chunk]:
    """Heading-sized chunks from the documentation allowlist, reread only when a file changes."""
    paths = [_ROOT / relative for _, _, relative in _DOCUMENTS if (_ROOT / relative).is_file()]
    fingerprint = _fingerprint(paths)
    cached = _chunk_cache.get("documents")
    if cached is not None and cached[0] == fingerprint:
        return list(cached[1])
    chunks = _read_chunks()
    _chunk_cache["documents"] = (fingerprint, tuple(chunks))
    return chunks


def _read_chunks() -> list[_Chunk]:
    """Read heading-sized chunks from the documentation allowlist."""
    chunks: list[_Chunk] = []
    for key, title, relative_path in _DOCUMENTS:
        path = _ROOT / relative_path
        if not path.is_file():
            continue
        heading = title
        body: list[str] = []
        index = 0

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                candidate = _chunk(key, title, relative_path, heading, body, index + 1)
                if candidate is not None:
                    index += 1
                    chunks.append(candidate)
                heading = line.lstrip("# ").strip() or title
                body = []
            else:
                body.append(line)
        candidate = _chunk(key, title, relative_path, heading, body, index + 1)
        if candidate is not None:
            chunks.append(candidate)
    return chunks


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _rank(question: str, chunk: _Chunk) -> int:
    asked = _tokens(question)
    document = _tokens(chunk.document)
    heading = _tokens(chunk.section)
    content = _tokens(chunk.content)
    return len(asked & document) * 8 + len(asked & heading) * 4 + len(asked & content)


def _count_test_functions(python_files: list[Path]) -> int:
    total = 0
    for path in python_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError):
            continue
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return total


def _test_inventory() -> tuple[int, int, int]:
    """Count test files and functions, reparsing only when a test file is added or changed."""
    python_files = sorted((_ROOT / "tests").rglob("test_*.py"))
    frontend_files = sorted((_ROOT / "frontend" / "src").rglob("*.test.ts*"))
    fingerprint = _fingerprint([*python_files, *frontend_files])
    cached = _inventory_cache.get("tests")
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    counts = (len(python_files), _count_test_functions(python_files), len(frontend_files))
    _inventory_cache["tests"] = (fingerprint, counts)
    return counts


def _source_metadata() -> EvidenceRecordOut:
    """Describe the test source tree without claiming that any test executed."""
    python_test_files, python_functions, frontend_test_files = _test_inventory()
    if python_test_files == frontend_test_files == 0:
        # Deployment packages ship without the test tree; zero here would read as "no tests".
        return EvidenceRecordOut(
            record_type="application_metadata",
            record_id="META-TEST-SOURCE-INVENTORY",
            fields={
                "test_source": "not included in this deployment",
                "meaning": (
                    "The test suites are kept in the source repository and are not packaged with "
                    "the running application, so no count can be read here."
                ),
            },
        )
    return EvidenceRecordOut(
        record_type="application_metadata",
        record_id="META-TEST-SOURCE-INVENTORY",
        fields={
            "python_test_files": str(python_test_files),
            "python_test_functions": str(python_functions),
            "frontend_test_files": str(frontend_test_files),
            "meaning": (
                "Static source inventory only. These counts do not prove execution, pass status, "
                "or the number of parametrized test cases."
            ),
        },
    )


def retrieve(question: str) -> list[EvidenceRecordOut]:
    """Select the documentation most relevant to the question, deterministically."""
    ranked = sorted(_chunks(), key=lambda chunk: (-_rank(question, chunk), chunk.source_id))
    relevant: list[_Chunk] = []
    per_document: dict[str, int] = {}
    for chunk in ranked:
        if _rank(question, chunk) <= 0 or len(relevant) >= _MAX_CHUNKS:
            break
        if per_document.get(chunk.path, 0) >= 2:
            continue
        relevant.append(chunk)
        per_document[chunk.path] = per_document.get(chunk.path, 0) + 1
    if not relevant:
        relevant = [
            chunk
            for chunk in ranked
            if chunk.path in {"docs/architecture.md", "docs/ai-governance.md"}
        ][:_MAX_CHUNKS]
    return [_source_metadata(), *(chunk.evidence() for chunk in relevant)]


def _section_title(chunk: _Chunk) -> str:
    return f"{chunk.document}: {chunk.section}"


def help_sections() -> tuple[str, ...]:
    """Section titles of the guides for people using EPOS, so a reader can choose what to open."""
    return tuple(
        dict.fromkeys(_section_title(chunk) for chunk in _chunks() if chunk.path in _USER_DOCUMENTS)
    )


def retrieve_help(topic: str, sections: Iterable[str] = ()) -> list[EvidenceRecordOut]:
    """Guide sections for a help question: the chosen ones, then the closest guide matches.

    Technical documents are added only when the guides match too little, so an everyday question
    is answered from the user guide rather than from design or architecture notes.
    """
    chunks = _chunks()
    wanted = set(sections)
    picked = [chunk for chunk in chunks if _section_title(chunk) in wanted][:_MAX_CHUNKS]
    chosen = bool(picked)

    def best(candidates: Iterable[_Chunk]) -> list[_Chunk]:
        # Words every guide's title shares, such as the product name, cannot tell sections apart.
        shared = set.intersection(
            *(_tokens(title) for _, title, path in _DOCUMENTS if path in _USER_DOCUMENTS)
        )
        asked = _tokens(topic) - shared or _tokens(topic)
        words = " ".join(sorted(asked))
        scored = [
            (score, chunk)
            for chunk in candidates
            if (
                score := _rank(words, chunk)
                + _TERM_WEIGHT * len(asked & _tokens(" ".join(_BOLD.findall(chunk.content))))
            )
            > 0
        ]
        return [
            chunk for _, chunk in sorted(scored, key=lambda item: (-item[0], item[1].source_id))
        ]

    for chunk in best(chunk for chunk in chunks if chunk.path in _USER_DOCUMENTS):
        if len(picked) >= _MAX_CHUNKS:
            break
        if chunk not in picked:
            picked.append(chunk)
    if not chosen and len(picked) < _MIN_GUIDE_CHUNKS:
        technical = best(chunk for chunk in chunks if chunk.path not in _USER_DOCUMENTS)
        picked += technical[:_MAX_TECHNICAL_CHUNKS]
    records = [chunk.evidence() for chunk in picked]
    if _tokens(topic) & {"test", "tests", "tested", "testing"}:
        records.insert(0, _source_metadata())
    return records


def build_request_payload(question: str, evidence: list[EvidenceRecordOut]) -> dict[str, object]:
    """Build a strict grounded-explanation request."""
    source_ids = [record.record_id for record in evidence]
    user_content = json.dumps(
        {
            "question": question,
            "documentation_records": [record.model_dump() for record in evidence],
            "valid_source_ids": source_ids,
            "disclaimer": AI_DISCLAIMER,
        },
        sort_keys=True,
    )
    return {
        "messages": [
            {"role": "system", "content": _KNOWLEDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "epos_knowledge_answer",
                "strict": True,
                "schema": RESPONSE_SCHEMA,
            },
        },
    }


def _fallback(status: str, message: str, warnings: tuple[str, ...]) -> CopilotAnswer:
    return CopilotAnswer(
        status=status,
        matched_intent=EPOS_KNOWLEDGE,
        matched_question="Explain EPOS from its documentation.",
        executive_summary=message,
        key_findings=[],
        recommended_actions=[],
        source_ids=[],
        human_review_required=True,
        disclaimer=AI_DISCLAIMER,
        warnings=list(warnings),
        evidence=[],
        suggested_questions=[],
    )


def answer(question: str, transport: Transport | None = None) -> CopilotAnswer:
    """Answer one product question from selected documentation and metadata."""
    evidence = retrieve(question)
    completion = complete_structured(build_request_payload(question, evidence), transport)
    if completion.status != "ok" or completion.content is None:
        message = (
            AI_UNAVAILABLE_MESSAGE
            if completion.status == "unavailable"
            else "The documentation answer could not be completed."
        )
        return _fallback(completion.status, message, completion.warnings)

    try:
        response = CopilotResponse.model_validate_json(completion.content)
    except ValidationError as exc:
        logger.warning("Knowledge response was rejected: %s", type(exc).__name__)
        return _fallback(
            "invalid_response",
            "The documentation answer did not match the required structure and was rejected.",
            (f"Validation failed with {type(exc).__name__}.",),
        )

    valid_ids = {record.record_id for record in evidence}
    warnings = citation_validation_warnings(
        response.source_ids, valid_ids, "the supplied documentation"
    )
    warnings += unsupported_identifier_warnings(
        response,
        json.dumps([record.model_dump() for record in evidence]),
        "the supplied documentation",
    )
    if warnings:
        return _fallback(
            "invalid_response",
            "The documentation answer could not be grounded in the supplied evidence and was "
            "rejected.",
            tuple(warnings),
        )

    source_ids = response.source_ids
    used_evidence = [record for record in evidence if record.record_id in source_ids]
    return CopilotAnswer(
        status="ok",
        matched_intent=EPOS_KNOWLEDGE,
        matched_question="Explain EPOS from its documentation.",
        executive_summary=response.executive_summary,
        key_findings=response.key_findings,
        recommended_actions=response.recommended_actions,
        source_ids=source_ids,
        human_review_required=True,
        disclaimer=AI_DISCLAIMER,
        warnings=[],
        evidence=used_evidence,
        suggested_questions=[],
    )
