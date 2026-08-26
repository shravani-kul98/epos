"""Deployment environment settings.

Values are read from the environment only. Nothing in this module logs, returns or echoes a
secret value; callers receive booleans, categories and exact origin strings only.
"""

from __future__ import annotations

import os
from typing import Final

ENVIRONMENT_ENV_VAR: Final[str] = "ENVIRONMENT"
ALLOWED_ORIGINS_ENV_VAR: Final[str] = "EPOS_ALLOWED_ORIGINS"
API_DOCS_ENV_VAR: Final[str] = "EPOS_ENABLE_API_DOCS"
STARTUP_MIGRATION_ENV_VAR: Final[str] = "EPOS_RUN_MIGRATIONS_ON_STARTUP"
SCHEMA_AUTO_UPGRADE_ENV_VAR: Final[str] = "EPOS_SCHEMA_AUTO_UPGRADE"
RATE_LIMITS_ENV_VAR: Final[str] = "EPOS_RATE_LIMITS"
SELF_REGISTRATION_ENV_VAR: Final[str] = "EPOS_SELF_REGISTRATION"
REGISTRATION_DOMAINS_ENV_VAR: Final[str] = "EPOS_REGISTRATION_EMAIL_DOMAINS"
INVITATION_ONLY_ENV_VAR: Final[str] = "EPOS_REGISTRATION_REQUIRES_INVITATION"
RATE_LIMIT_STORE_ENV_VAR: Final[str] = "EPOS_RATE_LIMIT_STORE"
RATE_LIMIT_STORE_MEMORY: Final[str] = "memory"
RATE_LIMIT_STORE_DATABASE: Final[str] = "database"
ASSISTANT_MODE_ENV_VAR: Final[str] = "EPOS_ASSISTANT_MODE"
ASSISTANT_AGENT: Final[str] = "agent"
ASSISTANT_CLASSIC: Final[str] = "classic"

PRODUCTION: Final[str] = "production"
DEVELOPMENT: Final[str] = "development"

# The Vite dev server, which is the only cross-origin caller outside production. Served from the
# API process the browser is same-origin and no CORS configuration applies at all.
DEVELOPMENT_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_FALSY: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})


def environment() -> str:
    """Return the deployment environment category, defaulting to development."""
    return (os.getenv(ENVIRONMENT_ENV_VAR) or DEVELOPMENT).strip().lower() or DEVELOPMENT


def is_production() -> bool:
    """Whether the process is running as a public production deployment."""
    return environment() == PRODUCTION


def _flag(name: str, default: bool) -> bool:
    """Read a boolean switch, falling back to ``default`` for absent or unrecognised values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return default


def allowed_origins() -> tuple[str, ...]:
    """Exact cross-origin browser origins permitted to call the API.

    Production defaults to none because the frontend is served from this same origin. A wildcard
    is discarded rather than honoured, so it can never be combined with credentialed requests.
    """
    configured = os.getenv(ALLOWED_ORIGINS_ENV_VAR)
    if configured:
        origins = dict.fromkeys(part.strip() for part in configured.split(",") if part.strip())
        return tuple(origin for origin in origins if origin != "*")
    return () if is_production() else DEVELOPMENT_ORIGINS


def api_docs_enabled() -> bool:
    """Whether the interactive API documentation is published. Off by default in production."""
    return _flag(API_DOCS_ENV_VAR, default=not is_production())


def run_migrations_on_startup() -> bool:
    """Whether the schema is upgraded during application startup.

    Never automatic in production: concurrent serverless cold starts must not race on schema
    changes. Production databases are initialised through the documented deployment procedure.
    """
    return _flag(STARTUP_MIGRATION_ENV_VAR, default=not is_production())


def schema_auto_upgrade() -> bool:
    """Whether a versioned database that is behind this release is upgraded on first use.

    On by default everywhere. The upgrade runs once per process under a database lock, applies
    only the governed Alembic migrations, and never initialises an empty or unversioned database.
    Administrators can also apply it from Team & Access when this switch is off.
    """
    return _flag(SCHEMA_AUTO_UPGRADE_ENV_VAR, default=True)


def rate_limits_enabled() -> bool:
    """Whether sign-in, registration and assistant request limits are enforced."""
    return _flag(RATE_LIMITS_ENV_VAR, default=True)


def self_registration_enabled() -> bool:
    """Whether anyone may create an account from the sign-up page."""
    return _flag(SELF_REGISTRATION_ENV_VAR, default=True)


def registration_email_domains() -> tuple[str, ...]:
    """Email domains allowed to self-register. Empty means any domain."""
    configured = os.getenv(REGISTRATION_DOMAINS_ENV_VAR) or ""
    domains = (part.strip().lower().lstrip("@") for part in configured.split(","))
    return tuple(dict.fromkeys(domain for domain in domains if domain))


def registration_requires_invitation() -> bool:
    """Whether new accounts need an administrator's invitation code."""
    return _flag(INVITATION_ONLY_ENV_VAR, default=False)


def assistant_mode() -> str:
    """How Ask EPOS reads a question: the model plans tool use, or the rule-based router does.

    Production defaults to the model-planned assistant. Elsewhere the rule-based router stays the
    default, so local runs and tests behave the same with or without an AI service.
    """
    configured = (os.getenv(ASSISTANT_MODE_ENV_VAR) or "").strip().lower()
    if configured in {ASSISTANT_AGENT, ASSISTANT_CLASSIC}:
        return configured
    return ASSISTANT_AGENT if is_production() else ASSISTANT_CLASSIC


def rate_limit_store() -> str:
    """Where request limits are counted. Production shares them through the database."""
    configured = (os.getenv(RATE_LIMIT_STORE_ENV_VAR) or "").strip().lower()
    if configured in {RATE_LIMIT_STORE_MEMORY, RATE_LIMIT_STORE_DATABASE}:
        return configured
    return RATE_LIMIT_STORE_DATABASE if is_production() else RATE_LIMIT_STORE_MEMORY
