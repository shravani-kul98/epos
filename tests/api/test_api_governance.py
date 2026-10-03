"""Governance tests: product language, evidence, and AI boundaries."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from api import labels
from src.risk_engine import (
    ALERT_BLOCKED_TASK,
    ALERT_MILESTONE_DEPENDENCY,
    ALERT_MILESTONE_SLIP,
    ALERT_OVERDUE_ACTION,
    ALERT_REQUIREMENT_VERIFICATION,
    ALERT_RESOURCE_OVERALLOCATION,
    ALERT_STALE_STATUS,
    ALERT_UNOWNED_RISK,
)
from src.scoring_rules import CONFIDENCE_FACTORS, HEALTH_FACTORS
from tests.api.conftest import url

# A snake_case token of two or more words, e.g. "task_execution".
_SNAKE_CASE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")

# Keys that are legitimately snake_case because they are machine-readable field names,
# not text shown to a person.
_ALLOWED_FIELD_NAMES = {
    "alert_type",
    "alert_type_label",
    "as_of_date",
    "baseline_date",
    "forecast_date",
    "issue_type",
    "record_id",
    "record_type",
    "source_ids",
    "trace_status",
}


# ------------------------------------------------------------------ label completeness
def test_every_engine_factor_has_a_product_label() -> None:
    assert labels.missing_labels() == []


def test_health_labels_are_human_readable() -> None:
    for key in HEALTH_FACTORS:
        label = labels.health_factor_label(key)
        assert "_" not in label
        assert label[0].isupper()


def test_confidence_labels_are_human_readable() -> None:
    for key in CONFIDENCE_FACTORS:
        label = labels.confidence_factor_label(key)
        assert "_" not in label
        assert label[0].isupper()


def test_every_alert_type_has_a_product_label() -> None:
    for alert_type in (
        ALERT_UNOWNED_RISK,
        ALERT_MILESTONE_SLIP,
        ALERT_MILESTONE_DEPENDENCY,
        ALERT_BLOCKED_TASK,
        ALERT_OVERDUE_ACTION,
        ALERT_RESOURCE_OVERALLOCATION,
        ALERT_STALE_STATUS,
        ALERT_REQUIREMENT_VERIFICATION,
    ):
        label = labels.alert_type_label(alert_type)
        assert "_" not in label
        assert label != alert_type


def test_unmapped_key_still_produces_a_readable_label() -> None:
    """No raw snake_case may reach the UI even if the engines add a factor."""
    assert labels.health_factor_label("brand_new_factor") == "Brand New Factor"


def test_engine_messages_are_humanised() -> None:
    """Engine text can embed raw field names; they must be rewritten, not passed through."""
    assert labels.humanise("Risk R-1 has no mitigation_owner.") == (
        "Risk R-1 has no mitigation owner."
    )


def test_humanising_uses_product_labels_for_known_keys() -> None:
    assert labels.humanise("task_execution is low") == "Task Delivery is low"


def test_humanising_leaves_ordinary_text_untouched() -> None:
    assert labels.humanise("Milestone M-1 is forecast to slip.") == (
        "Milestone M-1 is forecast to slip."
    )


def test_labels_are_distinct() -> None:
    values = list(labels.HEALTH_FACTOR_LABELS.values())
    assert len(values) == len(set(values))


# ------------------------------------------------------------------ no vocabulary leaks
def _human_text(payload: object) -> list[str]:
    """Collect every string that a person would read, ignoring machine field names."""
    collected: list[str] = []

    def walk(node: object, key: str | None) -> None:
        if isinstance(node, dict):
            for child_key, value in node.items():
                walk(value, child_key)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, str) and key in {
            "label",
            "description",
            "title",
            "explanation",
            "message",
            "recommended_next_step",
            "score_impact_description",
            "factor_label",
            "alert_type_label",
            "remediation_hint",
        }:
            collected.append(node)

    walk(payload, None)
    return collected


def test_health_response_shows_no_internal_factor_keys(client: TestClient) -> None:
    payload = client.get(url("/analytics/projects/P-002/health")).json()
    for text in _human_text(payload):
        assert not _SNAKE_CASE.search(text), text


def test_alerts_show_no_internal_vocabulary(client: TestClient) -> None:
    for alert in client.get(url("/analytics/alerts")).json():
        assert not _SNAKE_CASE.search(alert["title"]), alert["title"]
        assert alert["alert_type_label"] != alert["alert_type"]


def test_confidence_response_shows_no_internal_factor_keys(client: TestClient) -> None:
    payload = client.get(url("/analytics/projects/P-002/confidence")).json()
    for text in _human_text(payload):
        assert not _SNAKE_CASE.search(text), text


def test_machine_keys_are_still_available_for_clients(client: TestClient) -> None:
    """The raw key stays on the payload for filtering; only displayed text is translated."""
    factors = client.get(url("/analytics/projects/P-002/health")).json()["factors"]
    assert {factor["key"] for factor in factors} == set(HEALTH_FACTORS)


# ------------------------------------------------------------------ evidence everywhere
def test_every_scored_conclusion_carries_evidence(client: TestClient) -> None:
    health = client.get(url("/analytics/projects/P-002/health")).json()
    confidence = client.get(url("/analytics/projects/P-002/confidence")).json()
    assert health["source_ids"]
    assert confidence["source_ids"]


def test_every_critical_driver_cites_records(client: TestClient) -> None:
    for project_id in ("P-002", "P-007"):
        drivers = client.get(url(f"/analytics/projects/{project_id}/health")).json()[
            "critical_drivers"
        ]
        for driver in drivers:
            assert driver["source_ids"], driver


def test_every_data_quality_issue_cites_records(client: TestClient) -> None:
    for project_id in ("P-002", "P-007"):
        issues = client.get(url(f"/analytics/projects/{project_id}/confidence")).json()[
            "data_quality_issues"
        ]
        for issue in issues:
            assert issue["source_ids"], issue


def test_scored_results_declare_their_limitations(client: TestClient) -> None:
    health = client.get(url("/analytics/projects/P-002/health")).json()
    assert health["assumptions_or_limitations"]


def test_source_ids_reference_real_records(client: TestClient, csv_portfolio) -> None:
    """Every cited identifier must exist in the portfolio."""
    known = {project["project_id"] for project in client.get(url("/projects")).json()}
    known |= {row["task_id"] for row in client.get(url("/tasks")).json()}
    known |= {row["risk_id"] for row in client.get(url("/risks")).json()}
    known |= {row["milestone_id"] for row in client.get(url("/milestones")).json()}
    known |= {row["action_id"] for row in client.get(url("/actions")).json()}
    known |= {row["requirement_id"] for row in client.get(url("/requirements")).json()}
    known |= {row.resource_id for row in csv_portfolio.resources}
    known |= {row.dependency_id for row in csv_portfolio.dependencies}
    known |= {row.test_case_id for row in csv_portfolio.test_cases}
    known |= {row.trace_link_id for row in csv_portfolio.trace_links}

    for alert in client.get(url("/analytics/alerts")).json():
        for source_id in alert["source_ids"]:
            assert source_id in known, source_id


# ------------------------------------------------------------------ AI boundaries
def test_copilot_routes_only_touch_conversations(client: TestClient) -> None:
    """Ask EPOS may manage a user's own conversation history and nothing else."""
    paths = client.get("/openapi.json").json()["paths"]
    mutating = {"post", "patch", "put", "delete"}
    for path, operations in paths.items():
        if "/copilot/" not in path:
            continue
        for method in operations:
            if method in mutating:
                assert path.endswith("/ask") or "/conversations" in path, (path, method)


def test_ask_is_the_only_copilot_route_that_reaches_the_model(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    copilot_posts = [path for path, ops in paths.items() if "/copilot/" in path and "post" in ops]
    assert copilot_posts == [url("/copilot/ask")]


def test_asking_a_question_changes_no_workspace_record(client: TestClient) -> None:
    """The one AI route must leave every business record untouched."""
    before = {
        surface: client.get(url(f"/{surface}")).json()
        for surface in ("projects", "tasks", "risks", "milestones", "requirements")
    }
    client.post(url("/copilot/ask"), json={"question": "Which risks have no owner?"})
    after = {
        surface: client.get(url(f"/{surface}")).json()
        for surface in ("projects", "tasks", "risks", "milestones", "requirements")
    }
    assert after == before


def test_openapi_documents_the_governance_position(client: TestClient) -> None:
    description = client.get("/openapi.json").json()["info"]["description"]
    assert "calculates every score" in description.lower()
