"""Governed upkeep of verification evidence: test results and requirement trace links."""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import SQLModel

from api import clock
from api.crud import (
    ensure_absent,
    ensure_referenced_in_project,
    ensure_row_version,
    get_or_404,
    list_rows,
    soft_delete,
    stamp_create,
    stamp_update,
    to_entity,
)
from api.dependencies import RowVersionDep, SessionDep
from api.models import MilestoneTable, RequirementTable, TaskTable, TestCaseTable, TraceLinkTable
from api.schemas import (
    TestCaseCreate,
    TestCaseOut,
    TestCaseResultUpdate,
    TraceLinkCreate,
    TraceLinkOut,
)
from api.security.dependencies import CurrentUser, RequirementManager
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import test_case_out
from api.services import activity_service
from api.services.record_references import next_reference
from src.schemas import TestCase

router = APIRouter(tags=["verification"])

# The relationships the traceability and change-impact engines already read.
_LINK_TARGETS: Final[dict[str, tuple[str, type[SQLModel], str]]] = {
    "Task": ("implemented_by", TaskTable, "Task"),
    "TestCase": ("verified_by", TestCaseTable, "Test case"),
    "Milestone": ("delivered_in", MilestoneTable, "Milestone"),
}


def _link_out(row: TraceLinkTable) -> TraceLinkOut:
    return TraceLinkOut.model_validate(row, from_attributes=True)


@router.get("/trace-links", response_model=list[TraceLinkOut])
def list_trace_links(
    session: SessionDep, actor: CurrentUser, project_id: str | None = Query(default=None)
) -> list[TraceLinkOut]:
    rows = scope_rows(session, actor, list_rows(session, TraceLinkTable, project_id))
    return [_link_out(row) for row in sorted(rows, key=lambda link: link.trace_link_id)]


@router.post("/trace-links", response_model=TraceLinkOut, status_code=status.HTTP_201_CREATED)
def create_trace_link(
    payload: TraceLinkCreate, session: SessionDep, actor: RequirementManager
) -> TraceLinkOut:
    """Link a requirement to the task, test case or milestone that realises it."""
    require_project_access(session, actor, payload.project_id, write=True)
    link_type, table, label = _LINK_TARGETS[payload.target_type]
    ensure_referenced_in_project(
        session, RequirementTable, payload.requirement_id, payload.project_id, "Requirement"
    )
    ensure_referenced_in_project(session, table, payload.target_id, payload.project_id, label)
    if any(
        link.source_id == payload.requirement_id
        and link.target_type == payload.target_type
        and link.target_id == payload.target_id
        for link in list_rows(session, TraceLinkTable, payload.project_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{payload.requirement_id} is already linked to {payload.target_id}.",
        )
    trace_link_id = next_reference(session, payload.project_id, "TL")
    ensure_absent(session, TraceLinkTable, trace_link_id, "Trace link")
    row = TraceLinkTable(
        trace_link_id=trace_link_id,
        project_id=payload.project_id,
        source_type="Requirement",
        source_id=payload.requirement_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        link_type=link_type,
    )
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type="Trace link",
        entity_id=trace_link_id,
        project_id=payload.project_id,
        summary=f"Linked {payload.requirement_id} to {label.lower()} {payload.target_id}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _link_out(row)


@router.delete("/trace-links/{trace_link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trace_link(
    trace_link_id: str, row_version: RowVersionDep, session: SessionDep, actor: RequirementManager
) -> None:
    """Withdraw a link. The record is retained for audit."""
    row = get_or_404(session, TraceLinkTable, trace_link_id, "Trace link")
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type="Trace link",
        entity_id=trace_link_id,
        project_id=row.project_id,
        summary=f"Removed the link from {row.source_id} to {row.target_id}",
        actor=actor,
    )
    session.commit()


@router.post("/test-cases", response_model=TestCaseOut, status_code=status.HTTP_201_CREATED)
def create_test_case(
    payload: TestCaseCreate, session: SessionDep, actor: RequirementManager
) -> TestCaseOut:
    """Define a test case. It starts Not Run; a result needs its own recorded evidence."""
    require_project_access(session, actor, payload.project_id, write=True)
    test_case_id = payload.test_case_id or next_reference(session, payload.project_id, "TC")
    ensure_absent(session, TestCaseTable, test_case_id, "Test case")
    row = TestCaseTable(
        test_case_id=test_case_id,
        project_id=payload.project_id,
        test_case_name=payload.test_case_name,
        owner=payload.owner,
        status="Not Run",
        verification_evidence=None,
        last_updated_date=clock.utc_today(),
    )
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type="Test case",
        entity_id=test_case_id,
        project_id=payload.project_id,
        summary=f"Defined test case {test_case_id}: {payload.test_case_name}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return test_case_out(to_entity(row, TestCase)).model_copy(
        update={"row_version": row.row_version}
    )


@router.patch("/test-cases/{test_case_id}", response_model=TestCaseOut)
def record_test_result(
    test_case_id: str,
    payload: TestCaseResultUpdate,
    session: SessionDep,
    actor: RequirementManager,
) -> TestCaseOut:
    """Record a verification result. A pass must name the evidence that shows it."""
    row = get_or_404(session, TestCaseTable, test_case_id, "Test case")
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, payload.row_version)
    before = {"status": row.status, "verification_evidence": row.verification_evidence}
    row.status = payload.status
    # Evidence belongs to the result it supports, so a new result never inherits an old pass.
    row.verification_evidence = payload.verification_evidence
    row.last_updated_date = clock.utc_today()
    stamp_update(row, actor.email)
    session.add(row)
    after = {"status": row.status, "verification_evidence": row.verification_evidence}
    activity_service.record(
        session,
        action="result_recorded",
        entity_type="Test case",
        entity_id=test_case_id,
        project_id=row.project_id,
        summary=f"Recorded {row.status} for test case {test_case_id}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return test_case_out(to_entity(row, TestCase)).model_copy(
        update={"row_version": row.row_version}
    )
