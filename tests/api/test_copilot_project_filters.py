"""Project restrictions in Ask EPOS are honoured, shown back, and never silently widened."""

from __future__ import annotations

import json
from typing import Any

import pytest

from api.services import copilot_service, project_query, semantic_router
from src.config import AzureOpenAISettings
from src.health_engine import calculate_project_health
from src.ui_formatting import ANALYSIS_DATE

TECH = {"P-007", "P-019", "P-023"}


def _ids(portfolio, predicate) -> set[str]:
    return {project.project_id for project in portfolio.projects if predicate(project)}


def _ask(question: str, portfolio, **kwargs: Any):
    return copilot_service.ask(question, portfolio, ANALYSIS_DATE, **kwargs)


def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ai_assistant.get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )


def _route(**overrides: Any) -> dict[str, Any]:
    route: dict[str, Any] = dict.fromkeys(
        (
            "secondary_intent",
            "project_id",
            "project_name",
            "change_request_id",
            "domain_filter",
            "record_type",
            "status_filter",
            "dependency_id",
            "additional_delay_days",
            "clarification",
        )
    )
    route.update(intent="list_projects", confidence="high")
    route.update(overrides)
    return route


def _filter(**overrides: Any) -> dict[str, Any]:
    reply: dict[str, Any] = {
        "domains": [],
        "excluded_domains": [],
        "phases": [],
        "priorities": [],
        "managers": [],
        "health_bands": [],
        "name_keywords": [],
        "unmatched_terms": [],
        "sort": None,
        "limit": None,
    }
    reply.update(overrides)
    return reply


def _transport(route: dict[str, Any]):
    calls: list[str] = []

    def send(_url: str, _headers: dict[str, str], body: dict, _timeout: float) -> dict:
        calls.append(body["response_format"]["json_schema"]["name"])
        return {"choices": [{"message": {"content": json.dumps(route)}}]}

    send.calls = calls
    return send


class TestParsing:
    @pytest.mark.parametrize(
        ("question", "field", "values", "excluded", "interpreted"),
        [
            ("list software projects", "domain", ("Embedded Software",), False, False),
            ("list projects in embedded software", "domain", ("Embedded Software",), False, False),
            ("list IT projects", "domain", ("IT Systems",), False, False),
            ("list all projects except sustainability", "domain", ("Sustainability",), True, False),
            ("list high priority projects", "priority", ("High",), False, False),
            ("list critical projects", "priority", ("Critical",), False, True),
            ("list projects in execution phase", "phase", ("Execution",), False, False),
            ("list red projects", "health_band", ("Red",), False, False),
            ("which projects are red or amber?", "health_band", ("Red", "Amber"), False, False),
            ("list healthy projects", "health_band", ("Green",), False, True),
            ("list projects managed by Priya", "manager", ("Priya Nair",), False, False),
            ("list projects not managed by Alex Morgan", "manager", ("Alex Morgan",), True, False),
            ("list supplier projects", "name", ("supplier",), False, False),
        ],
    )
    def test_restrictions_resolve_onto_recorded_values(
        self, csv_portfolio, question, field, values, excluded, interpreted
    ) -> None:
        query = project_query.parse(question, csv_portfolio).query

        assert query.unmatched == ()
        [term] = project_query.merged_terms(query)
        assert (term.field, set(term.values), term.excluded, term.interpreted) == (
            field,
            set(values),
            excluded,
            interpreted,
        )

    def test_an_umbrella_word_is_an_explicit_interpretation(self, csv_portfolio) -> None:
        [term] = project_query.parse("list down only tech projects", csv_portfolio).query.terms

        assert term.field == "domain"
        assert set(term.values) == {"Digital Engineering", "Embedded Software", "IT Systems"}
        assert term.interpreted is True
        assert term.phrase == "tech"

    @pytest.mark.parametrize(
        "question",
        [
            "Which projects need attention this week?",
            "Why is P-002 red?",
            "Which risks are high priority",
            "Show only archived risks",
            "Which requirements lack verification evidence?",
            "What happens if dependency D-2001 slips by 10 days?",
            "Which projects are late?",
        ],
    )
    def test_questions_without_project_restrictions_are_left_alone(
        self, csv_portfolio, question
    ) -> None:
        assert project_query.parse(question, csv_portfolio).query.is_empty

    def test_filter_wording_is_removed_before_routing(self, csv_portfolio) -> None:
        parsed = project_query.parse("list projects in execution phase", csv_portfolio)

        assert parsed.residual == "list projects"

    def test_unrecognised_wording_is_kept_as_unmatched(self, csv_portfolio) -> None:
        query = project_query.parse("list blockchain projects", csv_portfolio).query

        assert query.terms == ()
        assert query.unmatched == ("blockchain",)

    def test_saved_queries_keep_only_values_still_recorded(self, csv_portfolio) -> None:
        saved = project_query.ProjectQuery(
            terms=(
                project_query.Term("domain", ("Embedded Software", "Quantum"), "tech"),
                project_query.Term("phase", ("Imaginary",), "imaginary"),
            )
        ).to_json()

        restored = project_query.ProjectQuery.from_json(saved, csv_portfolio)

        assert [(term.field, term.values) for term in restored.terms] == [
            ("domain", ("Embedded Software",))
        ]


class TestDeterministicAnswers:
    def test_only_tech_projects_are_listed_and_the_reading_is_stated(self, csv_portfolio) -> None:
        answer = _ask("list down only tech projects", csv_portfolio)

        assert answer.matched_intent == "list_projects"
        assert set(answer.source_ids) == TECH
        assert "“tech” is not a recorded domain" in answer.executive_summary
        [shown] = answer.applied_filters
        assert shown.field == "domain" and shown.interpreted_from == "tech"
        assert "List all projects" in answer.suggested_questions

    @pytest.mark.parametrize(
        "question", ["show me tech projects", "which projects are tech projects?"]
    )
    def test_tech_phrasings_without_selector_words_are_still_filtered(
        self, csv_portfolio, question
    ) -> None:
        assert set(_ask(question, csv_portfolio).source_ids) == TECH

    def test_an_exclusion_removes_the_named_domain(self, csv_portfolio) -> None:
        answer = _ask("list all projects except sustainability", csv_portfolio)

        assert set(answer.source_ids) == _ids(
            csv_portfolio, lambda project: project.domain != "Sustainability"
        )
        assert "other than Sustainability" in answer.executive_summary
        assert answer.applied_filters[0].excluded is True

    def test_priority_is_a_filter_not_an_attention_question(self, csv_portfolio) -> None:
        answer = _ask("list high priority projects", csv_portfolio)

        assert answer.matched_intent == "list_projects"
        assert set(answer.source_ids) == _ids(
            csv_portfolio, lambda project: project.business_priority == "High"
        )

    def test_a_phase_is_not_mistaken_for_an_executive_report(self, csv_portfolio) -> None:
        answer = _ask("list projects in execution phase", csv_portfolio)

        assert answer.status == "ok"
        assert answer.matched_intent == "list_projects"
        assert set(answer.source_ids) == _ids(
            csv_portfolio, lambda project: project.project_phase == "Execution"
        )

    def test_health_bands_come_from_the_engine(self, csv_portfolio) -> None:
        answer = _ask("list red projects", csv_portfolio)

        red = {
            project.project_id
            for project in csv_portfolio.projects
            if calculate_project_health(
                project.project_id, csv_portfolio, ANALYSIS_DATE
            ).health_band
            == "Red"
        }
        assert red and set(answer.source_ids) == red
        assert all(record.fields["health_band"] == "Red" for record in answer.evidence)

    def test_worst_projects_are_ordered_by_calculated_health(self, csv_portfolio) -> None:
        answer = _ask("top 3 worst projects", csv_portfolio)

        scores = sorted(
            (
                calculate_project_health(
                    project.project_id, csv_portfolio, ANALYSIS_DATE
                ).overall_score,
                project.project_name,
                project.project_id,
            )
            for project in csv_portfolio.projects
        )
        assert answer.source_ids == [project_id for *_, project_id in scores[:3]]
        assert "lowest health first" in answer.executive_summary

    def test_an_unrecorded_category_is_reported_not_widened(self, csv_portfolio) -> None:
        answer = _ask("list blockchain projects", csv_portfolio)

        assert answer.source_ids == []
        assert answer.unapplied_filters == ["blockchain"]
        assert "I couldn't match “blockchain” to a recorded domain" in answer.executive_summary
        for domain in {project.domain for project in csv_portfolio.projects}:
            assert domain in answer.executive_summary

    def test_a_filter_narrows_an_analytical_answer(self, csv_portfolio) -> None:
        answer = _ask("which high priority projects need attention?", csv_portfolio)

        high = _ids(csv_portfolio, lambda project: project.business_priority == "High")
        projects = {
            record.record_id
            for record in answer.evidence
            if record.record_id in csv_portfolio.project_ids
        }
        assert answer.matched_intent == "projects_needing_attention"
        assert projects and projects <= high
        assert answer.applied_filters[0].values == ["High"]
        assert "projects matching business priority High need attention" in (
            answer.executive_summary
        )
        assert "accessible projects" not in answer.executive_summary

    def test_risks_in_filtered_projects_stay_inside_those_projects(self, csv_portfolio) -> None:
        answer = _ask("what are the risks in tech projects", csv_portfolio)

        risks = [record for record in answer.evidence if record.record_type == "risk"]
        assert answer.matched_intent == "workspace_evidence"
        assert risks and {record.fields["project_id"] for record in risks} <= TECH

    def test_the_query_is_saved_for_follow_up_questions(self, csv_portfolio) -> None:
        answer = _ask("list high priority projects", csv_portfolio)

        saved = project_query.ProjectQuery.from_json(answer.context["project_query"], csv_portfolio)
        assert saved.terms[0].values == ("High",)


class TestModelInterpretation:
    def test_the_schema_limits_filters_to_recorded_values(self, csv_portfolio) -> None:
        schema = semantic_router.route_schema(csv_portfolio)
        filters = schema["properties"]["project_filter"]["properties"]

        assert set(filters["domains"]["items"]["enum"]) == {
            project.domain for project in csv_portfolio.projects
        }
        assert set(filters["phases"]["items"]["enum"]) == {
            project.project_phase for project in csv_portfolio.projects
        }
        assert "project_filter" in schema["required"]

    def test_a_model_reading_replaces_a_local_interpretation(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _transport(
            _route(
                domain_filter="tech",
                project_filter=_filter(domains=["Embedded Software", "IT Systems"]),
            )
        )

        answer = _ask("list down only tech projects", csv_portfolio, transport=transport)

        assert set(answer.source_ids) == {"P-019", "P-023"}
        assert answer.applied_filters[0].interpreted_from == "tech"

    def test_values_outside_the_portfolio_are_discarded(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)
        transport = _transport(
            _route(domain_filter="space", project_filter=_filter(domains=["Astronautics"]))
        )

        answer = _ask("list space projects", csv_portfolio, transport=transport)

        assert answer.source_ids == []
        assert answer.unapplied_filters == ["space"]

    def test_an_empty_model_filter_never_drops_the_users_restriction(
        self, csv_portfolio, monkeypatch
    ) -> None:
        _configured(monkeypatch)
        transport = _transport(_route(project_filter=_filter()))

        answer = _ask("list blockchain projects", csv_portfolio, transport=transport)

        assert answer.source_ids == []
        assert answer.unapplied_filters == ["blockchain"]

    def test_literal_matches_outrank_the_model(self, csv_portfolio, monkeypatch) -> None:
        _configured(monkeypatch)
        transport = _transport(
            _route(project_filter=_filter(domains=["Sustainability"]), confidence="high")
        )

        answer = _ask("list embedded software projects only", csv_portfolio, transport=transport)

        assert answer.source_ids == ["P-019"]
