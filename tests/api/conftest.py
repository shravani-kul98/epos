"""Shared fixtures for the EPOS API tests.

Every test runs against an isolated, freshly created in-memory database. The application engine is
replaced for the duration of each test, so no test can touch the real database file.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from api.database import init_db, reset_engine, set_engine
from api.main import API_PREFIX, create_app
from api.models import ProjectMemberTable, UserTable
from api.security.permissions import Role
from api.security.tokens import hash_password
from api.seed import seed_session
from src.config import AzureOpenAISettings
from src.data_loader import PortfolioData, load_portfolio
from src.ui_formatting import ANALYSIS_DATE

ANALYSIS_DATE_ISO = ANALYSIS_DATE.isoformat()

# Test-only credential. Never used outside the in-memory database created per test.
TEST_PASSWORD = "test-password-8241"

TEST_ACCOUNTS: dict[Role, tuple[str, str]] = {
    Role.EXECUTIVE: ("exec@test.example.com", "Test Executive"),
    Role.ENGINEER: ("engineer@test.example.com", "Test Engineer"),
    Role.ENGINEERING_LEAD: ("lead@test.example.com", "Test Lead"),
    Role.REQUIREMENTS_MANAGER: ("requirements@test.example.com", "Test Requirements Manager"),
    Role.PROJECT_MANAGER: ("pm@test.example.com", "Test Project Manager"),
    Role.PMO_ANALYST: ("pmo@test.example.com", "Test PMO Analyst"),
    Role.ADMINISTRATOR: ("admin@test.example.com", "Test Administrator"),
}


@pytest.fixture(autouse=True)
def deterministic_api_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep seeded engine expectations reproducible while production uses the UTC clock."""
    monkeypatch.setattr("api.clock.utc_today", lambda: ANALYSIS_DATE)


@pytest.fixture(autouse=True)
def no_live_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    """API tests use injected transports and never the workstation's Azure configuration."""
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key=None, endpoint=None),
    )


@pytest.fixture(scope="session")
def csv_portfolio() -> PortfolioData:
    """The starter workspace data, loaded once for the whole test session."""
    return load_portfolio()


@pytest.fixture
def engine() -> Iterator[Engine]:
    """An isolated in-memory database installed as the application engine."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    set_engine(test_engine)
    init_db(test_engine)
    yield test_engine
    reset_engine()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session bound to the isolated engine."""
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture(scope="session")
def test_password_hash() -> str:
    """Hash the shared test password once.

    Argon2 is deliberately slow. Hashing it per test would dominate the suite's runtime without
    testing anything extra: hashing and registration are covered directly in the auth tests, and
    signing in still performs a real Argon2 verification.
    """
    return hash_password(TEST_PASSWORD)


@pytest.fixture
def users(engine: Engine, test_password_hash: str) -> dict[Role, str]:
    """One account per role. Returns the email address for each."""
    with Session(engine) as db_session:
        for role, (email, full_name) in TEST_ACCOUNTS.items():
            db_session.add(
                UserTable(
                    email=email,
                    full_name=full_name,
                    password_hash=test_password_hash,
                    role=role,
                )
            )
        db_session.commit()
    return {role: email for role, (email, _) in TEST_ACCOUNTS.items()}


@pytest.fixture
def seeded_engine(engine: Engine, csv_portfolio: PortfolioData, users: dict[Role, str]) -> Engine:
    """The isolated engine, loaded with the starter workspace."""
    with Session(engine) as db_session:
        seed_session(db_session, csv_portfolio)
        assignments = {
            Role.ENGINEER: ("P-002",),
            Role.ENGINEERING_LEAD: ("P-002", "P-007"),
            Role.REQUIREMENTS_MANAGER: ("P-002",),
            Role.PROJECT_MANAGER: ("P-002", "P-007"),
        }
        for role, project_ids in assignments.items():
            user = db_session.exec(select(UserTable).where(UserTable.email == users[role])).one()
            for project_id in project_ids:
                db_session.add(ProjectMemberTable(project_id=project_id, user_id=user.id or 0))
        db_session.commit()
    return engine


@pytest.fixture
def anonymous_client(seeded_engine: Engine, users: dict[Role, str]) -> Iterator[TestClient]:
    """A client with no credentials."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def sign_in(anonymous_client: TestClient) -> Callable[[Role], TestClient]:
    """Return a factory that produces a client signed in as a given role."""

    def factory(role: Role) -> TestClient:
        email = TEST_ACCOUNTS[role][0]
        response = anonymous_client.post(
            url("/auth/login"), json={"email": email, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        client = TestClient(create_app())
        client.headers["Authorization"] = f"Bearer {token}"
        return client

    return factory


@pytest.fixture
def client(sign_in: Callable[[Role], TestClient]) -> TestClient:
    """A client signed in as an administrator, for tests not about authorisation."""
    return sign_in(Role.ADMINISTRATOR)


@pytest.fixture
def pm_client(sign_in: Callable[[Role], TestClient]) -> TestClient:
    """A client signed in as a project manager."""
    return sign_in(Role.PROJECT_MANAGER)


@pytest.fixture
def executive_client(sign_in: Callable[[Role], TestClient]) -> TestClient:
    """A client signed in as an executive, who may read but not change anything."""
    return sign_in(Role.EXECUTIVE)


@pytest.fixture
def engineer_client(sign_in: Callable[[Role], TestClient]) -> TestClient:
    """A client signed in as an engineer."""
    return sign_in(Role.ENGINEER)


@pytest.fixture
def requirements_client(sign_in: Callable[[Role], TestClient]) -> TestClient:
    """A client signed in as a requirements manager."""
    return sign_in(Role.REQUIREMENTS_MANAGER)


@pytest.fixture
def empty_client(engine: Engine, users: dict[Role, str]) -> Iterator[TestClient]:
    """An administrator client backed by a workspace with no project data."""
    with TestClient(create_app()) as anonymous:
        response = anonymous.post(
            url("/auth/login"),
            json={"email": TEST_ACCOUNTS[Role.ADMINISTRATOR][0], "password": TEST_PASSWORD},
        )
        token = response.json()["access_token"]
    authenticated = TestClient(create_app())
    authenticated.headers["Authorization"] = f"Bearer {token}"
    with authenticated as test_client:
        yield test_client


def url(path: str) -> str:
    """Prefix a path with the API version root."""
    return f"{API_PREFIX}{path}"
