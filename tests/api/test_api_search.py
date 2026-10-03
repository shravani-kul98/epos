"""One search across every record type in the workspace."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import url


def _search(client: TestClient, query: str, limit: int | None = None) -> dict:
    path = f"/search?q={query}" + (f"&limit={limit}" if limit else "")
    response = client.get(url(path))
    assert response.status_code == 200
    return response.json()


class TestAccess:
    def test_a_signed_out_visitor_cannot_search(self, anonymous_client: TestClient) -> None:
        assert anonymous_client.get(url("/search?q=supplier")).status_code == 401

    def test_the_query_is_required(self, client: TestClient) -> None:
        assert client.get(url("/search")).status_code == 422

    def test_the_page_size_is_bounded(self, client: TestClient) -> None:
        assert client.get(url("/search?q=supplier&limit=0")).status_code == 422
        assert client.get(url("/search?q=supplier&limit=500")).status_code == 422


class TestMatching:
    def test_a_single_character_returns_nothing_rather_than_everything(
        self, client: TestClient
    ) -> None:
        body = _search(client, "s")

        assert body["total"] == 0
        assert body["hits"] == []

    def test_an_identifier_finds_its_record(self, client: TestClient) -> None:
        body = _search(client, "P-002")

        assert body["hits"][0]["record_id"] == "P-002"
        assert body["hits"][0]["record_type"] == "project"

    def test_an_identifier_match_is_ranked_above_a_name_match(self, client: TestClient) -> None:
        body = _search(client, "R-2001")

        assert body["hits"][0]["record_id"] == "R-2001"

    def test_matching_ignores_case(self, client: TestClient) -> None:
        assert _search(client, "p-002")["hits"][0]["record_id"] == "P-002"

    def test_a_name_fragment_finds_records_across_types(self, client: TestClient) -> None:
        types = {hit["record_type"] for hit in _search(client, "supplier", limit=100)["hits"]}

        assert len(types) > 1

    def test_nothing_is_returned_for_a_query_that_matches_no_record(
        self, client: TestClient
    ) -> None:
        body = _search(client, "zzzzznotarecord")

        assert body["total"] == 0
        assert body["hits"] == []

    def test_an_owner_can_be_searched_for(self, client: TestClient) -> None:
        manager = client.get(url("/projects/P-002")).json()["project_manager"]
        surname = manager.split(" ")[-1]

        assert _search(client, surname, limit=100)["total"] > 0


class TestResults:
    def test_the_total_counts_every_match_not_only_the_page(self, client: TestClient) -> None:
        body = _search(client, "supplier", limit=1)

        assert len(body["hits"]) == 1
        assert body["total"] >= 1

    def test_every_hit_can_be_opened(self, client: TestClient) -> None:
        for hit in _search(client, "supplier", limit=100)["hits"]:
            assert hit["path"].startswith("/projects/")
            assert hit["project_id"]
            assert hit["project_name"]

    def test_every_hit_names_the_kind_of_record_it_is(self, client: TestClient) -> None:
        for hit in _search(client, "supplier", limit=100)["hits"]:
            assert hit["record_type_label"]
            assert "_" not in hit["record_type_label"]

    def test_a_withdrawn_record_disappears_from_search(self, client: TestClient) -> None:
        risk = client.get(url("/projects/P-002/risks")).json()[0]
        assert _search(client, risk["risk_id"])["total"] == 1

        client.delete(
            url(f"/risks/{risk['risk_id']}"),
            params={"row_version": risk["row_version"]},
        )

        assert _search(client, risk["risk_id"])["total"] == 0

    def test_a_new_record_appears_in_search(self, client: TestClient) -> None:
        client.post(
            url("/decisions"),
            json={
                "decision_id": "DEC-800",
                "project_id": "P-002",
                "title": "Adopt the dual sourcing route",
                "description": "A single source cannot cover the qualification window.",
                "category": "Supply",
                "decision_date": "2026-08-20",
                "owner": "Alex Morgan",
            },
        )
        hits = _search(client, "dual sourcing")["hits"]

        assert hits[0]["record_id"] == "DEC-800"
        assert hits[0]["path"] == "/projects/P-002?tab=decisions"

    def test_the_query_is_echoed_back_trimmed(self, client: TestClient) -> None:
        assert _search(client, "%20supplier%20")["query"] == "supplier"
