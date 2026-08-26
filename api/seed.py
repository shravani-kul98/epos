"""Seed the EPOS Next database from the existing validated synthetic CSV dataset.

Reusing :func:`src.data_loader.load_portfolio` means seeded data passes exactly the same schema
and referential-integrity validation the deterministic engines were built against.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, select

from api import models
from api.database import get_engine, init_db
from api.security.permissions import Role
from api.services import user_service
from src.data_loader import PortfolioData, load_portfolio

# Each portfolio collection paired with the table it seeds.
_SEED_PLAN: tuple[tuple[str, type[SQLModel]], ...] = (
    ("projects", models.ProjectTable),
    ("milestones", models.MilestoneTable),
    ("tasks", models.TaskTable),
    ("risks", models.RiskTable),
    ("dependencies", models.DependencyTable),
    ("actions", models.ActionTable),
    ("resources", models.ResourceTable),
    ("requirements", models.RequirementTable),
    ("test_cases", models.TestCaseTable),
    ("trace_links", models.TraceLinkTable),
    ("change_requests", models.ChangeRequestTable),
)


def _to_row(entity: BaseModel, table: type[SQLModel]) -> SQLModel:
    """Convert a validated entity model into its table row."""
    return table(**entity.model_dump())


def is_seeded(session: Session) -> bool:
    """True when the database already contains at least one project."""
    return session.exec(select(models.ProjectTable).limit(1)).first() is not None


def seed_session(session: Session, portfolio: PortfolioData) -> dict[str, int]:
    """Insert every portfolio record into ``session``. Returns rows written per table."""
    written: dict[str, int] = {}
    for attribute, table in _SEED_PLAN:
        entities: list[BaseModel] = getattr(portfolio, attribute)
        for entity in entities:
            session.add(_to_row(entity, table))
        session.flush()
        written[attribute] = len(entities)
    session.commit()
    return written


def seed_database(
    engine: Engine | None = None,
    data_dir: Path | str | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Create tables and load the starter workspace.

    Idempotent by default: an already-seeded database is left untouched and ``{}`` is returned.
    Pass ``force=True`` to clear and reload.
    """
    target = engine or get_engine()
    init_db(target)
    portfolio = load_portfolio(data_dir)

    with Session(target) as session:
        if is_seeded(session):
            if not force:
                return {}
            _clear(session)
        return seed_session(session, portfolio)


# Development accounts, one per role. The password is generated at seed time and printed once,
# so no usable credential is ever committed to the repository.
DEV_ACCOUNTS: tuple[tuple[str, str, Role, str], ...] = (
    ("ceo@epos.example.com", "Morgan Hale", Role.EXECUTIVE, "Chief Executive"),
    ("pmo@epos.example.com", "Rowan Patel", Role.PMO_ANALYST, "PMO Analyst"),
    ("pm@epos.example.com", "Alex Whitfield", Role.PROJECT_MANAGER, "Project Manager"),
    ("lead@epos.example.com", "Dana Okoro", Role.ENGINEERING_LEAD, "Engineering Lead"),
    ("engineer@epos.example.com", "Sam Ellery", Role.ENGINEER, "Systems Engineer"),
    (
        "requirements@epos.example.com",
        "Jules Marchetti",
        Role.REQUIREMENTS_MANAGER,
        "Requirements Manager",
    ),
    ("admin@epos.example.com", "Casey Lindqvist", Role.ADMINISTRATOR, "Workspace Administrator"),
)


def seed_users(session: Session, password: str) -> list[str]:
    """Create one development account per role. Returns the addresses created."""
    created: list[str] = []
    for email, full_name, role, job_title in DEV_ACCOUNTS:
        if user_service.find_by_email(session, email) is not None:
            continue
        user_service.register(
            session,
            email=email,
            full_name=full_name,
            password=password,
            job_title=job_title,
            role=role,
        )
        created.append(email)
    return created


def generate_dev_password() -> str:
    """Generate a random development password.

    Never a fixed default: an unattended seed must not create accounts whose password is
    discoverable by reading this repository.
    """
    return f"Epos-{secrets.token_urlsafe(12)}"


def _clear(session: Session) -> None:
    """Delete all seeded rows, children before parents."""
    events = session.exec(select(models.ActivityEventTable)).all()
    if events:
        event_ids = ", ".join(str(row.id) for row in events)
        raise RuntimeError(
            "Force reseeding is refused because immutable Activity Events exist: " f"{event_ids}."
        )
    reviews = session.exec(select(models.GateReviewTable)).all()
    if reviews:
        review_ids = ", ".join(sorted(row.review_id for row in reviews))
        raise RuntimeError(
            "Force reseeding is refused because immutable Gate Reviews exist: " f"{review_ids}."
        )
    for table in (
        models.ProjectMemberTable,
        models.DecisionTable,
        models.MeetingNoteTable,
        models.IssueTable,
        models.AssumptionTable,
    ):
        for row in session.exec(select(table)).all():
            session.delete(row)
    project_children = [
        table for _, table in reversed(_SEED_PLAN) if table is not models.ProjectTable
    ]
    for table in (
        *project_children,
        models.DeliverableTable,
        models.WorkPackageTable,
        models.GateCriterionTable,
        models.GateTable,
        models.ProjectTable,
    ):
        for row in session.exec(select(table)).all():
            session.delete(row)
    session.commit()


def main() -> None:
    """Command-line entry point: ``python -m api.seed``."""
    written = seed_database()
    if written:
        for name, count in written.items():
            print(f"{name}: {count}")
    else:
        print("Workspace data already present; no changes made.")

    password = generate_dev_password()
    with Session(get_engine()) as session:
        created = seed_users(session, password)

    if created:
        print("\nDevelopment accounts created:")
        for email in created:
            print(f"  {email}")
        print(f"\nPassword for all of the above: {password}")
        print("Shown once. Change it after first sign-in.")
    else:
        print("\nDevelopment accounts already present; passwords unchanged.")


if __name__ == "__main__":
    main()
