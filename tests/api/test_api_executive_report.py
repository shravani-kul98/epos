"""The weekly executive report.

The report is assembled from facts that already exist, so these tests assert that every statement
is traceable and that a section with nothing to say is omitted rather than shown empty.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.models import ProjectTable
from api.services.delta_service import _SOURCES
from src.ui_formatting import format_score
from tests.api.conftest import url


def _age(engine: Engine, days: int) -> None:
    """Push every record back in time so the movement section starts from a quiet baseline."""
    moment = datetime.now(UTC) - timedelta(days=days)
    with Session(engine) as session:
        for table in (ProjectTable, *(source.table for source in _SOURCES)):
            for row in session.exec(select(table)).all():
                row.created_at = moment
                row.updated_at = moment
                session.add(row)
        session.commit()


@pytest.fixture
def aged_client(client: TestClient, seeded_engine: Engine) -> TestClient:
    """A signed-in client whose seeded records predate every report window used here."""
    _age(seeded_engine, days=400)
    return client


def _report(client: TestClient, days: int = 7) -> dict:
    response = client.get(url(f"/analytics/executive-report?days={days}"))
    assert response.status_code == 200
    return response.json()


def _section(body: dict, key: str) -> dict | None:
    return next((section for section in body["sections"] if section["key"] == key), None)


class TestAccess:
    def test_a_signed_out_visitor_cannot_read_the_report(
        self, anonymous_client: TestClient
    ) -> None:
        assert anonymous_client.get(url("/analytics/executive-report")).status_code == 401

    def test_the_window_is_rejected_when_it_is_not_a_sane_number_of_days(
        self, client: TestClient
    ) -> None:
        assert client.get(url("/analytics/executive-report?days=0")).status_code == 422
        assert client.get(url("/analytics/executive-report?days=9999")).status_code == 422

    def test_an_engineer_cannot_read_the_report(self, engineer_client: TestClient) -> None:
        assert engineer_client.get(url("/analytics/executive-report")).status_code == 403


class TestHeadline:
    def test_the_headline_states_the_position_in_one_sentence(self, client: TestClient) -> None:
        headline = _report(client)["headline"]

        assert headline.endswith(".")
        assert headline[0].isupper()
        assert "_" not in headline

    def test_the_headline_counts_agree_with_the_band_tallies(self, client: TestClient) -> None:
        body = _report(client)
        bands = body["health_bands"]

        assert bands["green"] + bands["amber"] + bands["red"] == body["project_count"]
        if bands["red"]:
            assert str(bands["red"]) in body["headline"]

    def test_the_report_matches_the_portfolio_it_summarises(self, client: TestClient) -> None:
        report = _report(client)
        dashboard = client.get(url("/analytics/portfolio")).json()

        assert report["project_count"] == dashboard["project_count"]
        assert report["health_bands"] == dashboard["health_bands"]
        assert report["alert_severities"] == dashboard["alert_severities"]


class TestSections:
    def test_every_statement_names_the_records_behind_it(self, client: TestClient) -> None:
        for section in _report(client)["sections"]:
            for item in section["items"]:
                assert item["source_ids"], f"{section['key']} has an unsourced statement"

    def test_every_source_identifier_is_collected_at_the_top(self, client: TestClient) -> None:
        body = _report(client)
        used = {
            source
            for section in body["sections"]
            for item in section["items"]
            for source in item["source_ids"]
        }

        assert set(body["source_ids"]) == used
        assert body["source_ids"] == sorted(body["source_ids"])

    def test_a_section_with_nothing_to_say_is_left_out(self, aged_client: TestClient) -> None:
        assert _section(_report(aged_client), "movement") is None

    def test_projects_in_the_red_band_are_reported(self, client: TestClient) -> None:
        dashboard = client.get(url("/analytics/portfolio")).json()
        red = [row for row in dashboard["projects"] if row["health_band"] == "Red"]
        section = _section(_report(client), "attention")

        assert section is not None
        assert str(len(red)) in section["summary"]

    def test_a_score_reads_the_same_here_as_on_the_dashboard(self, client: TestClient) -> None:
        """One score, one rendering. A half such as 59.25 must not read 59.2 here and 59.3 there."""
        dashboard = client.get(url("/analytics/portfolio")).json()
        section = _section(_report(client), "attention")
        assert section is not None

        reported = {item["source_ids"][0]: item["text"] for item in section["items"]}
        for row in dashboard["projects"]:
            text = reported.get(row["project_id"])
            if text is None:
                continue
            assert f"scores {format_score(row['health_score'])} " in text

    def test_movement_is_reported_once_something_moves(self, aged_client: TestClient) -> None:
        milestone = aged_client.get(url("/projects/P-002/milestones")).json()[0]
        aged_client.patch(
            url(f"/milestones/{milestone['milestone_id']}"),
            json={"status": "At Risk", "row_version": milestone["row_version"]},
        )
        section = _section(_report(aged_client), "movement")

        assert section is not None
        assert section["items"][0]["source_ids"] == ["P-002"]

    def test_a_waiting_decision_is_reported(self, aged_client: TestClient) -> None:
        aged_client.post(
            url("/decisions"),
            json={
                "decision_id": "DEC-700",
                "project_id": "P-002",
                "title": "Confirm the supplier qualification route",
                "description": "Two routes remain open and the schedule cannot absorb both.",
                "category": "Supply",
                "decision_date": "2026-08-20",
                "owner": "Alex Morgan",
            },
        )
        section = _section(_report(aged_client), "decisions")

        assert section is not None
        assert any("still waiting on Alex Morgan" in item["text"] for item in section["items"])

    def test_a_resolved_decision_is_reported(self, aged_client: TestClient) -> None:
        created = aged_client.post(
            url("/decisions"),
            json={
                "decision_id": "DEC-701",
                "project_id": "P-002",
                "title": "Hold the pilot until tooling is confirmed",
                "description": "Committing now would put the launch date at risk.",
                "category": "Schedule",
                "decision_date": "2026-08-20",
                "owner": "Alex Morgan",
            },
        )
        aged_client.post(
            url("/decisions/DEC-701/outcome"),
            json={
                "outcome": "Approved",
                "rationale": "Supplier confirmation is the gating item.",
                "row_version": created.json()["row_version"],
            },
        )
        section = _section(_report(aged_client), "decisions")

        assert section is not None
        assert any("was approved by" in item["text"] for item in section["items"])

    def test_the_window_only_moves_the_period_sections(self, aged_client: TestClient) -> None:
        seven = _report(aged_client, days=7)
        thirty = _report(aged_client, days=30)

        assert seven["window_days"] == 7
        assert thirty["window_days"] == 30
        assert seven["health_bands"] == thirty["health_bands"]
        assert _section(seven, "attention") == _section(thirty, "attention")


class TestLanguage:
    def test_no_statement_leaks_an_internal_key(self, client: TestClient) -> None:
        for section in _report(client)["sections"]:
            assert "_" not in section["summary"]
            for item in section["items"]:
                assert "_" not in item["text"]

    def test_counts_and_nouns_agree(self, client: TestClient) -> None:
        for section in _report(client)["sections"]:
            assert " 1 projects" not in section["summary"]
            assert " 1 records" not in section["summary"]
            assert " 1 decisions" not in section["summary"]
