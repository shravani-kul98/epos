"""SQLite engine and session management for EPOS Next."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import weakref
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.script.revision import RevisionError
from alembic.util import CommandError
from sqlalchemy import Engine, event, inspect, text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

# Importing the models registers every table on SQLModel.metadata.
from api import models as _models  # noqa: F401
from api import settings
from src import config

DEFAULT_DATABASE_PATH: Path = config.PROJECT_ROOT / "data" / "epos_next.db"
DATABASE_URL_ENV_VAR = "EPOS_DATABASE_URL"
# Hosted providers and Vercel supply this name.
STANDARD_DATABASE_URL_ENV_VAR = "DATABASE_URL"
_POSTGRES_SCHEMES = ("postgresql+psycopg://", "postgresql://", "postgres://")

_engine: Engine | None = None
_FROZEN_BASELINE_REVISION = "20260316_0002"
# Serialises schema upgrades across every instance that shares one PostgreSQL database.
_UPGRADE_LOCK_KEY = 0x4550_4F53
_UPGRADE_THREAD_LOCK = threading.Lock()
_checked_engines: weakref.WeakSet[Engine] = weakref.WeakSet()
_NEON_REGION = re.compile(
    r"\.(?P<region>[a-z]{2}-[a-z]+-\d)\.aws\.neon\.tech$|\.(?P<azure>[a-z]+\d?)\.azure\.neon\.tech$"
)
logger = logging.getLogger(__name__)


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    """Enable referential integrity for each SQLite connection."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Install SQLite's per-connection foreign-key pragma on an engine."""
    if engine.dialect.name == "sqlite" and not event.contains(
        engine, "connect", _enable_sqlite_foreign_keys
    ):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)


def normalise_database_url(url: str) -> str:
    """Return a SQLAlchemy URL for ``url``, mapping provider schemes onto the installed driver.

    Hosted PostgreSQL providers hand out ``postgres://`` or ``postgresql://``, which SQLAlchemy
    resolves to psycopg2. EPOS ships psycopg 3, so the driver is named explicitly. The credentials
    inside the URL are never inspected, logged or altered.
    """
    for scheme in ("postgres://", "postgresql://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url[len(scheme) :]
    return url


def is_postgres_url(url: str) -> bool:
    """Whether ``url`` addresses a PostgreSQL server."""
    return url.startswith(_POSTGRES_SCHEMES)


def database_url() -> str:
    """Return the configured database URL, defaulting to a local SQLite file.

    ``EPOS_DATABASE_URL`` wins when both names are present, so an explicit EPOS setting is never
    silently overridden by a platform-provided one.
    """
    override = os.getenv(DATABASE_URL_ENV_VAR) or os.getenv(STANDARD_DATABASE_URL_ENV_VAR)
    if override and override.strip():
        return normalise_database_url(override.strip())
    return f"sqlite:///{DEFAULT_DATABASE_PATH}"


def _reject_sqlite_in_production(url: str) -> None:
    """A serverless filesystem is ephemeral, so a SQLite file is never durable storage."""
    if settings.is_production() and not is_postgres_url(url):
        raise RuntimeError(
            f"{STANDARD_DATABASE_URL_ENV_VAR} must address a PostgreSQL database when "
            f"{settings.ENVIRONMENT_ENV_VAR} is production; local file storage is not durable."
        )


def build_engine(url: str | None = None) -> Engine:
    """Create an engine for SQLite or PostgreSQL.

    SQLite needs ``check_same_thread`` disabled because FastAPI serves requests from a thread
    pool. PostgreSQL rejects that argument, so connection settings are chosen per dialect.
    """
    target = normalise_database_url(url or database_url())
    _reject_sqlite_in_production(target)

    if is_postgres_url(target):
        # A warm serverless instance serves many requests, so a small pool saves a network
        # handshake per request. Connections are verified before use and recycled well within
        # provider idle limits. Automatic server-side preparation is off because transaction
        # poolers do not keep prepared statements between transactions.
        engine = create_engine(
            target,
            echo=False,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=4,
            pool_recycle=240,
            pool_timeout=15,
            connect_args={"prepare_threshold": None},
        )
    else:
        if target.startswith("sqlite:///") and target != "sqlite:///:memory:":
            Path(target.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(target, echo=False, connect_args={"check_same_thread": False})

    enable_sqlite_foreign_keys(engine)
    return engine


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def set_engine(engine: Engine) -> None:
    """Install an engine explicitly.

    Tests use this to point the whole application at an isolated database, so no test can create
    or write to the real database file.
    """
    global _engine
    enable_sqlite_foreign_keys(engine)
    _engine = engine


def reset_engine() -> None:
    """Drop the cached engine so the next call rebuilds it. Used by tests."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def _alembic_config(connection: Connection) -> Config:
    config = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
    config.attributes["connection"] = connection
    return config


def _table_signature(connection: Connection, table_name: str) -> dict[str, object]:
    inspector = inspect(connection)
    columns = tuple(
        sorted(
            (
                column["name"],
                str(column["type"]).upper(),
                bool(column["nullable"]),
            )
            for column in inspector.get_columns(table_name)
        )
    )
    primary_key = tuple(inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
    indexes = tuple(
        sorted(
            (
                index.get("name"),
                tuple(index.get("column_names") or ()),
                bool(index.get("unique")),
            )
            for index in inspector.get_indexes(table_name)
        )
    )
    unique_constraints = tuple(
        sorted(
            tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints(table_name)
        )
    )
    foreign_keys = tuple(
        sorted(
            (
                tuple(foreign_key.get("constrained_columns") or ()),
                foreign_key.get("referred_table"),
                tuple(foreign_key.get("referred_columns") or ()),
                tuple(sorted((foreign_key.get("options") or {}).items())),
            )
            for foreign_key in inspector.get_foreign_keys(table_name)
        )
    )
    checks = tuple(
        sorted(
            " ".join(str(check.get("sqltext") or "").split())
            for check in inspector.get_check_constraints(table_name)
        )
    )
    return {
        "columns": columns,
        "primary key": primary_key,
        "indexes": indexes,
        "unique constraints": unique_constraints,
        "foreign keys": foreign_keys,
        "check constraints": checks,
    }


def _schema_signature(connection: Connection) -> dict[str, dict[str, object]]:
    table_names = set(inspect(connection).get_table_names()) - {"alembic_version"}
    return {
        table_name: _table_signature(connection, table_name) for table_name in sorted(table_names)
    }


def _unversioned_nonempty(engine: Engine) -> bool:
    with engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())
        business_tables = table_names - {"alembic_version"}
        if not business_tables:
            return False
        if "alembic_version" not in table_names:
            return True
        return (
            connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
            is None
        )


def _frozen_baseline_signature() -> dict[str, dict[str, object]]:
    reference = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    enable_sqlite_foreign_keys(reference)
    try:
        with reference.begin() as connection:
            command.upgrade(_alembic_config(connection), _FROZEN_BASELINE_REVISION)
            return _schema_signature(connection)
    finally:
        reference.dispose()


def _validate_legacy_schema(engine: Engine) -> None:
    expected = _frozen_baseline_signature()
    with engine.connect() as connection:
        actual = _schema_signature(connection)

    expected_tables = set(expected)
    actual_tables = set(actual)
    missing = sorted(expected_tables - actual_tables)
    extra = sorted(actual_tables - expected_tables)
    if missing or extra:
        table_issues = []
        if missing:
            table_issues.append("missing tables: " + ", ".join(missing))
        if extra:
            table_issues.append("unexpected tables: " + ", ".join(extra))
        raise RuntimeError("Cannot adopt a partial pre-Alembic schema; " + "; ".join(table_issues))

    issues: list[str] = []
    for table_name in sorted(expected_tables & actual_tables):
        for component, expected_value in expected[table_name].items():
            if actual[table_name][component] != expected_value:
                issues.append(f"{table_name} {component} do not match the frozen baseline")
    if issues:
        raise RuntimeError("Cannot adopt an invalid pre-Alembic schema; " + "; ".join(issues))


def upgrade_db(engine: Engine, revision: str = "head") -> None:
    """Upgrade an engine to a governed schema revision."""
    target = engine
    enable_sqlite_foreign_keys(target)
    if _unversioned_nonempty(target):
        _validate_legacy_schema(target)
    with target.begin() as connection:
        if connection.dialect.name == "postgresql":
            # A schema change waits for running reads; it must never queue behind them forever.
            connection.execute(text("SET LOCAL lock_timeout = '15s'"))
            # Transaction-scoped, so it holds through a transaction pooler such as Neon's.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": _UPGRADE_LOCK_KEY}
            )
        command.upgrade(_alembic_config(connection), revision)


def init_db(engine: Engine | None = None) -> None:
    """Upgrade the database to the latest governed schema revision."""
    upgrade_db(engine or get_engine())


@lru_cache(maxsize=1)
def expected_schema_revision() -> str | None:
    """The migration head this code was written against."""
    config = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
    return ScriptDirectory.from_config(config).get_current_head()


def schema_is_current(connection: Connection) -> bool:
    """Whether the connected database is at the revision this code expects.

    A release can reach a database that was never migrated. Reporting that explicitly is cheaper
    than discovering it through failed writes.
    """
    return current_schema_revision(connection) == expected_schema_revision()


def current_schema_revision(connection: Connection) -> str | None:
    """The revision recorded in the database, or None when it is empty or unversioned."""
    if "alembic_version" not in inspect(connection).get_table_names():
        return None
    row = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
    return None if row is None else str(row[0])


@dataclass(frozen=True)
class PendingRevision:
    """One governed migration the database has not received yet."""

    revision: str
    description: str


@dataclass(frozen=True)
class SchemaStatus:
    """Where the connected database stands against this release. Carries no connection detail."""

    dialect: str
    current_revision: str | None
    expected_revision: str | None
    pending: tuple[PendingRevision, ...] = field(default_factory=tuple)
    round_trip_ms: float | None = None
    database_region: str | None = None
    application_region: str | None = None

    @property
    def is_current(self) -> bool:
        return self.current_revision is not None and self.current_revision == self.expected_revision

    @property
    def can_upgrade(self) -> bool:
        """Only a versioned database on a known revision is upgraded; nothing is initialised."""
        return self.current_revision is not None and bool(self.pending)


def _pending_revisions(current: str | None) -> tuple[PendingRevision, ...]:
    if current is None:
        return ()
    scripts = ScriptDirectory.from_config(
        Config(Path(__file__).resolve().parents[1] / "alembic.ini")
    )
    head = scripts.get_current_head()
    if head is None or current == head:
        return ()
    try:
        steps = list(scripts.iterate_revisions(head, current))
    except RevisionError:
        logger.warning("The recorded schema revision is not part of this release's history.")
        return ()
    return tuple(
        PendingRevision(revision=step.revision, description=(step.doc or "").strip())
        for step in reversed(steps)
    )


def database_region(url: URL) -> str | None:
    """The hosting region named in a managed database host, never the host or credentials."""
    match = _NEON_REGION.search(url.host or "")
    if match is None:
        return None
    return match.group("region") or match.group("azure")


def schema_status(engine: Engine | None = None, *, measure: bool = False) -> SchemaStatus:
    """Report the recorded and expected revisions, and optionally one measured round trip."""
    target = engine or get_engine()
    round_trip: float | None = None
    with target.connect() as connection:
        current = current_schema_revision(connection)
        if measure:
            started = time.perf_counter()
            connection.execute(text("SELECT 1")).scalar_one()
            round_trip = round((time.perf_counter() - started) * 1000, 1)
    return SchemaStatus(
        dialect=target.dialect.name,
        current_revision=current,
        expected_revision=expected_schema_revision(),
        pending=_pending_revisions(current),
        round_trip_ms=round_trip,
        database_region=database_region(target.url),
        application_region=os.getenv("VERCEL_REGION") or None,
    )


def apply_pending_upgrades(engine: Engine | None = None) -> SchemaStatus:
    """Apply every governed migration the database is missing, one instance at a time.

    PostgreSQL instances queue on an advisory lock held by the migration transaction, and whoever
    acquires it second finds nothing left to do. Empty or unversioned databases are refused:
    initialising one stays a deliberate, documented step.
    """
    target = engine or get_engine()
    with _UPGRADE_THREAD_LOCK:
        before = schema_status(target)
        if not before.can_upgrade:
            return before
        upgrade_db(target)
        after = schema_status(target)
        logger.info(
            "Upgraded the database schema from %s to %s.",
            before.current_revision,
            after.current_revision,
        )
        return after


def ensure_schema_upgraded(engine: Engine) -> None:
    """Bring a versioned database up to this release once per engine, when enabled.

    A failure is logged and left for the administrator's status panel rather than blocking every
    request: reads that do not touch new columns keep working.
    """
    if engine in _checked_engines:
        return
    _checked_engines.add(engine)
    if not settings.schema_auto_upgrade():
        return
    try:
        if schema_status(engine).can_upgrade:
            apply_pending_upgrades(engine)
    except (SQLAlchemyError, CommandError, RuntimeError):
        # Reported through the administrator's status panel; never fatal for the request.
        logger.exception("Automatic schema upgrade failed; an administrator can retry it.")


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    engine = get_engine()
    ensure_schema_upgraded(engine)
    with Session(engine) as session:
        yield session
