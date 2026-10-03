"""Schema upgrades run through the application, so no database console is needed after setup."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from api import settings
from api.database import (
    current_schema_revision,
    database_region,
    expected_schema_revision,
    get_session,
    reset_engine,
    set_engine,
    upgrade_db,
)
from api.main import create_app
from api.models import ActivityEventTable, UserTable
from api.security.permissions import Role
from tests.api.conftest import TEST_ACCOUNTS, TEST_PASSWORD, url

PREVIOUS_REVISION = "20260925_0017"


def _memory_engine(revision: str | None) -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    if revision is not None:
        upgrade_db(engine, revision)
    return engine


def _revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return current_schema_revision(connection)


def _revision_after_first_session(engine: Engine) -> str | None:
    """Open one request session, then report the revision before the memory database closes."""
    set_engine(engine)
    try:
        sessions = get_session()
        next(sessions)
        sessions.close()
        return _revision(engine)
    finally:
        reset_engine()


@pytest.fixture
def automatic_upgrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(settings.SCHEMA_AUTO_UPGRADE_ENV_VAR, raising=False)


def test_a_database_behind_the_release_is_upgraded_on_first_use(automatic_upgrades) -> None:
    engine = _memory_engine(PREVIOUS_REVISION)
    assert _revision_after_first_session(engine) == expected_schema_revision()


def test_automatic_upgrades_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(settings.SCHEMA_AUTO_UPGRADE_ENV_VAR, "false")
    engine = _memory_engine(PREVIOUS_REVISION)
    assert _revision_after_first_session(engine) == PREVIOUS_REVISION


def test_an_unversioned_database_is_never_initialised_automatically(automatic_upgrades) -> None:
    engine = _memory_engine(None)
    assert _revision_after_first_session(engine) is None


def test_the_database_region_is_read_from_a_managed_host_only() -> None:
    hosted = make_url(
        "postgresql+psycopg://reader:placeholder@ep-quiet-lake-123456-pooler"
        ".eu-central-1.aws.neon.tech/epos"
    )
    assert database_region(hosted) == "eu-central-1"
    assert database_region(make_url("sqlite://")) is None


@pytest.fixture
def behind_release(monkeypatch: pytest.MonkeyPatch, test_password_hash: str) -> Iterator[Engine]:
    """A signed-in administrator's database one governed migration behind this release."""
    monkeypatch.setenv(settings.SCHEMA_AUTO_UPGRADE_ENV_VAR, "false")
    monkeypatch.setenv(settings.STARTUP_MIGRATION_ENV_VAR, "false")
    engine = _memory_engine(PREVIOUS_REVISION)
    set_engine(engine)
    with Session(engine) as session:
        for role in (Role.ADMINISTRATOR, Role.PROJECT_MANAGER):
            email, full_name = TEST_ACCOUNTS[role]
            session.add(
                UserTable(
                    email=email, full_name=full_name, password_hash=test_password_hash, role=role
                )
            )
        session.commit()
    yield engine
    reset_engine()


def _signed_in(role: Role) -> TestClient:
    with TestClient(create_app()) as anonymous:
        response = anonymous.post(
            url("/auth/login"),
            json={"email": TEST_ACCOUNTS[role][0], "password": TEST_PASSWORD},
        )
        assert response.status_code == 200, response.text
    client = TestClient(create_app())
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


def test_an_administrator_sees_the_pending_upgrade_and_applies_it(behind_release: Engine) -> None:
    admin = _signed_in(Role.ADMINISTRATOR)

    status = admin.get(url("/admin/database")).json()
    assert status["current_revision"] == PREVIOUS_REVISION
    assert status["is_current"] is False
    assert status["can_upgrade"] is True
    assert [step["revision"] for step in status["pending"]] == [expected_schema_revision()]
    assert status["round_trip_ms"] is not None

    applied = admin.post(url("/admin/database/upgrade"))
    assert applied.status_code == 200, applied.text
    assert applied.json()["is_current"] is True
    assert applied.json()["pending"] == []
    assert _revision(behind_release) == expected_schema_revision()
    with Session(behind_release) as session:
        event = session.exec(
            select(ActivityEventTable).where(ActivityEventTable.entity_type == "Database")
        ).one()
    assert PREVIOUS_REVISION in event.summary
    assert event.actor_email == TEST_ACCOUNTS[Role.ADMINISTRATOR][0]


def test_only_an_administrator_may_read_or_upgrade_the_database(behind_release: Engine) -> None:
    manager = _signed_in(Role.PROJECT_MANAGER)
    assert manager.get(url("/admin/database")).status_code == 403
    assert manager.post(url("/admin/database/upgrade")).status_code == 403
    assert _revision(behind_release) == PREVIOUS_REVISION


def test_a_current_database_reports_nothing_to_do(client: TestClient) -> None:
    status = client.get(url("/admin/database")).json()
    assert status["is_current"] is True
    assert status["can_upgrade"] is False
    assert status["dialect"] == "sqlite"
    response = client.post(url("/admin/database/upgrade"))
    assert response.status_code == 200
    assert response.json()["current_revision"] == expected_schema_revision()
