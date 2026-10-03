"""Shared pytest fixtures. Tests never make network/API calls and need no Azure key."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config
from src.data_loader import PortfolioData, load_portfolio
from src.schemas import (
    Action,
    ChangeRequest,
    Dependency,
    Milestone,
    Project,
    Requirement,
    Resource,
    Risk,
    Task,
    TestCase,
    TraceLink,
)

# Fixed reference date for all deterministic tests unless a boundary test needs another.
AS_OF = date(2026, 8, 25)

APP_PATH = str(config.PROJECT_ROOT / "app.py")

# Settings the application reads from the environment. A developer's shell or .env file must not
# change what a test observes, so every test starts without them and sets only what it needs.
_APPLICATION_ENVIRONMENT = (
    "API_KEY",
    "ENDPOINT",
    "DATABASE_URL",
    "EPOS_DATABASE_URL",
    "EPOS_ALEMBIC_DATABASE_URL",
    "ENVIRONMENT",
    "JWT_SECRET",
    "EPOS_SECRET_KEY",
    "EPOS_ALLOWED_ORIGINS",
    "EPOS_ENABLE_API_DOCS",
    "EPOS_RUN_MIGRATIONS_ON_STARTUP",
    "EPOS_RATE_LIMITS",
    "EPOS_SELF_REGISTRATION",
    "EPOS_REGISTRATION_EMAIL_DOMAINS",
    "EPOS_ASSISTANT_MODE",
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test without the deployment settings of the machine running it."""
    for name in _APPLICATION_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


PAGE_DASHBOARD = "pages/1_Portfolio_Dashboard.py"
PAGE_PROJECT_INTELLIGENCE = "pages/2_Project_Intelligence.py"
PAGE_TRACEABILITY = "pages/3_Requirements_Traceability.py"
PAGE_CHANGE_IMPACT = "pages/4_Change_Impact.py"
PAGE_SCENARIO = "pages/5_Scenario_Planner.py"
PAGE_ASK_EPOS = "pages/6_Ask_EPOS.py"


def rendered_text(app: AppTest) -> str:
    """Concatenate the app's text-bearing elements for verbatim content assertions."""
    parts: list[str] = []
    for collection in (app.markdown, app.caption, app.info, app.warning, app.error, app.success):
        parts.extend(element.value for element in collection)
    return "\n".join(parts)


def frame_named(app: AppTest, *columns: str):
    """Return the first rendered dataframe containing all the given column names."""
    for element in app.dataframe:
        frame = element.value
        if all(column in frame.columns for column in columns):
            return frame
    raise AssertionError(f"no rendered dataframe has columns {columns}")


@pytest.fixture
def open_page() -> Callable[..., AppTest]:
    """Open the app, switch to a page, apply session state, and run it."""

    def _open(page_path: str, **session_state: object) -> AppTest:
        app = AppTest.from_file(APP_PATH, default_timeout=120)
        app.run()
        app.switch_page(page_path)
        for key, value in session_state.items():
            app.session_state[key] = value
        app.run()
        return app

    return _open


@pytest.fixture
def as_of_date() -> date:
    """The fixed calculation reference date used across deterministic tests."""
    return AS_OF


@pytest.fixture
def real_data_dir() -> Path:
    """Path to the repository's synthetic CSV data."""
    return config.DATA_DIR


@pytest.fixture
def portfolio() -> PortfolioData:
    """The validated portfolio loaded from the real synthetic data."""
    return load_portfolio()


@pytest.fixture
def temp_data_dir(tmp_path: Path, real_data_dir: Path) -> Path:
    """A writable copy of the synthetic data so tests can corrupt files safely."""
    destination = tmp_path / "data"
    shutil.copytree(real_data_dir, destination)
    return destination


# --------------------------------------------------------------------------- builders
# Builder fixtures return callables that produce healthy-by-default entities. Tests override
# only the fields relevant to the scenario under test.

TEST_PROJECT_ID = "P-TEST"


@pytest.fixture
def make_project() -> Callable[..., Project]:
    def _make(**overrides: object) -> Project:
        defaults: dict[str, object] = {
            "project_id": TEST_PROJECT_ID,
            "project_name": "Test Project",
            "domain": "Engineering",
            "project_manager": "Pat Owner",
            "start_date": date(2025, 1, 1),
            "baseline_end_date": date(2026, 12, 31),
            "forecast_end_date": date(2026, 12, 31),
            "status_update_date": date(2026, 8, 20),
            "project_phase": "Execution",
            "business_priority": "High",
        }
        defaults.update(overrides)
        return Project.model_validate(defaults)

    return _make


@pytest.fixture
def make_milestone() -> Callable[..., Milestone]:
    def _make(**overrides: object) -> Milestone:
        defaults: dict[str, object] = {
            "milestone_id": "M1",
            "project_id": TEST_PROJECT_ID,
            "milestone_name": "Test Milestone",
            "baseline_date": date(2026, 12, 1),
            "forecast_date": date(2026, 12, 1),
            "status": "On Track",
            "criticality": "Medium",
            "owner": "Pat Owner",
        }
        defaults.update(overrides)
        return Milestone.model_validate(defaults)

    return _make


@pytest.fixture
def make_task() -> Callable[..., Task]:
    def _make(**overrides: object) -> Task:
        defaults: dict[str, object] = {
            "task_id": "T1",
            "project_id": TEST_PROJECT_ID,
            "milestone_id": "M1",
            "task_name": "Test Task",
            "owner": "Pat Owner",
            "status": "In Progress",
            "planned_end_date": date(2026, 12, 1),
            "forecast_end_date": date(2026, 12, 1),
            "completion_percent": 80,
            "is_blocked": False,
            "last_updated_date": date(2026, 8, 20),
        }
        defaults.update(overrides)
        return Task.model_validate(defaults)

    return _make


@pytest.fixture
def make_risk() -> Callable[..., Risk]:
    def _make(**overrides: object) -> Risk:
        defaults: dict[str, object] = {
            "risk_id": "R1",
            "project_id": TEST_PROJECT_ID,
            "risk_name": "Test Risk",
            "probability": 1,
            "impact": 1,
            "status": "Open",
            "mitigation_owner": "Pat Owner",
            "mitigation_status": "In Progress",
            "due_date": date(2026, 12, 31),
        }
        defaults.update(overrides)
        return Risk.model_validate(defaults)

    return _make


@pytest.fixture
def make_dependency() -> Callable[..., Dependency]:
    def _make(**overrides: object) -> Dependency:
        defaults: dict[str, object] = {
            "dependency_id": "D1",
            "project_id": TEST_PROJECT_ID,
            "predecessor_type": "Task",
            "predecessor_id": "T1",
            "successor_type": "Milestone",
            "successor_id": "M1",
            "dependency_name": "Test Dependency",
            "status": "On Track",
            "delay_days": 0,
            "criticality": "Medium",
        }
        defaults.update(overrides)
        return Dependency.model_validate(defaults)

    return _make


@pytest.fixture
def make_resource() -> Callable[..., Resource]:
    def _make(**overrides: object) -> Resource:
        defaults: dict[str, object] = {
            "resource_id": "RES1",
            "resource_name": "Pat Owner",
            "project_id": TEST_PROJECT_ID,
            "allocated_hours": 32,
            "capacity_hours": 40,
            "week_start_date": date(2026, 8, 24),
        }
        defaults.update(overrides)
        return Resource.model_validate(defaults)

    return _make


@pytest.fixture
def make_action() -> Callable[..., Action]:
    def _make(**overrides: object) -> Action:
        defaults: dict[str, object] = {
            "action_id": "A1",
            "project_id": TEST_PROJECT_ID,
            "action_description": "Test Action",
            "owner": "Pat Owner",
            "due_date": date(2026, 12, 31),
            "status": "Open",
            "priority": "Medium",
            "source_reference": "M1",
        }
        defaults.update(overrides)
        return Action.model_validate(defaults)

    return _make


@pytest.fixture
def make_requirement() -> Callable[..., Requirement]:
    def _make(**overrides: object) -> Requirement:
        defaults: dict[str, object] = {
            "requirement_id": "REQ1",
            "project_id": TEST_PROJECT_ID,
            "requirement_text": "The system shall do something verifiable.",
            "requirement_type": "Functional",
            "priority": "High",
            "status": "Approved",
            "owner": "Pat Owner",
            "last_updated_date": date(2026, 8, 20),
        }
        defaults.update(overrides)
        return Requirement.model_validate(defaults)

    return _make


@pytest.fixture
def make_test_case() -> Callable[..., TestCase]:
    def _make(**overrides: object) -> TestCase:
        defaults: dict[str, object] = {
            "test_case_id": "TC1",
            "project_id": TEST_PROJECT_ID,
            "test_case_name": "Verify something",
            "status": "Passed",
            "owner": "Pat Owner",
            "verification_evidence": "EVID1",
            "last_updated_date": date(2026, 8, 20),
        }
        defaults.update(overrides)
        return TestCase.model_validate(defaults)

    return _make


@pytest.fixture
def make_trace_link() -> Callable[..., TraceLink]:
    def _make(**overrides: object) -> TraceLink:
        defaults: dict[str, object] = {
            "trace_link_id": "TL1",
            "project_id": TEST_PROJECT_ID,
            "source_type": "Requirement",
            "source_id": "REQ1",
            "target_type": "TestCase",
            "target_id": "TC1",
            "link_type": "verified_by",
        }
        defaults.update(overrides)
        return TraceLink.model_validate(defaults)

    return _make


@pytest.fixture
def make_change_request() -> Callable[..., ChangeRequest]:
    def _make(**overrides: object) -> ChangeRequest:
        defaults: dict[str, object] = {
            "change_request_id": "CR1",
            "project_id": TEST_PROJECT_ID,
            "requirement_id": "REQ1",
            "change_description": "Adjust a requirement.",
            "reason": "Stakeholder request.",
            "priority": "Medium",
            "status": "Proposed",
            "requested_by": "Pat Owner",
            "requested_date": date(2026, 8, 1),
        }
        defaults.update(overrides)
        return ChangeRequest.model_validate(defaults)

    return _make


@pytest.fixture
def make_portfolio() -> Callable[..., PortfolioData]:
    def _make(**overrides: object) -> PortfolioData:
        return PortfolioData(**overrides)  # type: ignore[arg-type]

    return _make
