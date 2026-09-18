"""Render the authoritative EPOS schema and starter workspace as PostgreSQL SQL.

No database is contacted. The DDL is compiled against SQLAlchemy's PostgreSQL dialect, and the
seed statements are read back from a throwaway in-memory SQLite database that has been migrated
by Alembic and populated through the application's own seeding code, so stored defaults such as
row versions and timestamps are real values rather than assumptions.

The generated schema is cross-checked against that migrated database, so it cannot silently drift
from the migration head.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Boolean, Engine, Enum, create_engine, inspect  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402
from sqlmodel import Session, SQLModel, select  # noqa: E402

from api.database import enable_sqlite_foreign_keys, init_db  # noqa: E402
from api.seed import _SEED_PLAN, seed_session  # noqa: E402
from src.data_loader import load_portfolio  # noqa: E402

HEAD_REVISION = "20260925_0018"
_DIALECT = postgresql.dialect()


def _migrated_sqlite() -> Engine:
    """An isolated in-memory database migrated to the authoritative head."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    enable_sqlite_foreign_keys(engine)
    init_db(engine)
    return engine


def _ordered_tables() -> list[Any]:
    """Every mapped table in dependency order, so foreign keys resolve on creation."""
    return list(SQLModel.metadata.sorted_tables)


def _render_enum_types() -> list[str]:
    """Create every named PostgreSQL enum before a table references it."""
    enums: dict[str, tuple[str, ...]] = {}
    for table in _ordered_tables():
        for column in table.columns:
            if isinstance(column.type, Enum) and column.type.name:
                values = tuple(column.type.enums)
                existing = enums.setdefault(column.type.name, values)
                if existing != values:
                    raise ValueError(f"conflicting definitions for enum '{column.type.name}'")

    statements: list[str] = []
    for name, values in sorted(enums.items()):
        quoted_values = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
        statements.extend(
            [
                f"-- Named enum required by mapped columns using type {name}.",
                "DO $$",
                "BEGIN",
                f"    CREATE TYPE {name} AS ENUM ({quoted_values});",
                "EXCEPTION",
                "    WHEN duplicate_object THEN NULL;",
                "END",
                "$$;",
                "",
            ]
        )
    return statements


def _postgresql_table_ddl(table: Any) -> str:
    """Compile one table and translate SQLite-style Boolean literals in string constraints."""
    statement = str(CreateTable(table, if_not_exists=True).compile(dialect=_DIALECT)).strip()
    for column in table.columns:
        if not isinstance(column.type, Boolean):
            continue
        name = re.escape(column.name)
        replacements = (
            (rf"\b{name}\s*=\s*0\b", f"{column.name} IS FALSE"),
            (rf"\b{name}\s*=\s*1\b", f"{column.name} IS TRUE"),
            (rf"\b{name}\s*(?:!=|<>)\s*0\b", f"{column.name} IS TRUE"),
            (rf"\b{name}\s*(?:!=|<>)\s*1\b", f"{column.name} IS FALSE"),
            (rf"\b0\s*=\s*{name}\b", f"{column.name} IS FALSE"),
            (rf"\b1\s*=\s*{name}\b", f"{column.name} IS TRUE"),
        )
        for pattern, replacement in replacements:
            statement = re.sub(pattern, replacement, statement)
    return statement


def _render_schema() -> str:
    lines = [
        "-- EPOS PostgreSQL schema",
        f"-- Generated from the Alembic migration head {HEAD_REVISION}.",
        "-- Creates tables only. It drops nothing and deletes nothing.",
        "",
        "BEGIN;",
        "",
    ]
    lines.extend(_render_enum_types())
    for table in _ordered_tables():
        statement = _postgresql_table_ddl(table)
        lines.append(f"{statement};")
        lines.append("")
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            index_sql = str(CreateIndex(index, if_not_exists=True).compile(dialect=_DIALECT))
            lines.append(f"{index_sql.strip()};")
        if table.indexes:
            lines.append("")

    lines += [
        "-- Record the migration head so Alembic recognises this database as up to date.",
        "CREATE TABLE IF NOT EXISTS alembic_version (",
        "    version_num VARCHAR(32) NOT NULL,",
        "    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)",
        ");",
        "",
        f"INSERT INTO alembic_version (version_num) VALUES ('{HEAD_REVISION}')",
        "    ON CONFLICT DO NOTHING;",
        "",
        "COMMIT;",
        "",
    ]
    return "\n".join(lines)


def _render_seed(engine: Engine) -> str:
    """Emit idempotent INSERT statements for the synthetic starter workspace."""
    lines = [
        "-- EPOS synthetic starter workspace",
        "-- Fictional demonstration data only. No real person, customer or employer is described.",
        "-- Idempotent: re-running inserts nothing new and overwrites nothing.",
        "-- Contains no user accounts, passwords or credentials.",
        "",
        "BEGIN;",
        "",
    ]
    with Session(engine) as session:
        for attribute, table_model in _SEED_PLAN:
            table = table_model.__table__
            rows = session.exec(select(table_model)).all()
            if not rows:
                continue
            lines.append(f"-- {attribute}: {len(rows)} records")
            for row in rows:
                values = {column.name: getattr(row, column.name) for column in table.columns}
                statement = pg_insert(table).values(**values).on_conflict_do_nothing()
                sql = statement.compile(dialect=_DIALECT, compile_kwargs={"literal_binds": True})
                lines.append(f"{str(sql).strip()};")
            lines.append("")

    lines += ["COMMIT;", ""]
    return "\n".join(lines)


def _verify_against_migration_head(engine: Engine) -> list[str]:
    """Compare mapped metadata with the migrated database, reporting any difference."""
    inspector = inspect(engine)
    live_tables = set(inspector.get_table_names()) - {"alembic_version"}
    mapped_tables = {table.name for table in _ordered_tables()}

    problems: list[str] = []
    for missing in sorted(mapped_tables - live_tables):
        problems.append(f"table '{missing}' is mapped but absent from the migrated database")
    for extra in sorted(live_tables - mapped_tables):
        problems.append(f"table '{extra}' exists in the migrated database but is not mapped")

    for name in sorted(mapped_tables & live_tables):
        live_columns = {column["name"] for column in inspector.get_columns(name)}
        mapped_columns = {column.name for column in SQLModel.metadata.tables[name].columns}
        for missing in sorted(mapped_columns - live_columns):
            problems.append(f"{name}.{missing} is mapped but absent after migration")
        for extra in sorted(live_columns - mapped_columns):
            problems.append(f"{name}.{extra} exists after migration but is not mapped")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="deployment/postgresql", type=Path)
    arguments = parser.parse_args()

    engine = _migrated_sqlite()
    try:
        problems = _verify_against_migration_head(engine)
        if problems:
            print("Schema verification failed:")
            for problem in problems:
                print(f"  - {problem}")
            return 1

        with Session(engine) as session:
            seed_session(session, load_portfolio())

        destination: Path = arguments.output
        destination.mkdir(parents=True, exist_ok=True)
        schema_file = destination / "001_schema.sql"
        seed_file = destination / "002_synthetic_seed.sql"
        schema_file.write_text(_render_schema(), encoding="utf-8")
        seed_file.write_text(_render_seed(engine), encoding="utf-8")
    finally:
        engine.dispose()

    tables = len(_ordered_tables())
    print(f"Verified mapped metadata against migration head {HEAD_REVISION}.")
    print(f"Wrote {schema_file} ({tables} tables).")
    print(f"Wrote {seed_file}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
