"""Tests for CSV loading, validation and referential integrity."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data_loader import PortfolioData, load_portfolio
from src.validators import DataValidationError


def test_load_real_portfolio_counts(portfolio: PortfolioData) -> None:
    """The shipped workspace loads, and every collection carries records."""
    assert portfolio.projects
    for name in (
        "milestones",
        "tasks",
        "risks",
        "dependencies",
        "requirements",
        "test_cases",
        "trace_links",
        "change_requests",
    ):
        assert getattr(portfolio, name), f"{name} is empty"


def test_every_record_belongs_to_a_known_project(portfolio: PortfolioData) -> None:
    """An orphaned row would be scored against a project that does not exist."""
    known = set(portfolio.project_ids)
    for name in (
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
        orphans = [r.project_id for r in getattr(portfolio, name) if r.project_id not in known]
        assert orphans == [], f"{name} references unknown projects: {sorted(set(orphans))}"


def test_identifiers_are_unique_within_each_collection(portfolio: PortfolioData) -> None:
    for name, key in (
        ("projects", "project_id"),
        ("milestones", "milestone_id"),
        ("tasks", "task_id"),
        ("risks", "risk_id"),
        ("requirements", "requirement_id"),
        ("change_requests", "change_request_id"),
    ):
        ids = [getattr(row, key) for row in getattr(portfolio, name)]
        assert len(ids) == len(set(ids)), f"{name} contains duplicate identifiers"


def test_the_shipped_workspace_has_no_status_anomalies(portfolio: PortfolioData) -> None:
    """Unrecognised status values silently weaken confidence scoring."""
    assert portfolio.status_anomalies == []


def test_optional_blank_becomes_none(portfolio: PortfolioData) -> None:
    unowned = next(r for r in portfolio.risks if r.risk_id == "R-2001")
    assert unowned.mitigation_owner is None


def test_missing_required_column_raises(temp_data_dir: Path) -> None:
    projects = temp_data_dir / "projects.csv"
    lines = projects.read_text(encoding="utf-8").splitlines()
    # Drop the 'domain' column from header and every row.
    header = lines[0].split(",")
    drop_index = header.index("domain")
    rewritten = [
        ",".join(part for i, part in enumerate(line.split(",")) if i != drop_index)
        for line in lines
    ]
    projects.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

    with pytest.raises(DataValidationError) as exc:
        load_portfolio(temp_data_dir)
    assert any("missing required column 'domain'" in issue for issue in exc.value.issues)


def test_duplicate_id_raises(temp_data_dir: Path) -> None:
    projects = temp_data_dir / "projects.csv"
    with projects.open("a", encoding="utf-8") as handle:
        handle.write(
            "P-002,Duplicate,Sustainability,Alex Morgan,2025-09-01,2026-06-30,"
            "2026-09-15,2026-08-20,Execution,High\n"
        )

    with pytest.raises(DataValidationError) as exc:
        load_portfolio(temp_data_dir)
    assert any("duplicate id 'P-002'" in issue for issue in exc.value.issues)


def test_unknown_project_reference_raises(temp_data_dir: Path) -> None:
    milestones = temp_data_dir / "milestones.csv"
    with milestones.open("a", encoding="utf-8") as handle:
        handle.write("M-999,P-999,Orphan milestone,2026-01-01,2026-01-01,Planned,Low,Nobody\n")

    with pytest.raises(DataValidationError) as exc:
        load_portfolio(temp_data_dir)
    assert any("references unknown project_id" in issue for issue in exc.value.issues)


def test_task_milestone_must_belong_to_the_same_project(temp_data_dir: Path) -> None:
    tasks = temp_data_dir / "tasks.csv"
    with tasks.open("a", encoding="utf-8") as handle:
        handle.write(
            "T-999,P-002,M-701,Cross-project hierarchy probe,Nobody,Not Started,"
            "2026-10-01,2026-10-01,0,FALSE,2026-08-27\n"
        )

    with pytest.raises(DataValidationError) as exc:
        load_portfolio(temp_data_dir)
    assert any(
        "task 'T-999' references milestone 'M-701' outside project 'P-002'" in issue
        for issue in exc.value.issues
    )


def test_change_request_requirement_must_belong_to_the_same_project(
    temp_data_dir: Path,
) -> None:
    change_requests = temp_data_dir / "change_requests.csv"
    with change_requests.open("a", encoding="utf-8") as handle:
        handle.write(
            "CR-999,P-002,REQ-7001,Cross-project requirement probe,Integrity test,"
            "High,Proposed,Synthetic Requester,2026-08-27\n"
        )

    with pytest.raises(DataValidationError) as exc:
        load_portfolio(temp_data_dir)
    assert any(
        "change request 'CR-999' references requirement 'REQ-7001' outside project 'P-002'" in issue
        for issue in exc.value.issues
    )


def test_dependency_endpoint_must_belong_to_the_same_project(temp_data_dir: Path) -> None:
    dependencies = temp_data_dir / "dependencies.csv"
    with dependencies.open("a", encoding="utf-8") as handle:
        handle.write(
            "D-999,P-002,Task,T-7001,Milestone,M-202,Cross-project probe," "On Track,0,High\n"
        )

    with pytest.raises(DataValidationError) as exc:
        load_portfolio(temp_data_dir)
    assert any(
        "dependency 'D-999' references Task 'T-7001' outside project 'P-002'" in issue
        for issue in exc.value.issues
    )


def test_dependency_network_must_be_acyclic(temp_data_dir: Path) -> None:
    dependencies = temp_data_dir / "dependencies.csv"
    with dependencies.open("a", encoding="utf-8") as handle:
        handle.write("D-999,P-002,Task,T-2002,Task,T-2001,Cycle probe,On Track,0,High\n")

    with pytest.raises(DataValidationError) as exc:
        load_portfolio(temp_data_dir)
    assert any("D-2002, D-999" in issue for issue in exc.value.issues)


def test_invalid_row_value_raises(temp_data_dir: Path) -> None:
    risks = temp_data_dir / "risks.csv"
    with risks.open("a", encoding="utf-8") as handle:
        # impact 9 is outside the allowed 1–5 range.
        handle.write("R-9999,P-002,Bad risk,3,9,Open,,Not Started,2026-09-30\n")

    with pytest.raises(DataValidationError):
        load_portfolio(temp_data_dir)
