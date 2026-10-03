"""What changed on a project since a chosen moment.

A delta is a reading of the audit columns, never a stored snapshot, so these tests move real
timestamps rather than asserting against fixed dates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from api.models import DecisionTable, ProjectTable
from api.services.delta_service import _SOURCES
from tests.api.conftest import url

PROJECT = "P-002"


def _age(engine: Engine, days: int) -> None:
    """Push every record on the project back in time so a window can see past it."""
    moment = datetime.now(UTC) - timedelta(days=days)
    tables = (ProjectTable, *(source.table for source in _SOURCES))
    with Session(engine) as session:
        for table in tables:
            for row in session.exec(select(table)).all():
                row.created_at = moment
                row.updated_at = moment
                session.add(row)
        session.commit()


@pytest.fixture
def aged_client(client: TestClient, seeded_engine: Engine) -> TestClient:
    """A signed-in client whose seeded records predate every delta window used here."""
    _age(seeded_engine, days=400)
    return client


def _delta(client: TestClient, days: int = 7, project: str = PROJECT) -> dict:
    response = client.get(url(f"/projects/{project}/delta?days={days}"))
    assert response.status_code == 200
    return response.json()


def _entries(body: dict, group: str) -> list[dict]:
    for item in body["groups"]:
        if item["key"] == group:
            return item["entries"]
    return []


class TestWindow:
    def test_a_freshly_seeded_project_reports_no_earlier_state(self, client: TestClient) -> None:
        body = _delta(client)

        assert body["has_history"] is False

    def test_an_established_project_has_something_to_compare_against(
        self, aged_client: TestClient
    ) -> None:
        assert _delta(aged_client)["has_history"] is True

    def test_a_quiet_week_reports_no_changes(self, aged_client: TestClient) -> None:
        body = _delta(aged_client)

        assert body["total_changes"] == 0
        assert body["groups"] == []

    def test_the_window_is_rejected_when_it_is_not_a_sane_number_of_days(
        self, client: TestClient
    ) -> None:
        assert client.get(url(f"/projects/{PROJECT}/delta?days=0")).status_code == 422
        assert client.get(url(f"/projects/{PROJECT}/delta?days=9999")).status_code == 422

    def test_an_unknown_project_is_not_found(self, client: TestClient) -> None:
        assert client.get(url("/projects/P-999/delta")).status_code == 404

    def test_the_delta_names_the_project_it_describes(self, aged_client: TestClient) -> None:
        body = _delta(aged_client)

        assert body["project_id"] == PROJECT
        assert body["project_name"]
        assert body["project_name"] != PROJECT

    def test_a_signed_out_visitor_cannot_read_a_delta(self, anonymous_client: TestClient) -> None:
        assert anonymous_client.get(url(f"/projects/{PROJECT}/delta")).status_code == 401


class TestChanges:
    def test_a_new_record_appears_as_added(self, aged_client: TestClient) -> None:
        aged_client.post(
            url("/risks"),
            json={
                "risk_id": "R-900",
                "project_id": PROJECT,
                "risk_name": "Supplier tooling capacity is unconfirmed",
                "probability": 4,
                "impact": 4,
                "status": "Open",
                "due_date": "2026-09-30",
            },
        )
        entries = _entries(_delta(aged_client), "risks")

        assert [entry["change_type"] for entry in entries] == ["added"]
        assert entries[0]["entity_id"] == "R-900"

    def test_an_edited_record_appears_as_updated(self, aged_client: TestClient) -> None:
        milestone = aged_client.get(url(f"/projects/{PROJECT}/milestones")).json()[0]
        aged_client.patch(
            url(f"/milestones/{milestone['milestone_id']}"),
            json={"status": "At Risk", "row_version": milestone["row_version"]},
        )
        entries = _entries(_delta(aged_client), "delivery")

        assert [entry["change_type"] for entry in entries] == ["updated"]
        assert entries[0]["entity_id"] == milestone["milestone_id"]

    def test_a_withdrawn_record_appears_as_withdrawn(self, aged_client: TestClient) -> None:
        risk = aged_client.get(url(f"/projects/{PROJECT}/risks")).json()[0]
        aged_client.delete(
            url(f"/risks/{risk['risk_id']}"),
            params={"row_version": risk["row_version"]},
        )
        entries = _entries(_delta(aged_client), "risks")

        assert [entry["change_type"] for entry in entries] == ["withdrawn"]
        assert entries[0]["entity_id"] == risk["risk_id"]

    def test_a_change_outside_the_window_is_not_reported(self, aged_client: TestClient) -> None:
        milestone = aged_client.get(url(f"/projects/{PROJECT}/milestones")).json()[0]
        aged_client.patch(
            url(f"/milestones/{milestone['milestone_id']}"),
            json={"status": "At Risk", "row_version": milestone["row_version"]},
        )

        assert _delta(aged_client, days=7)["total_changes"] == 1

    def test_another_project_is_never_mixed_in(self, aged_client: TestClient) -> None:
        aged_client.post(
            url("/risks"),
            json={
                "risk_id": "R-901",
                "project_id": "P-007",
                "risk_name": "Test rig availability is contested",
                "probability": 3,
                "impact": 3,
                "status": "Open",
                "due_date": "2026-09-30",
            },
        )

        assert _delta(aged_client, project=PROJECT)["total_changes"] == 0
        assert _delta(aged_client, project="P-007")["total_changes"] == 1


class TestPresentation:
    def test_each_group_counts_what_it_holds(self, aged_client: TestClient) -> None:
        milestone = aged_client.get(url(f"/projects/{PROJECT}/milestones")).json()[0]
        aged_client.patch(
            url(f"/milestones/{milestone['milestone_id']}"),
            json={"status": "At Risk", "row_version": milestone["row_version"]},
        )
        body = _delta(aged_client)

        for group in body["groups"]:
            assert group["added"] + group["updated"] + group["withdrawn"] == len(group["entries"])
        assert body["total_changes"] == sum(len(group["entries"]) for group in body["groups"])

    def test_a_headline_reads_as_a_sentence(self, aged_client: TestClient) -> None:
        milestone = aged_client.get(url(f"/projects/{PROJECT}/milestones")).json()[0]
        aged_client.patch(
            url(f"/milestones/{milestone['milestone_id']}"),
            json={"status": "At Risk", "row_version": milestone["row_version"]},
        )
        headline = _entries(_delta(aged_client), "delivery")[0]["headline"]

        assert headline.endswith(".")
        assert headline[0].isupper()
        assert "_" not in headline

    def test_the_person_who_made_the_change_is_credited(self, aged_client: TestClient) -> None:
        milestone = aged_client.get(url(f"/projects/{PROJECT}/milestones")).json()[0]
        aged_client.patch(
            url(f"/milestones/{milestone['milestone_id']}"),
            json={"status": "At Risk", "row_version": milestone["row_version"]},
        )

        assert _entries(_delta(aged_client), "delivery")[0]["actor_name"]

    def test_groups_follow_a_fixed_reading_order(self, aged_client: TestClient) -> None:
        milestone = aged_client.get(url(f"/projects/{PROJECT}/milestones")).json()[0]
        aged_client.patch(
            url(f"/milestones/{milestone['milestone_id']}"),
            json={"status": "At Risk", "row_version": milestone["row_version"]},
        )
        aged_client.post(
            url("/risks"),
            json={
                "risk_id": "R-902",
                "project_id": PROJECT,
                "risk_name": "Qualification slots may not be released in time",
                "probability": 3,
                "impact": 4,
                "status": "Open",
                "due_date": "2026-09-30",
            },
        )
        keys = [group["key"] for group in _delta(aged_client)["groups"]]

        assert keys == ["delivery", "risks"]

    def test_decisions_are_reported_in_their_own_group(
        self, aged_client: TestClient, seeded_engine: Engine
    ) -> None:
        aged_client.post(
            url("/decisions"),
            json={
                "decision_id": "DEC-500",
                "project_id": PROJECT,
                "title": "Hold the pilot until supplier tooling is confirmed",
                "description": "Committing before confirmation would put the launch date at risk.",
                "category": "Schedule",
                "decision_date": "2026-08-20",
                "owner": "Alex Morgan",
            },
        )
        entries = _entries(_delta(aged_client), "decisions")

        assert [entry["entity_id"] for entry in entries] == ["DEC-500"]
        with Session(seeded_engine) as session:
            assert session.get(DecisionTable, "DEC-500") is not None
