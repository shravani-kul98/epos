"""Risk records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.crud import (
    apply_update,
    ensure_absent,
    ensure_not_referenced_by_decisions,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import RiskTable
from api.schemas import RiskCreate, RiskOut, RiskUpdate
from api.security.dependencies import CurrentUser, RiskManager
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import risk_row_out
from api.services import activity_service, notification_service, record_owners
from api.services.record_references import next_reference
from src.scoring_rules import StatusDomain, normalize_status
from src.workflow_rules import (
    MITIGATION_STATUSES_ALLOWING_CLOSURE,
    RISK_CLOSED,
    RISK_STATUSES_REQUIRING_RATIONALE,
)

router = APIRouter(prefix="/risks", tags=["risks"])

_LABEL = "Risk"
_NON_COLUMN_FIELDS = frozenset({"rationale", "mitigation_owner_user_id"})
_OWNER_LINK = {"id_field": "mitigation_owner_user_id", "name_field": "mitigation_owner"}


def _ensure_mitigation_finished(mitigation_status: str | None) -> None:
    """A risk is closed only once its mitigation is complete or no longer needed."""
    recorded = (
        normalize_status(mitigation_status, StatusDomain.MITIGATION) if mitigation_status else None
    )
    if recorded not in MITIGATION_STATUSES_ALLOWING_CLOSURE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Set the mitigation to Complete or Not Required before closing the risk.",
        )


def _present(row: RiskTable) -> RiskOut:
    return risk_row_out(row)


def _notify_owner(
    session: SessionDep, row: RiskTable, previous_owner_id: int | None, actor: CurrentUser
) -> None:
    record_owners.notify_new_owner(
        session,
        owner_id=row.mitigation_owner_user_id,
        previous_owner_id=previous_owner_id,
        kind=notification_service.RISK_ASSIGNED,
        title=f"You own the mitigation of risk {row.risk_id}: {row.risk_name}",
        detail=f"Mitigation due {row.due_date:%d %b %Y}.",
        project_id=row.project_id,
        entity_type=_LABEL,
        entity_id=row.risk_id,
        actor=actor,
    )


@router.get("", response_model=list[RiskOut])
def list_risks(
    session: SessionDep, actor: CurrentUser, project_id: str | None = Query(default=None)
) -> list[RiskOut]:
    """List risks, optionally filtered to one project."""
    rows = list_rows(session, RiskTable, project_id)
    rows = scope_rows(session, actor, rows)
    return [_present(row) for row in sorted(rows, key=lambda r: r.risk_id)]


@router.get("/{risk_id}", response_model=RiskOut)
def get_risk(risk_id: str, session: SessionDep, actor: CurrentUser) -> RiskOut:
    """Return one risk."""
    row = get_or_404(session, RiskTable, risk_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.post("", response_model=RiskOut, status_code=status.HTTP_201_CREATED)
def create_risk(payload: RiskCreate, session: SessionDep, actor: RiskManager) -> RiskOut:
    """Create a risk, allocating the next project reference when none is supplied."""
    require_project_access(session, actor, payload.project_id, write=True)
    if payload.status == RISK_CLOSED:
        _ensure_mitigation_finished(payload.mitigation_status)
    risk_id = payload.risk_id or next_reference(session, payload.project_id, "R")
    ensure_absent(session, RiskTable, risk_id, _LABEL)
    row = RiskTable(
        **{**payload.model_dump(exclude={"mitigation_owner_user_id"}), "risk_id": risk_id}
    )
    record_owners.apply_owner_link(
        session,
        row,
        payload.project_id,
        **_OWNER_LINK,
        user_id=payload.mitigation_owner_user_id,
        id_supplied=payload.mitigation_owner_user_id is not None,
        name_supplied=False,
    )
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=risk_id,
        project_id=payload.project_id,
        summary=f"Raised risk {payload.risk_name}",
        actor=actor,
    )
    _notify_owner(session, row, None, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{risk_id}", response_model=RiskOut)
def update_risk(
    risk_id: str, payload: RiskUpdate, session: SessionDep, actor: RiskManager
) -> RiskOut:
    """Update the supplied fields of a risk.

    Closing or accepting a risk ends its scored exposure, so the reasoning must be recorded.
    """
    row = get_or_404(session, RiskTable, risk_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    current_status = normalize_status(row.status, StatusDomain.RISK) or row.status
    ends_management = (
        payload.status is not None
        and payload.status != current_status
        and payload.status in RISK_STATUSES_REQUIRING_RATIONALE
    )
    if ends_management and payload.rationale is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Record why risk {risk_id} is being marked {payload.status}.",
        )
    if payload.status == RISK_CLOSED and current_status != RISK_CLOSED:
        _ensure_mitigation_finished(
            payload.mitigation_status
            if "mitigation_status" in payload.model_fields_set
            else row.mitigation_status
        )
    previous_owner_id = row.mitigation_owner_user_id
    before = apply_update(row, payload, actor.email, exclude=_NON_COLUMN_FIELDS)
    after = payload.model_dump(exclude_unset=True, exclude=set(_NON_COLUMN_FIELDS))
    link_before = record_owners.apply_owner_link(
        session,
        row,
        row.project_id,
        **_OWNER_LINK,
        user_id=payload.mitigation_owner_user_id,
        id_supplied="mitigation_owner_user_id" in payload.model_fields_set,
        name_supplied="mitigation_owner" in payload.model_fields_set,
    )
    for field_name, value in link_before.items():
        before.setdefault(field_name, value)
        after[field_name] = getattr(row, field_name)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type=_LABEL,
        entity_id=risk_id,
        project_id=row.project_id,
        summary=f"Updated risk {row.risk_name}",
        detail=payload.rationale or activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    _notify_owner(session, row, previous_owner_id, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


@router.delete("/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_risk(
    risk_id: str, row_version: RowVersionDep, session: SessionDep, actor: RiskManager
) -> None:
    """Withdraw a risk. The record is retained for audit."""
    row = get_or_404(session, RiskTable, risk_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    ensure_not_referenced_by_decisions(session, row.project_id, "related_risk_id", risk_id, _LABEL)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=risk_id,
        project_id=row.project_id,
        summary=f"Deleted risk {row.risk_name}",
        actor=actor,
    )
    session.commit()
