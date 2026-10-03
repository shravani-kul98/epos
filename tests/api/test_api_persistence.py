"""Persistence, seeding and service-readiness tests."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.models import ActivityEventTable, DecisionTable, MeetingNoteTable, ProjectTable
from api.seed import is_seeded, seed_database, seed_session
from api.services.portfolio_service import load_portfolio_from_db
from src.data_loader import PortfolioData
from src.health_engine import calculate_project_health
from tests.api.conftest import url


def test_empty_database_reports_not_seeded(empty_client: TestClient) -> None:
    payload = empty_client.get(url("/health")).json()
    assert payload["status"] == "ok"
    assert payload["database_seeded"] is False
    assert payload["project_count"] == 0


def test_seeded_database_reports_project_count(client: TestClient, csv_portfolio) -> None:
    payload = client.get(url("/health")).json()
    assert payload["database_seeded"] is True
    assert payload["project_count"] == len(csv_portfolio.projects)


def test_health_check_never_exposes_secret_values(client: TestClient) -> None:
    body = client.get(url("/health")).text
    assert "api_key" not in body.lower()
    assert "endpoint" not in body.lower()


def test_health_check_reports_ai_configuration_as_boolean(client: TestClient) -> None:
    assert isinstance(client.get(url("/health")).json()["ai_configured"], bool)


def test_seeding_is_detected(session: Session, csv_portfolio: PortfolioData) -> None:
    assert is_seeded(session) is False
    seed_session(session, csv_portfolio)
    assert is_seeded(session) is True


def test_seed_writes_every_collection(session: Session, csv_portfolio: PortfolioData) -> None:
    written = seed_session(session, csv_portfolio)
    assert written["projects"] == len(csv_portfolio.projects)
    assert written["tasks"] == len(csv_portfolio.tasks)
    assert written["trace_links"] == len(csv_portfolio.trace_links)


def test_force_reseed_clears_project_memberships_decisions_and_notes(
    seeded_engine: Engine, csv_portfolio: PortfolioData
) -> None:
    with Session(seeded_engine) as session:
        session.add(
            DecisionTable(
                decision_id="DEC-RESEED",
                project_id="P-002",
                title="Synthetic reseed decision",
                description="Synthetic decision created for reseed validation.",
                category="Delivery",
                decision_date=date(2026, 3, 1),
                owner="Synthetic Owner",
                status="Proposed",
            )
        )
        session.add(
            MeetingNoteTable(
                note_id="MN-RESEED",
                project_id="P-002",
                title="Synthetic reseed note",
                meeting_date=date(2026, 3, 1),
                body="Synthetic meeting evidence.",
            )
        )
        session.commit()

    written = seed_database(seeded_engine, force=True)

    assert written["projects"] == len(csv_portfolio.projects)
    with Session(seeded_engine) as session:
        assert session.get(DecisionTable, "DEC-RESEED") is None
        assert session.get(MeetingNoteTable, "MN-RESEED") is None


def test_force_reseed_refuses_to_reuse_identifiers_in_immutable_activity(
    seeded_engine: Engine,
) -> None:
    with Session(seeded_engine) as session:
        event = ActivityEventTable(
            action="updated",
            entity_type="Project",
            entity_id="P-002",
            project_id="P-002",
            summary="Updated synthetic project",
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        event_id = event.id

    with pytest.raises(RuntimeError, match="immutable Activity Events exist"):
        seed_database(seeded_engine, force=True)

    with Session(seeded_engine) as session:
        assert session.get(ActivityEventTable, event_id) is not None
        assert session.get(ProjectTable, "P-002") is not None


def test_database_round_trip_matches_csv_portfolio(
    seeded_engine: Engine, csv_portfolio: PortfolioData
) -> None:
    """Loading from the database must reproduce the CSV portfolio exactly."""
    with Session(seeded_engine) as session:
        from_db = load_portfolio_from_db(session)

    for attribute in (
        "projects",
        "milestones",
        "tasks",
        "risks",
        "dependencies",
        "actions",
        "resources",
        "requirements",
        "test_cases",
        "trace_links",
        "change_requests",
    ):
        expected = sorted(getattr(csv_portfolio, attribute), key=lambda item: str(item))
        actual = sorted(getattr(from_db, attribute), key=lambda item: str(item))
        assert actual == expected, attribute


@pytest.mark.parametrize(
    ("project_id", "expected_score", "expected_band"),
    [("P-002", 49.9, "Red"), ("P-007", 51.15, "Red")],
)
def test_engine_results_are_identical_through_the_database(
    seeded_engine: Engine, project_id: str, expected_score: float, expected_band: str
) -> None:
    """The database must be a faithful substitute for the CSV source of truth."""
    with Session(seeded_engine) as session:
        portfolio = load_portfolio_from_db(session)

    result = calculate_project_health(project_id, portfolio, date(2026, 8, 25))
    assert result.overall_score == expected_score
    assert result.health_band == expected_band


def test_seeded_data_has_no_status_anomalies(seeded_engine: Engine) -> None:
    with Session(seeded_engine) as session:
        assert load_portfolio_from_db(session).status_anomalies == []


def test_seeding_does_not_write_activity_events(seeded_engine: Engine) -> None:
    """Seeding is not a user action and must not pollute the audit trail."""
    with Session(seeded_engine) as session:
        assert session.exec(select(ActivityEventTable)).all() == []


def test_tests_never_touch_the_real_database_file(seeded_engine: Engine) -> None:
    """The installed engine must be in-memory for the whole suite."""
    assert seeded_engine.url.database in (None, ":memory:")


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get(url("/does-not-exist")).status_code == 404


def test_project_table_primary_key_is_the_project_id(session: Session) -> None:
    session.add(
        ProjectTable(
            project_id="P-999",
            project_name="Synthetic",
            domain="Test",
            project_manager="A. Person",
            start_date=date(2026, 1, 1),
            project_phase="Design",
            business_priority="Medium",
        )
    )
    session.commit()
    assert session.get(ProjectTable, "P-999") is not None
