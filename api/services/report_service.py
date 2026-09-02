"""The weekly executive report.

The report is assembled on request rather than stored. Everything in it is already calculated by
the engines or already recorded in the database, so a saved copy would only introduce a second
version of the truth that could go stale. Every statement carries the record identifiers it was
drawn from, because an executive summary that cannot be traced is an opinion.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, select

from api.models import DecisionTable
from api.schemas import (
    ExecutiveReport,
    ExecutiveReportItem,
    ExecutiveReportSection,
    PortfolioDashboard,
)
from api.services import analytics_service, delta_service
from src.data_loader import PortfolioData
from src.ui_formatting import format_score

_ATTENTION_LIMIT = 6
_ALERT_LIMIT = 6
_MOVEMENT_LIMIT = 8
_DECISION_LIMIT = 6


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """Count and noun agreeing with each other, so the prose never reads as a template."""
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def _day(value: date) -> str:
    """A report date as people write it: 25 Sep 2026."""
    return f"{value.day} {value:%b %Y}"


def _headline(dashboard: PortfolioDashboard) -> str:
    """One sentence stating the portfolio position, drawn only from the band tallies."""
    bands = dashboard.health_bands
    as_of = _day(dashboard.as_of_date)
    if dashboard.project_count == 0:
        return "No project currently holds enough delivery information to be scored."
    if dashboard.unassessed_count:
        assessed = dashboard.project_count - dashboard.unassessed_count
        return (
            f"{_plural(assessed, 'project')} assessed; "
            f"{_plural(dashboard.unassessed_count, 'project')} not yet assessed. "
            f"Assessed health: {bands.green} green, {bands.amber} amber, {bands.red} red "
            f"as at {as_of}."
        )
    if bands.red == 0 and bands.amber == 0:
        return (
            f"All {_plural(dashboard.project_count, 'project')} score in the green health band "
            f"as at {as_of}."
        )
    parts = []
    if bands.red:
        parts.append(f"{bands.red} {'is' if bands.red == 1 else 'are'} red")
    if bands.amber:
        parts.append(f"{bands.amber} {'is' if bands.amber == 1 else 'are'} amber")
    return (
        f"Of {_plural(dashboard.project_count, 'project')}, {' and '.join(parts)} "
        f"as at {as_of}."
    )


def _attention_section(dashboard: PortfolioDashboard) -> ExecutiveReportSection | None:
    """Projects in the red band, weakest first, each with its calculated score."""
    red = [
        project
        for project in dashboard.projects
        if project.health_band == "Red"
        and (project.assessment is None or project.assessment.is_assessed)
    ]
    if not red:
        return None

    items = [
        ExecutiveReportItem(
            text=(
                f"{project.project_name} scores {format_score(project.health_score)} with "
                f"{_plural(project.open_alert_count, 'open alert')}, "
                f"{project.critical_alert_count} of them critical."
            ),
            source_ids=[project.project_id],
        )
        for project in red[:_ATTENTION_LIMIT]
    ]
    return ExecutiveReportSection(
        key="attention",
        title="Projects needing attention",
        summary=f"{_plural(len(red), 'project')} in the red health band.",
        items=items,
    )


def _alert_section(dashboard: PortfolioDashboard) -> ExecutiveReportSection | None:
    """The most severe early warnings, with the next step the engine recommends."""
    severe = [alert for alert in dashboard.top_alerts if alert.severity in {"Critical", "High"}][
        :_ALERT_LIMIT
    ]
    if not severe:
        return None

    names = {project.project_id: project.project_name for project in dashboard.projects}
    items = [
        ExecutiveReportItem(
            text=(
                f"{names.get(alert.project_id, alert.project_id)}: {alert.title}. "
                f"{alert.recommended_next_step}"
            ),
            source_ids=list(alert.source_ids) or [alert.project_id],
        )
        for alert in severe
    ]
    return ExecutiveReportSection(
        key="alerts",
        title="Early warnings",
        summary=(
            f"{_plural(dashboard.alert_severities.critical, 'critical alert')} and "
            f"{_plural(dashboard.alert_severities.high, 'high alert')} are open."
        ),
        items=items,
    )


def _confidence_section(dashboard: PortfolioDashboard) -> ExecutiveReportSection | None:
    """Projects whose reporting confidence is low, because their numbers deserve less weight."""
    low = [
        project
        for project in dashboard.projects
        if project.confidence_band == "Low"
        and (project.assessment is None or project.assessment.is_assessed)
    ]
    if not low:
        return None

    items = [
        ExecutiveReportItem(
            text=(
                f"{project.project_name} reports at {format_score(project.confidence_score)} "
                "confidence, so its health score should be read with caution."
            ),
            source_ids=[project.project_id],
        )
        for project in low[:_ATTENTION_LIMIT]
    ]
    return ExecutiveReportSection(
        key="confidence",
        title="Reporting confidence",
        summary=f"{_plural(len(low), 'project')} report on incomplete or stale information.",
        items=items,
    )


def _unassessed_section(dashboard: PortfolioDashboard) -> ExecutiveReportSection | None:
    projects = [
        project
        for project in dashboard.projects
        if project.assessment is not None and not project.assessment.is_assessed
    ]
    if not projects:
        return None
    return ExecutiveReportSection(
        key="unassessed",
        title="Projects not yet assessed",
        summary="Delivery records are missing; fallback scores are not reported as an assessment.",
        items=[
            ExecutiveReportItem(
                text=f"{project.project_name}: add a milestone or task before interpreting delivery health.",
                source_ids=[project.project_id],
            )
            for project in projects
        ],
    )


def _movement_section(
    session: Session, project_ids: list[str], since: datetime, days: int
) -> ExecutiveReportSection | None:
    """What actually moved in the period, read from the audit trail rather than re-derived."""
    moved: list[tuple[int, str, str]] = []
    total = 0
    deltas = delta_service.build_many(session, project_ids, since)
    for project_id in project_ids:
        delta = deltas[project_id]
        if delta.total_changes == 0:
            continue
        total += delta.total_changes
        busiest = [
            group.label.lower()
            for group in sorted(delta.groups, key=lambda group: -len(group.entries))[:3]
        ]
        areas = busiest[0] if len(busiest) == 1 else f"{', '.join(busiest[:-1])} and {busiest[-1]}"
        moved.append(
            (
                delta.total_changes,
                project_id,
                f"{delta.project_name}: {_plural(delta.total_changes, 'change')}, "
                f"{'all' if len(delta.groups) <= 3 else 'mostly'} to {areas}.",
            )
        )

    if not moved:
        return None

    moved.sort(key=lambda row: (-row[0], row[1]))
    items = [
        ExecutiveReportItem(text=text, source_ids=[project_id])
        for _, project_id, text in moved[:_MOVEMENT_LIMIT]
    ]
    return ExecutiveReportSection(
        key="movement",
        title="Movement in the period",
        summary=(
            f"{_plural(total, 'record')} across {_plural(len(moved), 'project')} "
            f"changed in the last {_plural(days, 'day')}."
        ),
        items=items,
    )


def _decision_section(
    session: Session, project_ids: list[str], since: datetime, days: int
) -> ExecutiveReportSection | None:
    """Decisions resolved in the period and decisions still waiting on someone."""
    rows = [
        row
        for row in session.exec(select(DecisionTable)).all()
        if row.deleted_at is None and row.project_id in project_ids
    ]
    resolved = [
        row
        for row in rows
        if row.status.lower() != "proposed"
        and (delta_service.as_utc(row.updated_at) or since) >= since
    ]
    waiting = [row for row in rows if row.status.lower() == "proposed"]
    if not resolved and not waiting:
        return None

    items = [
        ExecutiveReportItem(
            text=f"{row.title} was {row.status.lower()} by {row.approver or row.owner}.",
            source_ids=[row.decision_id, row.project_id],
        )
        for row in sorted(resolved, key=lambda row: row.decision_id)[:_DECISION_LIMIT]
    ]
    items += [
        ExecutiveReportItem(
            text=f"{row.title} is still waiting on {row.owner}.",
            source_ids=[row.decision_id, row.project_id],
        )
        for row in sorted(waiting, key=lambda row: row.decision_id)[:_DECISION_LIMIT]
    ]
    return ExecutiveReportSection(
        key="decisions",
        title="Decisions",
        summary=(
            f"{_plural(len(resolved), 'decision')} resolved in the last "
            f"{_plural(days, 'day')}; {_plural(len(waiting), 'decision')} still waiting."
        ),
        items=items,
    )


def build(
    session: Session, portfolio: PortfolioData, as_of_date: date, days: int
) -> ExecutiveReport:
    """Assemble the report for the period ending at ``as_of_date``.

    ``days`` sets how far back the movement and decision sections look. The scored sections always
    describe the position as at ``as_of_date``, because a health score is a statement about now,
    not about a window.
    """
    dashboard = analytics_service.portfolio_dashboard(portfolio, as_of_date)
    since = datetime.now(UTC) - timedelta(days=days)
    project_ids = [project.project_id for project in portfolio.projects]

    sections = [
        section
        for section in (
            _unassessed_section(dashboard),
            _attention_section(dashboard),
            _alert_section(dashboard),
            _movement_section(session, project_ids, since, days),
            _decision_section(session, project_ids, since, days),
            _confidence_section(dashboard),
        )
        if section is not None
    ]

    source_ids = sorted(
        {item_id for section in sections for item in section.items for item_id in item.source_ids}
    )
    return ExecutiveReport(
        as_of_date=as_of_date,
        window_days=days,
        generated_at=datetime.now(UTC),
        headline=_headline(dashboard),
        project_count=dashboard.project_count,
        health_bands=dashboard.health_bands,
        confidence_bands=dashboard.confidence_bands,
        alert_severities=dashboard.alert_severities,
        sections=sections,
        source_ids=source_ids,
    )
