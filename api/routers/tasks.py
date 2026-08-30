"""Task records."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ValidationError
from sqlmodel import select

from api import clock
from api.crud import (
    apply_update,
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
from api.models import (
    DeliverableTable,
    DependencyTable,
    MilestoneTable,
    ProjectMemberTable,
    TaskTable,
    TraceLinkTable,
    UserTable,
)
from api.schemas import (
    TaskAssignmentResponse,
    TaskCompletionRequest,
    TaskCreate,
    TaskOut,
    TaskProgressEntry,
    TaskReviewRequest,
    TaskUpdate,
)
from api.security.dependencies import CurrentUser, WorkManager, WorkUpdater
from api.security.permissions import Permission, has_permission
from api.security.project_scope import require_project_access, scope_rows
from api.serializers import task_row_out
from api.services import activity_service, notification_service
from api.services.record_references import next_reference
from src.delivery_rules import (
    DeliveryHierarchyError,
    TaskHierarchyNode,
    ensure_valid_task_hierarchy,
)
from src.schemas import DeliveryTask
from src.scoring_rules import StatusDomain, normalize_status
from src.task_workflow import (
    REVIEW_ACCEPTED,
    REVIEW_PENDING,
    REVIEW_RETURNED,
    prepare_task_progress,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

_LABEL = "Task"
_ENGINEER_UPDATE_FIELDS = frozenset(
    {"completion_percent", "status", "is_blocked", "progress_note", "row_version"}
)
ASSIGNMENT_PENDING = "Pending"
ASSIGNMENT_ACCEPTED = "Accepted"
ASSIGNMENT_DECLINED = "Declined"


def _present(row: TaskTable) -> TaskOut:
    return task_row_out(row)


def _reset_assignment(row: TaskTable, previous_owner_id: int | None, actor: UserTable) -> None:
    """A new assignee has not answered yet, unless they assigned the work to themselves."""
    if row.owner_user_id == previous_owner_id:
        return
    row.assignment_note = None
    if row.owner_user_id is None:
        row.assignment_status = None
        row.assignment_responded_at = None
    elif row.owner_user_id == actor.id:
        row.assignment_status = ASSIGNMENT_ACCEPTED
        row.assignment_responded_at = datetime.now(UTC)
    else:
        row.assignment_status = ASSIGNMENT_PENDING
        row.assignment_responded_at = None


def _resolve_owner_user_id(
    session: SessionDep, project_id: str, owner_name: str | None
) -> int | None:
    if owner_name is None:
        return None
    statement = (
        select(UserTable.id)
        .join(ProjectMemberTable, ProjectMemberTable.user_id == UserTable.id)
        .where(
            ProjectMemberTable.project_id == project_id,
            UserTable.full_name == owner_name,
            UserTable.is_active.is_(True),
        )
    )
    matches = [user_id for user_id in session.exec(statement).all() if user_id is not None]
    return matches[0] if len(matches) == 1 else None


def _assignment_values(
    session: SessionDep, project_id: str, payload: TaskCreate | TaskUpdate
) -> dict[str, object]:
    if "owner_user_id" not in payload.model_fields_set:
        if "owner" not in payload.model_fields_set:
            return {}
        return {
            "owner": payload.owner,
            "owner_user_id": _resolve_owner_user_id(session, project_id, payload.owner),
        }
    if payload.owner_user_id is None:
        if payload.owner:
            raise HTTPException(
                status_code=422, detail="Choose an assignee or clear the owner name."
            )
        return {"owner_user_id": None, "owner": None}
    user = session.get(UserTable, payload.owner_user_id)
    membership = session.exec(
        select(ProjectMemberTable).where(
            ProjectMemberTable.project_id == project_id,
            ProjectMemberTable.user_id == payload.owner_user_id,
        )
    ).first()
    if (
        user is None
        or not user.is_active
        or membership is None
        or not has_permission(user.role, Permission.WORK_UPDATE)
    ):
        raise HTTPException(
            status_code=422,
            detail="Select an active project member whose role can update assigned tasks.",
        )
    if "owner" in payload.model_fields_set and payload.owner != user.full_name:
        raise HTTPException(
            status_code=422, detail="The owner name does not match the selected account."
        )
    return {"owner_user_id": user.id, "owner": user.full_name}


def _authorize_task_update(row: TaskTable, payload: TaskUpdate, actor: UserTable) -> None:
    if has_permission(actor.role, Permission.WORK_MANAGE):
        return
    if actor.id is None or row.owner_user_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may update progress only on tasks assigned to your account.",
        )
    forbidden_fields = payload.model_fields_set - _ENGINEER_UPDATE_FIELDS
    if forbidden_fields:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role may update only task status, progress, blocker state and notes.",
        )
    if normalize_status(payload.status, StatusDomain.SCHEDULE) == "Cancelled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ask the project's manager to cancel assigned work.",
        )


def _validate_schedule(values: dict[str, object]) -> DeliveryTask:
    try:
        return DeliveryTask.model_validate(
            {key: value for key, value in values.items() if key in DeliveryTask.model_fields}
        )
    except ValidationError as exc:
        detail = "; ".join(error["msg"] for error in exc.errors())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
        ) from exc


def _hierarchy_node(values: dict[str, object]) -> TaskHierarchyNode:
    parent_task_id = values.get("parent_task_id")
    deliverable_id = values.get("deliverable_id")
    return TaskHierarchyNode(
        task_id=str(values["task_id"]),
        project_id=str(values["project_id"]),
        parent_task_id=str(parent_task_id) if parent_task_id is not None else None,
        deliverable_id=str(deliverable_id) if deliverable_id is not None else None,
    )


def _validate_hierarchy(
    session: SessionDep,
    values: dict[str, object],
    *,
    replacing_id: str | None = None,
) -> None:
    candidate = _hierarchy_node(values)
    if candidate.deliverable_id is not None:
        ensure_referenced_in_project(
            session,
            DeliverableTable,
            candidate.deliverable_id,
            candidate.project_id,
            "Deliverable",
        )
    if candidate.parent_task_id == candidate.task_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Task {candidate.task_id} cannot be its own parent.",
        )
    if candidate.parent_task_id is not None:
        ensure_referenced_in_project(
            session,
            TaskTable,
            candidate.parent_task_id,
            candidate.project_id,
            "Parent Task",
        )
    nodes = [
        TaskHierarchyNode(
            task_id=row.task_id,
            project_id=row.project_id,
            parent_task_id=row.parent_task_id,
            deliverable_id=row.deliverable_id,
        )
        for row in list_rows(session, TaskTable, candidate.project_id)
        if row.task_id != replacing_id
    ]
    try:
        ensure_valid_task_hierarchy([*nodes, candidate])
    except DeliveryHierarchyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("", response_model=list[TaskOut])
def list_tasks(
    session: SessionDep,
    actor: CurrentUser,
    project_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None, max_length=20),
) -> list[TaskOut]:
    """List tasks, optionally filtered to one project or one review state."""
    rows = list_rows(session, TaskTable, project_id)
    rows = scope_rows(session, actor, rows)
    if review_status is not None:
        rows = [row for row in rows if row.review_status == review_status]
    return [_present(row) for row in sorted(rows, key=lambda t: t.task_id)]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, session: SessionDep, actor: CurrentUser) -> TaskOut:
    """Return one task."""
    row = get_or_404(session, TaskTable, task_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return _present(row)


@router.get("/{task_id}/progress", response_model=list[TaskProgressEntry])
def read_task_progress(
    task_id: str, session: SessionDep, actor: CurrentUser
) -> list[TaskProgressEntry]:
    """The task's recorded reports, newest first, with the notes their authors added."""
    row = get_or_404(session, TaskTable, task_id, _LABEL)
    require_project_access(session, actor, row.project_id)
    return activity_service.task_history(session, task_id)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, session: SessionDep, actor: WorkManager) -> TaskOut:
    """Create a task."""
    require_project_access(session, actor, payload.project_id, write=True)
    task_id = payload.task_id or next_reference(session, payload.project_id, "T")
    ensure_absent(session, TaskTable, task_id, _LABEL)
    ensure_referenced_in_project(
        session, MilestoneTable, payload.milestone_id, payload.project_id, "Milestone"
    )
    values = payload.model_dump()
    values["task_id"] = task_id
    task = _validate_schedule(values)
    try:
        values.update(
            prepare_task_progress(task, None, payload.model_fields_set, clock.utc_today())
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _validate_hierarchy(session, values)
    values.update(_assignment_values(session, payload.project_id, payload))
    row = TaskTable(**values)
    _reset_assignment(row, None, actor)
    stamp_create(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="created",
        entity_type=_LABEL,
        entity_id=task_id,
        project_id=payload.project_id,
        summary=f"Created task {payload.task_name}",
        actor=actor,
    )
    notification_service.notify(
        session,
        [row.owner_user_id],
        kind=notification_service.TASK_ASSIGNED,
        title=f"You were assigned task {payload.task_name}",
        project_id=payload.project_id,
        entity_type=_LABEL,
        entity_id=task_id,
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str, payload: TaskUpdate, session: SessionDep, actor: WorkUpdater
) -> TaskOut:
    """Update the supplied fields of a task."""
    row = get_or_404(session, TaskTable, task_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    _authorize_task_update(row, payload, actor)
    ensure_row_version(row, payload.row_version)
    if payload.milestone_id is not None:
        ensure_referenced_in_project(
            session, MilestoneTable, payload.milestone_id, row.project_id, "Milestone"
        )
    previous = to_entity(row, DeliveryTask)
    previous_owner_id = row.owner_user_id
    was_blocked = row.is_blocked
    note = payload.progress_note
    changes = payload.model_dump(exclude_unset=True, exclude={"row_version", "progress_note"})
    changes.update(_assignment_values(session, row.project_id, payload))
    candidate = previous.model_dump()
    candidate.update(changes)
    task = _validate_schedule(candidate)
    try:
        changes.update(
            prepare_task_progress(task, previous, payload.model_fields_set, clock.utc_today())
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    candidate.update(changes)
    _validate_schedule(candidate)
    _validate_hierarchy(session, candidate, replacing_id=task_id)
    if bool(candidate.get("is_blocked")) and not was_blocked and not (note and note.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Say what is blocking the task so the right person can clear it.",
        )
    reported_on = changes.pop("last_updated_date")
    normalized = TaskUpdate.model_validate({**changes, "row_version": payload.row_version})
    previous_report = row.last_updated_date
    before = apply_update(row, normalized, actor.email)
    row.last_updated_date = reported_on
    before["last_updated_date"] = previous_report
    changes["last_updated_date"] = reported_on
    was_complete = normalize_status(previous.status, StatusDomain.SCHEDULE) == "Complete"
    is_complete = normalize_status(row.status, StatusDomain.SCHEDULE) == "Complete"
    action = (
        "completed"
        if is_complete and not was_complete
        else "reopened" if was_complete and not is_complete else "updated"
    )
    _update_review_state(row, action, changes)
    _reset_assignment(row, previous_owner_id, actor)
    differences = activity_service.field_changes(before, changes)
    detail = activity_service.describe_changes(before, changes)
    if note:
        differences.append(activity_service.progress_note_change(note))
        detail = f"{detail}; Note: {note}" if detail else f"Note: {note}"
    if action == "completed" and row.review_status == REVIEW_PENDING:
        summary = f"Submitted task {row.task_name} for review"
    elif action == "updated" and (note or "completion_percent" in changes or "status" in changes):
        summary = (
            f"Reported progress on task {row.task_name}: {row.status}, "
            f"{row.completion_percent}% complete"
        )
    else:
        summary = f"{action.capitalize()} task {row.task_name}"
    session.add(row)
    activity_service.record(
        session,
        action=action,
        entity_type=_LABEL,
        entity_id=task_id,
        project_id=row.project_id,
        summary=summary,
        detail=detail,
        changes=differences,
        actor=actor,
    )
    _notify_task_change(session, row, action, previous_owner_id, was_blocked, note, actor)
    session.commit()
    session.refresh(row)
    return _present(row)


def _update_review_state(row: TaskTable, action: str, changes: dict[str, object]) -> None:
    """Keep reported completion and its optional acceptance consistent with the task."""
    complete = normalize_status(row.status, StatusDomain.SCHEDULE) == "Complete"
    if action == "completed" and row.review_required:
        row.review_status = REVIEW_PENDING
        row.reviewed_by = row.reviewed_at = row.review_note = None
    elif action in {"completed", "reopened"}:
        row.review_status = None
    elif "review_required" in changes:
        if not row.review_required and row.review_status == REVIEW_PENDING:
            row.review_status = None
        elif row.review_required and complete and row.review_status is None:
            row.review_status = REVIEW_PENDING


def _notify_task_change(
    session: SessionDep,
    row: TaskTable,
    action: str,
    previous_owner_id: int | None,
    was_blocked: bool,
    note: str | None,
    actor: UserTable,
) -> None:
    """Tell the people who need to act: a new assignee, or the project's managers."""
    common = {
        "project_id": row.project_id,
        "entity_type": _LABEL,
        "entity_id": row.task_id,
        "actor": actor,
    }
    if row.owner_user_id is not None and row.owner_user_id != previous_owner_id:
        notification_service.notify(
            session,
            [row.owner_user_id],
            kind=notification_service.TASK_ASSIGNED,
            title=f"You were assigned task {row.task_name}",
            **common,
        )
    managers = notification_service.project_managers(session, row.project_id)
    if was_blocked and not row.is_blocked:
        notification_service.resolve(
            session,
            entity_type=_LABEL,
            entity_id=row.task_id,
            kinds=[notification_service.TASK_BLOCKED],
        )
    if row.is_blocked and not was_blocked:
        notification_service.notify(
            session,
            managers,
            kind=notification_service.TASK_BLOCKED,
            title=f"{actor.full_name} reported task {row.task_name} as blocked",
            detail=note,
            **common,
        )
    if action == "completed":
        pending = row.review_status == REVIEW_PENDING
        notification_service.resolve(
            session,
            entity_type=_LABEL,
            entity_id=row.task_id,
            kinds=[notification_service.TASK_ASSIGNED, notification_service.REVIEW_RETURNED],
            user_ids=[actor.id],
        )
        notification_service.notify(
            session,
            managers,
            kind=(
                notification_service.REVIEW_REQUESTED
                if pending
                else notification_service.TASK_COMPLETED
            ),
            title=(
                f"{actor.full_name} completed task {row.task_name} and asked for review"
                if pending
                else f"{actor.full_name} completed task {row.task_name}"
            ),
            detail=note,
            **common,
        )


@router.post("/{task_id}/review", response_model=TaskOut)
def review_task(
    task_id: str, payload: TaskReviewRequest, session: SessionDep, actor: WorkManager
) -> TaskOut:
    """Accept reported completion, or return the task for rework with the reason.

    The person who completed the work cannot accept it, so acceptance is always a second view.
    """
    row = get_or_404(session, TaskTable, task_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, payload.row_version)
    if row.review_status != REVIEW_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This task is not waiting for review."
        )
    if row.owner_user_id is not None and row.owner_user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed work must be reviewed by someone other than its assignee.",
        )
    note = payload.note.strip() if payload.note else None
    before: dict[str, object] = {"review_status": row.review_status}
    changes: dict[str, object] = {}
    if payload.decision == "accept":
        row.review_status = REVIEW_ACCEPTED
        action, kind = "review_accepted", notification_service.REVIEW_ACCEPTED
        summary = f"Accepted completion of task {row.task_name}"
    else:
        previous = to_entity(row, DeliveryTask)
        resume_at = activity_service.progress_before_completion(session, task_id)
        progress = prepare_task_progress(
            previous.model_copy(update={"status": "In Progress", "completion_percent": resume_at}),
            previous,
            {"status", "completion_percent"},
            clock.utc_today(),
        )
        before.update(status=row.status, completion_percent=row.completion_percent)
        for field_name, value in progress.items():
            setattr(row, field_name, value)
        changes.update(status=row.status, completion_percent=row.completion_percent)
        row.review_status = REVIEW_RETURNED
        action, kind = "review_returned", notification_service.REVIEW_RETURNED
        summary = f"Returned task {row.task_name} for rework"
    row.reviewed_by = actor.full_name
    row.reviewed_at = datetime.now(UTC)
    row.review_note = note
    changes["review_status"] = row.review_status
    stamp_update(row, actor.email)
    differences = activity_service.field_changes(before, changes)
    if note:
        differences.append(activity_service.progress_note_change(note))
    session.add(row)
    activity_service.record(
        session,
        action=action,
        entity_type=_LABEL,
        entity_id=task_id,
        project_id=row.project_id,
        summary=summary,
        detail=f"Note: {note}" if note else None,
        changes=differences,
        actor=actor,
    )
    # The review is recorded, so the request stops being news for every manager who received it.
    notification_service.resolve(
        session,
        entity_type=_LABEL,
        entity_id=task_id,
        kinds=[notification_service.REVIEW_REQUESTED],
    )
    notification_service.notify(
        session,
        [row.owner_user_id],
        kind=kind,
        title=summary,
        detail=note,
        project_id=row.project_id,
        entity_type=_LABEL,
        entity_id=task_id,
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.post("/{task_id}/assignment", response_model=TaskOut)
def respond_to_assignment(
    task_id: str, payload: TaskAssignmentResponse, session: SessionDep, actor: WorkUpdater
) -> TaskOut:
    """The assignee accepts the work, or declines it with a reason so it can be reassigned."""
    row = get_or_404(session, TaskTable, task_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, payload.row_version)
    if actor.id is None or row.owner_user_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee can answer this assignment.",
        )
    if row.assignment_status != ASSIGNMENT_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assignment has already been answered.",
        )
    note = payload.note.strip() if payload.note else None
    before: dict[str, object] = {
        "assignment_status": row.assignment_status,
        "owner": row.owner,
        "owner_user_id": row.owner_user_id,
    }
    row.assignment_responded_at = datetime.now(UTC)
    row.assignment_note = note
    if payload.decision == "accept":
        row.assignment_status = ASSIGNMENT_ACCEPTED
        action, kind = "assignment_accepted", notification_service.ASSIGNMENT_ACCEPTED
        summary = f"{actor.full_name} accepted task {row.task_name}"
    else:
        row.assignment_status = ASSIGNMENT_DECLINED
        row.owner_user_id = None
        row.owner = None
        action, kind = "assignment_declined", notification_service.ASSIGNMENT_DECLINED
        summary = f"{actor.full_name} declined task {row.task_name}"
    stamp_update(row, actor.email)
    after = {field: getattr(row, field) for field in before}
    session.add(row)
    activity_service.record(
        session,
        action=action,
        entity_type=_LABEL,
        entity_id=task_id,
        project_id=row.project_id,
        summary=summary,
        detail=f"Note: {note}" if note else None,
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    notification_service.resolve(
        session,
        entity_type=_LABEL,
        entity_id=task_id,
        kinds=[notification_service.TASK_ASSIGNED],
        user_ids=[actor.id],
    )
    notification_service.notify(
        session,
        notification_service.project_managers(session, row.project_id),
        kind=kind,
        title=summary,
        detail=note,
        project_id=row.project_id,
        entity_type=_LABEL,
        entity_id=task_id,
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return _present(row)


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(
    task_id: str, payload: TaskCompletionRequest, session: SessionDep, actor: WorkUpdater
) -> TaskOut:
    """Record completion using the same ownership and concurrency checks as progress edits."""
    completion = TaskUpdate(
        row_version=payload.row_version,
        status="Complete",
        progress_note=payload.progress_note,
    )
    return update_task(task_id, completion, session, actor)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str, row_version: RowVersionDep, session: SessionDep, actor: WorkManager
) -> None:
    """Withdraw a task. The record is retained for audit."""
    row = get_or_404(session, TaskTable, task_id, _LABEL)
    require_project_access(session, actor, row.project_id, write=True)
    ensure_row_version(row, row_version)
    reference_ids = {
        child.task_id
        for child in list_rows(session, TaskTable, row.project_id)
        if child.parent_task_id == row.task_id
    }
    reference_ids.update(
        dependency.dependency_id
        for dependency in list_rows(session, DependencyTable, row.project_id)
        if (dependency.predecessor_type == "Task" and dependency.predecessor_id == row.task_id)
        or (dependency.successor_type == "Task" and dependency.successor_id == row.task_id)
    )
    reference_ids.update(
        link.trace_link_id
        for link in list_rows(session, TraceLinkTable, row.project_id)
        if (link.source_type == "Task" and link.source_id == row.task_id)
        or (link.target_type == "Task" and link.target_id == row.task_id)
    )
    if reference_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Task {row.task_id} cannot be withdrawn while live references remain: "
                f"{', '.join(sorted(reference_ids))}."
            ),
        )
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type=_LABEL,
        entity_id=task_id,
        project_id=row.project_id,
        summary=f"Deleted task {row.task_name}",
        actor=actor,
    )
    session.commit()
