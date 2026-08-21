"""Alembic environment for EPOS persistence revisions."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

import api.models  # noqa: F401
from api.database import database_url, enable_sqlite_foreign_keys, normalise_database_url

config = context.config
if config.config_file_name is not None:
    # The API runs migrations at startup; the default would silently disable every application
    # logger created before this point, including AI failure warnings.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata


def _migration_url() -> str:
    """The database the Alembic command line migrates.

    ``EPOS_ALEMBIC_DATABASE_URL`` names a database explicitly. Otherwise the command line reads the
    same variables as the API, so ``alembic upgrade head`` migrates the database the API opens.
    The URL is passed straight to SQLAlchemy rather than through the ini parser, which would
    misread the ``%`` escapes of an encoded password.
    """
    explicit = os.getenv("EPOS_ALEMBIC_DATABASE_URL", "").strip()
    return normalise_database_url(explicit) if explicit else database_url()


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(
        url=_migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a configured Engine or Connection."""
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        context.configure(
            connection=supplied_connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = create_engine(_migration_url(), poolclass=pool.NullPool)
    # The API migrates with foreign keys enforced; the command line must behave identically.
    enable_sqlite_foreign_keys(connectable)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
