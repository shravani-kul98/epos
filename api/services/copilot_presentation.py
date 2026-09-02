"""Human-readable labels and safe fallback over an already selected evidence package."""

from __future__ import annotations

import re

from api import labels
from api.schemas import CopilotAnswer, EvidenceRecordOut, ProjectReferenceOut
from src.config import AI_DISCLAIMER
from src.data_loader import PortfolioData
from src.schemas import EvidencePackage
from src.ui_formatting import format_score

# What an empty result means for each calculated question, said plainly and no more broadly than
# the warning rule that selected the evidence.
_EMPTY_ANSWERS: dict[str, str] = {
    "risks_without_owner": (
        "No high-exposure risk you can access is missing a mitigation owner. Lower-exposure risks "
        "without an owner are listed in the Risks register."
    ),
    "milestones_at_risk": "No milestone you can access is forecast to slip.",
    "requirements_without_verification": (
        "No requirement you can access is flagged for missing verification evidence."
    ),
    "projects_needing_attention": "No project you can access needs attention at the moment.",
}
# How far before an identifier a project's name still counts as naming it, so "the Battery
# Programme project (P-002)" is not rewritten into "the Battery Programme project (Battery ...".
_NAME_WINDOW = 40


def _named_just_before(text: str, position: int, name: str) -> bool:
    """Whether the project's name already appears shortly before an identifier."""
    window = text[max(0, position - len(name) - _NAME_WINDOW) : position]
    return name.casefold() in window.casefold()


def from_calculated_evidence(
    intent: str, evidence: EvidencePackage, warnings: list[str]
) -> CopilotAnswer:
    """Present calculated facts when the optional narrative provider is unavailable."""
    findings: list[str] = []
    actions: list[str] = []
    attention = any(record.record_type == "attention_metadata" for record in evidence.records)
    records = [
        record
        for record in evidence.records
        if not (
            attention
            and record.record_type == "project_summary"
            and record.fields.get("needs_attention") != "True"
        )
    ]
    summaries = [record for record in records if record.record_type == "project_summary"]
    primary_warnings = {}
    for record in records:
        if record.record_type == "alert":
            primary_warnings.setdefault(record.fields.get("project_id"), record)
    summary = "Current calculated evidence is available; the AI explanation is unavailable."
    for record in records:
        f = record.fields
        name = f.get("project_name", f.get("project_id", record.record_id))
        if record.record_type == "attention_metadata":
            summary = f"{f['matched_count']} of {f['reviewed_count']} accessible projects need attention. {f['criteria']}"
        elif record.record_type == "project_summary":
            warning = primary_warnings.get(record.record_id)
            signal = (
                f" Main signal: {warning.fields['title']} [{warning.record_id}]." if warning else ""
            )
            findings.append(
                f"{name} ({record.record_id}): health {format_score(float(f['health_score']))} ({f['health_band']}), "
                f"confidence {format_score(float(f['confidence_score']))} ({f['confidence_band']}); "
                f"{f['critical_alerts']} Critical and {f['high_alerts']} High warnings.{signal}"
            )
        elif record.record_type in {"health_result", "confidence_result"}:
            band = f.get("health_band") or f.get("confidence_band")
            label = "Health" if record.record_type == "health_result" else "Confidence"
            findings.append(
                f"{name} ({record.record_id}): {label} {format_score(float(f['overall_score']))} ({band})."
            )
            if record.record_type == "health_result":
                summary = f"{name} ({record.record_id}): health is {band}. Review the calculated drivers and sources below."
                if f.get("critical_drivers"):
                    findings.extend(
                        line.strip() + f" [{record.record_id}]"
                        for line in f["critical_drivers"].split(" | ")[:3]
                    )
        elif record.record_type == "alert" and not attention:
            findings.append(
                f"{name}: {f['severity']} — {f['title']} [{record.record_id}]. Sources: {f['source_ids']}."
            )
            if f.get("recommended_next_step"):
                actions.append(f"{name}: {f['recommended_next_step']} [{record.record_id}].")
    if (
        not findings
        and not summaries
        and not any(record.record_type == "attention_metadata" for record in evidence.records)
    ):
        summary = _EMPTY_ANSWERS.get(
            intent,
            "Nothing in the records you can access matches this question. Check the project "
            "registers if you expected a result.",
        )
    return CopilotAnswer(
        status="ok",
        matched_intent=intent,
        matched_question=None,
        executive_summary=labels.humanise(summary),
        key_findings=findings,
        recommended_actions=list(dict.fromkeys(actions)),
        source_ids=list(dict.fromkeys(record.record_id for record in records)),
        evidence=[EvidenceRecordOut(**record.model_dump()) for record in records],
        human_review_required=False,
        disclaimer=AI_DISCLAIMER,
        warnings=[
            "AI narration is unavailable; these are current calculated facts, not an AI explanation.",
            *warnings,
        ],
        suggested_questions=[],
    )


def present(
    answer: CopilotAnswer, portfolio: PortfolioData, *, authored: bool = False
) -> CopilotAnswer:
    """Expand only known project identifiers, leaving citation keys and numbers unchanged.

    Engine messages also have their internal factor vocabulary rewritten. Prose the model
    ``authored`` for the reader only loses raw field keys; its words are kept as written.
    """
    readable = labels.humanise_keys if authored else labels.humanise
    names = {project.project_id: project.project_name for project in portfolio.projects}
    relevant = {source_id for source_id in answer.source_ids if source_id in names}
    relevant.update(
        record.fields.get("project_id")
        for record in answer.evidence
        if record.fields.get("project_id") in names and record.record_id in answer.source_ids
    )
    relevant.update(
        record.record_id
        for record in answer.evidence
        if record.record_id in names and record.record_id in answer.source_ids
    )
    if answer.resolved_project_id in names:
        relevant.add(answer.resolved_project_id)

    def expand(text: str) -> str:
        for project_id in sorted(relevant, key=len, reverse=True):
            name = names[project_id]
            pattern = re.compile(rf"(?<![\w-]){re.escape(project_id)}(?![\w-])")
            text = pattern.sub(
                lambda match, value=text, label=name, pid=project_id: (
                    match.group()
                    if _named_just_before(value, match.start(), label)
                    else f"{label} ({pid})"
                ),
                text,
            )
        protected = sorted({*answer.source_ids, *names.values()}, key=len, reverse=True)
        replacements = {}
        for index, value in enumerate(protected):
            if value in text:
                placeholder = f"EPOSREF{index}TOKEN"
                text = text.replace(value, placeholder)
                replacements[placeholder] = value
        text = readable(text)
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)
        return text

    # Weakest health first, so "the first one" in a follow-up is the project most in need.
    health_by_project: dict[str, float] = {}
    for record in answer.evidence:
        if record.record_type not in {"project_summary", "health_result"}:
            continue
        score = record.fields.get("health_score", record.fields.get("overall_score"))
        try:
            health_by_project[record.record_id] = float(score)
        except (TypeError, ValueError):
            continue
    ordered = sorted(relevant, key=lambda pid: (health_by_project.get(pid, float("inf")), pid))

    return answer.model_copy(
        update={
            "executive_summary": expand(answer.executive_summary),
            "key_findings": [expand(line) for line in answer.key_findings],
            "recommended_actions": [expand(line) for line in answer.recommended_actions],
            "project_references": [
                ProjectReferenceOut(project_id=pid, project_name=names[pid]) for pid in ordered
            ],
        }
    )
