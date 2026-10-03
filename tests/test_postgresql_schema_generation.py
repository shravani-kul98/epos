"""PostgreSQL deployment SQL must include database-native types before dependent tables."""

from __future__ import annotations

import re

from scripts import generate_postgresql_schema as generator


def test_named_enums_are_created_before_tables_that_use_them() -> None:
    sql = generator._render_schema()

    enum_position = sql.index("CREATE TYPE role AS ENUM")
    users_position = sql.index("CREATE TABLE IF NOT EXISTS users")

    assert enum_position < users_position
    assert "WHEN duplicate_object THEN NULL" in sql
    assert sql.count("CREATE TYPE role AS ENUM") == 1


def test_role_enum_matches_the_authoritative_application_values() -> None:
    sql = generator._render_schema()
    enum = re.search(r"CREATE TYPE role AS ENUM \(([^)]+)\)", sql)

    assert enum is not None
    assert enum.group(1) == (
        "'EXECUTIVE', 'ENGINEER', 'ENGINEERING_LEAD', 'REQUIREMENTS_MANAGER', "
        "'PROJECT_MANAGER', 'PMO_ANALYST', 'ADMINISTRATOR'"
    )


def test_schema_remains_non_destructive() -> None:
    sql = generator._render_schema()

    assert re.search(r"\b(DROP\s+(TABLE|SCHEMA|DATABASE)|TRUNCATE|DELETE\s+FROM)\b", sql) is None


def test_boolean_check_constraints_use_postgresql_boolean_syntax() -> None:
    sql = generator._render_schema()

    assert "evidence_required IS FALSE" in sql
    assert (
        re.search(
            r"\b(?:is_active|is_mandatory|evidence_required|is_blocked)\s*" r"(?:=|!=|<>)\s*[01]\b",
            sql,
        )
        is None
    )


def test_schema_contains_no_sqlite_only_ddl() -> None:
    sql = generator._render_schema()

    assert "AUTOINCREMENT" not in sql.upper()
    assert re.search(r"\bDATETIME\b", sql, re.IGNORECASE) is None
