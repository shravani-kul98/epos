"""Roles and permissions for EPOS.

Authorisation is permission-based. Routes declare the permission they need; this module is the
single place where roles are mapped to permissions, so the whole security model is reviewable at
once. See ``docs/epos-next-security.md``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Role(StrEnum):
    """A user's role. Stored as its string value."""

    EXECUTIVE = "executive"
    ENGINEER = "engineer"
    ENGINEERING_LEAD = "engineering_lead"
    REQUIREMENTS_MANAGER = "requirements_manager"
    PROJECT_MANAGER = "project_manager"
    PMO_ANALYST = "pmo_analyst"
    ADMINISTRATOR = "administrator"


class Permission(StrEnum):
    """A single authorised capability."""

    PORTFOLIO_READ = "portfolio.read"
    PROJECT_CREATE = "project.create"
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"
    PROJECT_MEMBERS_MANAGE = "project_members.manage"
    WORK_UPDATE = "work.update"
    WORK_MANAGE = "work.manage"
    ACTION_MANAGE = "action.manage"
    RISK_MANAGE = "risk.manage"
    ISSUE_MANAGE = "issue.manage"
    ASSUMPTION_MANAGE = "assumption.manage"
    REQUIREMENT_MANAGE = "requirement.manage"
    CHANGE_CREATE = "change.create"
    CHANGE_DECIDE = "change.decide"
    SCENARIO_RUN = "scenario.run"
    REPORT_READ = "report.read"
    COPILOT_ASK = "copilot.ask"
    USER_MANAGE = "user.manage"
    WORKSPACE_ADMIN = "workspace.admin"


# The role a self-registered account receives. Never configurable by the client.
DEFAULT_ROLE: Final[Role] = Role.ENGINEER

_BASE: Final[frozenset[Permission]] = frozenset({Permission.PORTFOLIO_READ, Permission.COPILOT_ASK})

ROLE_PERMISSIONS: Final[dict[Role, frozenset[Permission]]] = {
    Role.EXECUTIVE: _BASE | {Permission.REPORT_READ},
    Role.ENGINEER: _BASE | {Permission.WORK_UPDATE},
    Role.ENGINEERING_LEAD: _BASE
    | {
        Permission.WORK_UPDATE,
        Permission.WORK_MANAGE,
        Permission.ACTION_MANAGE,
        Permission.RISK_MANAGE,
        Permission.ISSUE_MANAGE,
        Permission.ASSUMPTION_MANAGE,
        Permission.SCENARIO_RUN,
        Permission.REPORT_READ,
    },
    Role.REQUIREMENTS_MANAGER: _BASE
    | {
        Permission.ASSUMPTION_MANAGE,
        Permission.REQUIREMENT_MANAGE,
        Permission.CHANGE_CREATE,
        Permission.SCENARIO_RUN,
        Permission.REPORT_READ,
    },
    Role.PROJECT_MANAGER: _BASE
    | {
        Permission.PROJECT_CREATE,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_MEMBERS_MANAGE,
        Permission.WORK_UPDATE,
        Permission.WORK_MANAGE,
        Permission.ACTION_MANAGE,
        Permission.RISK_MANAGE,
        Permission.ISSUE_MANAGE,
        Permission.ASSUMPTION_MANAGE,
        Permission.REQUIREMENT_MANAGE,
        Permission.CHANGE_CREATE,
        Permission.CHANGE_DECIDE,
        Permission.SCENARIO_RUN,
        Permission.REPORT_READ,
    },
    Role.PMO_ANALYST: _BASE
    | {
        Permission.PROJECT_CREATE,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_MEMBERS_MANAGE,
        Permission.WORK_UPDATE,
        Permission.WORK_MANAGE,
        Permission.ACTION_MANAGE,
        Permission.RISK_MANAGE,
        Permission.ISSUE_MANAGE,
        Permission.ASSUMPTION_MANAGE,
        Permission.REQUIREMENT_MANAGE,
        Permission.CHANGE_CREATE,
        Permission.CHANGE_DECIDE,
        Permission.SCENARIO_RUN,
        Permission.REPORT_READ,
    },
    Role.ADMINISTRATOR: frozenset(Permission),
}

ROLE_LABELS: Final[dict[Role, str]] = {
    Role.EXECUTIVE: "Executive",
    Role.ENGINEER: "Engineer",
    Role.ENGINEERING_LEAD: "Engineering Lead",
    Role.REQUIREMENTS_MANAGER: "Requirements Manager",
    Role.PROJECT_MANAGER: "Project Manager",
    Role.PMO_ANALYST: "PMO Analyst",
    Role.ADMINISTRATOR: "Administrator",
}

# What each permission lets a person do, in the words the interface uses.
PERMISSION_DESCRIPTIONS: Final[dict[Permission, str]] = {
    Permission.PORTFOLIO_READ: "see the projects you have access to",
    Permission.PROJECT_CREATE: "create projects",
    Permission.PROJECT_UPDATE: "edit project details",
    Permission.PROJECT_DELETE: "remove projects",
    Permission.PROJECT_MEMBERS_MANAGE: "add and remove project members",
    Permission.WORK_UPDATE: "update tasks assigned to you",
    Permission.WORK_MANAGE: "plan milestones and tasks and assign work",
    Permission.ACTION_MANAGE: "create and manage actions",
    Permission.RISK_MANAGE: "create and manage risks",
    Permission.ISSUE_MANAGE: "raise and manage issues",
    Permission.ASSUMPTION_MANAGE: "record and manage assumptions",
    Permission.REQUIREMENT_MANAGE: "manage requirements, tests and trace links",
    Permission.CHANGE_CREATE: "raise change requests",
    Permission.CHANGE_DECIDE: "decide change requests and proposed decisions",
    Permission.SCENARIO_RUN: "run what-if scenarios",
    Permission.REPORT_READ: "read the executive report",
    Permission.COPILOT_ASK: "use Ask EPOS",
    Permission.USER_MANAGE: "manage accounts, roles and invitations",
    Permission.WORKSPACE_ADMIN: "run workspace maintenance",
}


def permissions_for(role: Role) -> frozenset[Permission]:
    """Return every permission granted to ``role``."""
    return ROLE_PERMISSIONS[role]


def has_permission(role: Role, permission: Permission) -> bool:
    """True when ``role`` grants ``permission``."""
    return permission in ROLE_PERMISSIONS[role]


def role_label(role: Role) -> str:
    """Return the display name for a role."""
    return ROLE_LABELS[role]
