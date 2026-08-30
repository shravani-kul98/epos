"""Project records and their child collections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from api import clock
from api.crud import (
    apply_update,
    ensure_absent,
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
    PROJECT_OWNED_AUDIT_TABLES,
    ActionTable,
    DeliverableTable,
    DependencyTable,
    GateTable,
    MilestoneTable,
    ProjectMemberTable,
    ProjectTable,
    RequirementTable,
    ResourceTable,
    RiskTable,
    TaskTable,
    TestCaseTable,
    UserTable,
    WorkPackageTable,
)
from api.schemas import (
    ActionOut,
    DeliverableOut,
    DependencyOut,
    GateOut,
    MilestoneOut,
    ProjectCreate,
    ProjectDelta,
    ProjectOut,
    ProjectUpdate,
    RequirementOut,
    ResourceOut,
    RiskOut,
    TaskOut,
    TestCaseOut,
    VersionedUpdate,
    WorkPackageOut,
)
from api.schemas_auth import (
    ProjectMemberCreate,
    ProjectMemberOut,
    ProjectMemberUpdate,
    ProjectOptions,
    ProjectUserOption,
)
from api.security.dependencies import (
    CurrentUser,
    ProjectCreator,
    ProjectEditor,
    ProjectMemberManager,
    ProjectRemover,
    WorkManager,
)
from api.security.permissions import Permission, has_permission, role_label
from api.security.project_scope import add_membership, require_project_access, scope_rows
from api.serializers import (
    action_row_out,
    dependency_out,
    gate_out,
    milestone_out,
    project_out,
    requirement_out,
    resource_out,
    risk_row_out,
    task_row_out,
    test_case_out,
)
from api.services import activity_service, delta_service
from src.schemas import (
    DeliveryMilestone,
    GovernedDependency,
    Project,
    Requirement,
    Resource,
    TestCase,
)
from src.scoring_rules import is_terminal_schedule_status

router = APIRouter(prefix="/projects", tags=["projects"])

_LABEL = "Project"


def _require_project_read(session: SessionDep, actor: CurrentUser, project_id: str) -> None:
    get_or_404(session, ProjectTable, project_id, _LABEL)
    require_project_access(session, actor, project_id)


@router.get("", response_model=list[ProjectOut])
def list_projects(session: SessionDep, actor: CurrentUser) -> list[ProjectOut]:
    """List every project."""
    rows = list_rows(session, ProjectTable, project_id=None)
    rows = scope_rows(session, actor, rows)
    rows.sort(key=lambda row: row.project_id)
    return [project_out(to_entity(row, Project), row.row_version) for row in rows]


@router.get("/options", response_model=ProjectOptions)
def project_creation_options(session: SessionDep, actor: ProjectCreator) -> ProjectOptions:
    """Return authorized domains and active accounts eligible to manage a project."""
    projects = scope_rows(session, actor, list_rows(session, ProjectTable, None))
    people = session.exec(
        select(UserTable)
        .where(UserTable.is_active.is_(True))
        .order_by(UserTable.full_name, UserTable.email)
    ).all()
    return ProjectOptions(
        domains=sorted({project.domain for project in projects}),
        managers=[
            _user_option(user)
            for user in people
            if has_permission(user.role, Permission.PROJECT_UPDATE)
        ],
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, session: SessionDep, actor: CurrentUser) -> ProjectOut:
    """Return one project."""
    row = get_or_404(session, ProjectTable, project_id, _LABEL)
    require_project_access(session, actor, project_id)
    return project_out(to_entity(row, Project), row.row_version)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate, session: SessionDep, actor: ProjectCreator
) -> ProjectOut:
    """Create a project."""
    ensure_absent(session, ProjectTable, payload.project_id, _LABEL)
    manager = (
        _selected_manager(session, payload.project_manager_user_id, payload.project_manager)
        if payload.project_manager_user_id is not None
        else None
    )
    row = ProjectTable(**payload.model_dump(exclude={"project_manager_user_id"}))
    # Creating a project states its current position, so it starts with a status date rather
    # than an immediate "no status recorded" alert that nothing in the wizard could clear.
    if row.status_update_date is None:
        row.status_update_date = clock.utc_today()
    stamp_create(row, actor.email)
    session.add(row)
    session.flush()
    add_membership(session, actor, payload.project_id, project_role="Project creator")
    if manager is not None and manager.id != actor.id:
        add_membership(session, manager, payload.project_id, project_role="Project manager")
        activity_service.record(
            session,
            action="assigned",
            entity_type="Project member",
            entity_id=manager.email,
            project_id=payload.project_id,
            summary=f"Assigned {manager.full_name} as Project manager",
            actor=actor,
        )
    activity_service.record(
        session,
        action="created",
        entity_type="Project",
        entity_id=payload.project_id,
        project_id=payload.project_id,
        summary=f"Created project {payload.project_name}",
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return project_out(to_entity(row, Project), row.row_version)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str, payload: ProjectUpdate, session: SessionDep, actor: ProjectEditor
) -> ProjectOut:
    """Update the supplied fields of a project.

    Choosing a manager by account keeps the recorded name and the account's access in step.
    """
    row = get_or_404(session, ProjectTable, project_id, _LABEL)
    require_project_access(session, actor, project_id, write=True)
    manager = None
    if payload.project_manager_user_id is not None:
        manager = _selected_manager(
            session,
            payload.project_manager_user_id,
            payload.project_manager if "project_manager" in payload.model_fields_set else None,
        )
    before = apply_update(row, payload, actor.email, exclude=frozenset({"project_manager_user_id"}))
    after = payload.model_dump(exclude_unset=True, exclude={"project_manager_user_id"})
    if manager is not None:
        before.setdefault("project_manager", row.project_manager)
        row.project_manager = manager.full_name
        after["project_manager"] = manager.full_name
        add_membership(session, manager, project_id, project_role="Project manager")
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type="Project",
        entity_id=project_id,
        project_id=project_id,
        summary=f"Updated project {row.project_name}",
        detail=activity_service.describe_changes(before, after),
        changes=activity_service.field_changes(before, after),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return project_out(to_entity(row, Project), row.row_version)


@router.post("/{project_id}/status-update", response_model=ProjectOut)
def record_status_update(
    project_id: str, payload: VersionedUpdate, session: SessionDep, actor: ProjectEditor
) -> ProjectOut:
    """Record that the project's status was reviewed today, dated by the server."""
    row = get_or_404(session, ProjectTable, project_id, _LABEL)
    require_project_access(session, actor, project_id, write=True)
    ensure_row_version(row, payload.row_version)
    before = {"status_update_date": row.status_update_date}
    row.status_update_date = clock.utc_today()
    stamp_update(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="updated",
        entity_type="Project",
        entity_id=project_id,
        project_id=project_id,
        summary=f"Recorded a status update for {row.project_name}",
        changes=activity_service.field_changes(
            before, {"status_update_date": row.status_update_date}
        ),
        actor=actor,
    )
    session.commit()
    session.refresh(row)
    return project_out(to_entity(row, Project), row.row_version)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    row_version: RowVersionDep,
    session: SessionDep,
    actor: ProjectRemover,
) -> None:
    """Withdraw a project and everything belonging to it.

    Records are retained for audit but no longer appear in the product or in the analysis.
    """
    row = get_or_404(session, ProjectTable, project_id, _LABEL)
    require_project_access(session, actor, project_id, write=True)
    ensure_row_version(row, row_version)
    for table in PROJECT_OWNED_AUDIT_TABLES:
        for child in list_rows(session, table, project_id):
            soft_delete(child, actor.email)
            session.add(child)
    memberships = session.exec(
        select(ProjectMemberTable).where(ProjectMemberTable.project_id == project_id)
    ).all()
    for membership in memberships:
        session.delete(membership)
    soft_delete(row, actor.email)
    session.add(row)
    activity_service.record(
        session,
        action="deleted",
        entity_type="Project",
        entity_id=project_id,
        project_id=None,
        summary=f"Deleted project {row.project_name} and its records",
        actor=actor,
    )
    session.commit()


def _user_option(user: UserTable) -> ProjectUserOption:
    return ProjectUserOption(
        user_id=user.id or 0,
        email=user.email,
        full_name=user.full_name,
        workspace_role=user.role,
        role_label=role_label(user.role),
    )


def _selected_manager(session: SessionDep, user_id: int, recorded_name: str | None) -> UserTable:
    """Return the active account chosen to manage a project, or refuse the choice."""
    manager = session.get(UserTable, user_id)
    if (
        manager is None
        or not manager.is_active
        or not has_permission(manager.role, Permission.PROJECT_UPDATE)
    ):
        raise HTTPException(
            status_code=422, detail="Select an active account permitted to manage projects."
        )
    if recorded_name is not None and manager.full_name != recorded_name:
        raise HTTPException(
            status_code=422, detail="Project manager does not match the selected account."
        )
    return manager


@router.get("/{project_id}/people", response_model=list[ProjectUserOption])
def list_record_owners(
    project_id: str,
    session: SessionDep,
    actor: CurrentUser,
    purpose: Literal[
        "risk", "decision", "meeting", "action", "issue", "assumption", "requirement", "gate"
    ],
) -> list[ProjectUserOption]:
    """Offer active project members only to callers who can manage that record type."""
    permission = {
        "risk": Permission.RISK_MANAGE,
        "decision": Permission.CHANGE_CREATE,
        "meeting": Permission.WORK_UPDATE,
        "action": Permission.ACTION_MANAGE,
        "issue": Permission.ISSUE_MANAGE,
        "assumption": Permission.ASSUMPTION_MANAGE,
        "requirement": Permission.REQUIREMENT_MANAGE,
        "gate": Permission.WORK_MANAGE,
    }[purpose]
    if not has_permission(actor.role, permission):
        raise HTTPException(status_code=403, detail="Your role cannot manage this record type.")
    require_project_access(session, actor, project_id, write=True)
    people = session.exec(
        select(UserTable)
        .join(ProjectMemberTable, ProjectMemberTable.user_id == UserTable.id)
        .where(ProjectMemberTable.project_id == project_id, UserTable.is_active.is_(True))
        .order_by(UserTable.full_name, UserTable.email)
    ).all()
    return [_user_option(user) for user in people]


@router.get("/{project_id}/assignees", response_model=list[ProjectUserOption])
def list_task_assignees(
    project_id: str, session: SessionDep, actor: WorkManager
) -> list[ProjectUserOption]:
    """List active project accounts that can update assigned work."""
    require_project_access(session, actor, project_id, write=True)
    statement = (
        select(UserTable)
        .join(ProjectMemberTable, ProjectMemberTable.user_id == UserTable.id)
        .where(ProjectMemberTable.project_id == project_id, UserTable.is_active.is_(True))
        .order_by(UserTable.full_name, UserTable.email)
    )
    return [
        _user_option(user)
        for user in session.exec(statement).all()
        if has_permission(user.role, Permission.WORK_UPDATE)
    ]


@router.get("/{project_id}/member-candidates", response_model=list[ProjectUserOption])
def list_member_candidates(
    project_id: str, session: SessionDep, actor: ProjectMemberManager
) -> list[ProjectUserOption]:
    """List minimal active-account details for authorized membership administration."""
    _require_membership_management(session, actor, project_id)
    member_ids = set(
        session.exec(
            select(ProjectMemberTable.user_id).where(ProjectMemberTable.project_id == project_id)
        ).all()
    )
    users = session.exec(
        select(UserTable)
        .where(UserTable.is_active.is_(True))
        .order_by(UserTable.full_name, UserTable.email)
    ).all()
    return [_user_option(user) for user in users if user.id not in member_ids]


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
def list_project_members(
    project_id: str, session: SessionDep, actor: ProjectMemberManager
) -> list[ProjectMemberOut]:
    """List the active assignments for a project the actor may govern."""
    _require_membership_management(session, actor, project_id)
    statement = select(ProjectMemberTable).where(ProjectMemberTable.project_id == project_id)
    pairs = [
        (membership, session.get(UserTable, membership.user_id))
        for membership in session.exec(statement).all()
    ]
    members = [
        _project_member_out(membership, user) for membership, user in pairs if user is not None
    ]
    return sorted(members, key=lambda member: (member.full_name, member.email))


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberOut,
    status_code=status.HTTP_201_CREATED,
)
def create_project_member(
    project_id: str,
    payload: ProjectMemberCreate,
    session: SessionDep,
    actor: ProjectMemberManager,
) -> ProjectMemberOut:
    """Assign an active workspace account to a governed project."""
    _require_membership_management(session, actor, project_id)
    from api.services import user_service

    user = (
        session.get(UserTable, payload.user_id)
        if payload.user_id is not None
        else user_service.find_by_email(session, str(payload.user_email))
    )
    if user is None or user.id is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That active user was not found.",
        )
    if _find_membership(session, project_id, user.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That user is already assigned to this project.",
        )

    membership = ProjectMemberTable(
        project_id=project_id,
        user_id=user.id,
        project_role=payload.project_role,
    )
    session.add(membership)
    activity_service.record(
        session,
        action="assigned",
        entity_type="Project member",
        entity_id=user.email,
        project_id=project_id,
        summary=f"Assigned {user.full_name} as {payload.project_role}",
        actor=actor,
    )
    session.commit()
    session.refresh(membership)
    return _project_member_out(membership, user)


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberOut)
def update_project_member(
    project_id: str,
    user_id: int,
    payload: ProjectMemberUpdate,
    session: SessionDep,
    actor: ProjectMemberManager,
) -> ProjectMemberOut:
    """Change a governed assignment's descriptive project role."""
    _require_membership_management(session, actor, project_id)
    membership = _find_membership(session, project_id, user_id)
    user = session.get(UserTable, user_id)
    if membership is None or user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That project member was not found.",
        )

    previous_role = membership.project_role
    membership.project_role = payload.project_role
    session.add(membership)
    activity_service.record(
        session,
        action="updated",
        entity_type="Project member",
        entity_id=user.email,
        project_id=project_id,
        summary=(
            f"Changed {user.full_name}'s project role from {previous_role} "
            f"to {payload.project_role}"
        ),
        actor=actor,
    )
    session.commit()
    session.refresh(membership)
    return _project_member_out(membership, user)


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_member(
    project_id: str,
    user_id: int,
    session: SessionDep,
    actor: ProjectMemberManager,
) -> None:
    """Revoke a user's assignment to a governed project."""
    _require_membership_management(session, actor, project_id)
    membership = _find_membership(session, project_id, user_id)
    user = session.get(UserTable, user_id)
    if membership is None or user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That project member was not found.",
        )

    open_task_ids = [
        task.task_id
        for task in list_rows(session, TaskTable, project_id)
        if task.owner_user_id == user_id and not is_terminal_schedule_status(task.status)
    ]
    open_task_ids += [
        action.action_id
        for action in list_rows(session, ActionTable, project_id)
        if action.owner_user_id == user_id and action.status not in {"Complete", "Cancelled"}
    ]
    if open_task_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reassign or complete this member's open work before removing access: {', '.join(open_task_ids)}.",
        )
    session.delete(membership)
    activity_service.record(
        session,
        action="unassigned",
        entity_type="Project member",
        entity_id=user.email,
        project_id=project_id,
        summary=f"Removed {user.full_name} from the project",
        actor=actor,
    )
    session.commit()


def _require_membership_management(
    session: SessionDep, actor: ProjectMemberManager, project_id: str
) -> None:
    get_or_404(session, ProjectTable, project_id, _LABEL)
    require_project_access(session, actor, project_id, write=True)


def _find_membership(
    session: SessionDep, project_id: str, user_id: int
) -> ProjectMemberTable | None:
    statement = select(ProjectMemberTable).where(
        ProjectMemberTable.project_id == project_id,
        ProjectMemberTable.user_id == user_id,
    )
    return session.exec(statement).first()


def _project_member_out(membership: ProjectMemberTable, user: UserTable) -> ProjectMemberOut:
    return ProjectMemberOut(
        user_id=user.id or 0,
        email=user.email,
        full_name=user.full_name,
        workspace_role=user.role,
        project_role=membership.project_role,
        is_active=user.is_active,
        created_at=membership.created_at,
    )


# ------------------------------------------------------------------ child collections
@router.get("/{project_id}/work-packages", response_model=list[WorkPackageOut])
def list_project_work_packages(
    project_id: str, session: SessionDep, actor: CurrentUser
) -> list[WorkPackageOut]:
    """List a project's Work Packages."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, WorkPackageTable, project_id)
    return [WorkPackageOut.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{project_id}/deliverables", response_model=list[DeliverableOut])
def list_project_deliverables(
    project_id: str, session: SessionDep, actor: CurrentUser
) -> list[DeliverableOut]:
    """List a project's Deliverables."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, DeliverableTable, project_id)
    return [DeliverableOut.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{project_id}/milestones", response_model=list[MilestoneOut])
def list_project_milestones(
    project_id: str, session: SessionDep, actor: CurrentUser
) -> list[MilestoneOut]:
    """List a project's milestones."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, MilestoneTable, project_id)
    return [milestone_out(to_entity(row, DeliveryMilestone), row.row_version) for row in rows]


@router.get("/{project_id}/gates", response_model=list[GateOut])
def list_project_gates(project_id: str, session: SessionDep, actor: CurrentUser) -> list[GateOut]:
    """List a project's governed Gates in lifecycle order."""
    _require_project_read(session, actor, project_id)
    rows = sorted(list_rows(session, GateTable, project_id), key=lambda row: row.sequence)
    return [gate_out(row) for row in rows]


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
def list_project_tasks(project_id: str, session: SessionDep, actor: CurrentUser) -> list[TaskOut]:
    """List a project's tasks."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, TaskTable, project_id)
    return [task_row_out(row) for row in rows]


@router.get("/{project_id}/risks", response_model=list[RiskOut])
def list_project_risks(project_id: str, session: SessionDep, actor: CurrentUser) -> list[RiskOut]:
    """List a project's risks."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, RiskTable, project_id)
    return [risk_row_out(row) for row in rows]


@router.get("/{project_id}/actions", response_model=list[ActionOut])
def list_project_actions(
    project_id: str, session: SessionDep, actor: CurrentUser
) -> list[ActionOut]:
    """List a project's actions."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, ActionTable, project_id)
    return [action_row_out(row) for row in rows]


@router.get("/{project_id}/requirements", response_model=list[RequirementOut])
def list_project_requirements(
    project_id: str, session: SessionDep, actor: CurrentUser
) -> list[RequirementOut]:
    """List a project's requirements."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, RequirementTable, project_id)
    return [requirement_out(to_entity(row, Requirement), row.row_version) for row in rows]


@router.get("/{project_id}/test-cases", response_model=list[TestCaseOut])
def list_project_test_cases(
    project_id: str, session: SessionDep, actor: CurrentUser
) -> list[TestCaseOut]:
    """List a project's test cases."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, TestCaseTable, project_id)
    return [
        test_case_out(to_entity(row, TestCase)).model_copy(update={"row_version": row.row_version})
        for row in rows
    ]


@router.get("/{project_id}/dependencies", response_model=list[DependencyOut])
def list_project_dependencies(
    project_id: str, session: SessionDep, actor: CurrentUser
) -> list[DependencyOut]:
    """List a project's dependencies."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, DependencyTable, project_id)
    return [dependency_out(to_entity(row, GovernedDependency), row.row_version) for row in rows]


@router.get("/{project_id}/resources", response_model=list[ResourceOut])
def list_project_resources(
    project_id: str, session: SessionDep, actor: CurrentUser
) -> list[ResourceOut]:
    """List a project's weekly resource allocations."""
    _require_project_read(session, actor, project_id)
    rows = list_rows(session, ResourceTable, project_id)
    return [resource_out(to_entity(row, Resource), row.row_version) for row in rows]


@router.get("/{project_id}/delta", response_model=ProjectDelta)
def get_project_delta(
    project_id: str,
    session: SessionDep,
    actor: CurrentUser,
    days: int = Query(default=7, ge=1, le=365),
) -> ProjectDelta:
    """Answer "what changed since last review?" for one project.

    The window is expressed in days back from now. Nothing is calculated here: the response is a
    reading of the audit columns and the activity trail the records already carry.
    """
    _require_project_read(session, actor, project_id)
    since = datetime.now(UTC) - timedelta(days=days)
    return delta_service.build(session, project_id, since)
