"""Deployment configuration must fail closed in production.

Nothing here contacts a database, a network service or a real environment file. Every setting is
supplied through monkeypatched environment variables and removed again by pytest.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import settings
from api.database import build_engine, database_url, is_postgres_url, normalise_database_url
from api.main import API_PREFIX, create_app
from api.security import tokens

PRODUCTION_SECRET = "x" * 64


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a known, unconfigured environment."""
    for name in (
        settings.ENVIRONMENT_ENV_VAR,
        settings.ALLOWED_ORIGINS_ENV_VAR,
        settings.API_DOCS_ENV_VAR,
        settings.STARTUP_MIGRATION_ENV_VAR,
        "DATABASE_URL",
        "EPOS_DATABASE_URL",
        "JWT_SECRET",
        "EPOS_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(settings.ENVIRONMENT_ENV_VAR, "production")


class TestDatabaseUrl:
    @pytest.mark.parametrize(
        "supplied",
        ["postgres://user:pass@host:5432/db", "postgresql://user:pass@host:5432/db"],
    )
    def test_provider_schemes_use_the_installed_driver(self, supplied: str) -> None:
        assert normalise_database_url(supplied).startswith("postgresql+psycopg://")

    def test_an_explicit_driver_is_preserved(self) -> None:
        url = "postgresql+psycopg://user:pass@host:5432/db"
        assert normalise_database_url(url) == url

    def test_sqlite_is_left_alone(self) -> None:
        assert normalise_database_url("sqlite:///./local.db") == "sqlite:///./local.db"

    def test_the_standard_variable_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/db")
        assert is_postgres_url(database_url())

    def test_the_epos_variable_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/platform")
        monkeypatch.setenv("EPOS_DATABASE_URL", "postgresql://user:pass@host:5432/explicit")
        assert database_url().endswith("/explicit")

    def test_local_development_falls_back_to_sqlite(self) -> None:
        assert database_url().startswith("sqlite:///")

    def test_production_refuses_a_local_file_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _production(monkeypatch)
        with pytest.raises(RuntimeError) as error:
            build_engine("sqlite:///./local.db")
        assert "PostgreSQL" in str(error.value)

    def test_the_refusal_never_repeats_the_connection_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _production(monkeypatch)
        with pytest.raises(RuntimeError) as error:
            build_engine("sqlite:///./secret-looking-name.db")
        assert "secret-looking-name" not in str(error.value)

    def test_sqlite_remains_available_outside_production(self) -> None:
        assert build_engine("sqlite:///:memory:").dialect.name == "sqlite"


class TestSigningKey:
    def test_production_requires_a_configured_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        with pytest.raises(RuntimeError):
            tokens.signing_key()

    def test_production_rejects_a_short_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        monkeypatch.setenv("JWT_SECRET", "too-short")
        with pytest.raises(RuntimeError):
            tokens.signing_key()

    def test_production_accepts_a_sufficient_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        monkeypatch.setenv("JWT_SECRET", PRODUCTION_SECRET)
        assert tokens.signing_key() == PRODUCTION_SECRET

    def test_either_secret_name_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        monkeypatch.setenv("EPOS_SECRET_KEY", PRODUCTION_SECRET)
        assert tokens.signing_key() == PRODUCTION_SECRET

    def test_the_failure_never_reveals_a_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        monkeypatch.setenv("JWT_SECRET", "abcdefg")
        with pytest.raises(RuntimeError) as error:
            tokens.signing_key()
        assert "abcdefg" not in str(error.value)

    def test_local_development_still_works_without_configuration(self) -> None:
        assert len(tokens.signing_key()) > 20


class TestProductionSurface:
    def test_documentation_is_not_published(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        app = create_app()
        assert app.openapi_url is None
        assert app.docs_url is None
        assert app.redoc_url is None

    def test_documentation_is_available_locally(self) -> None:
        assert create_app().openapi_url == "/openapi.json"

    def test_startup_never_migrates_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        assert settings.run_migrations_on_startup() is False

    def test_startup_migrates_locally(self) -> None:
        assert settings.run_migrations_on_startup() is True

    def test_no_cross_origin_caller_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        assert settings.allowed_origins() == ()

    def test_development_keeps_the_dev_server_origins(self) -> None:
        assert settings.allowed_origins() == settings.DEVELOPMENT_ORIGINS

    def test_a_wildcard_origin_is_discarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        monkeypatch.setenv(settings.ALLOWED_ORIGINS_ENV_VAR, "*,https://example.com")
        assert settings.allowed_origins() == ("https://example.com",)

    def test_configured_origins_are_exact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _production(monkeypatch)
        monkeypatch.setenv(
            settings.ALLOWED_ORIGINS_ENV_VAR, "https://a.example.com, https://b.example.com"
        )
        assert settings.allowed_origins() == ("https://a.example.com", "https://b.example.com")


class TestReadiness:
    def test_readiness_answers_without_a_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(settings.STARTUP_MIGRATION_ENV_VAR, "false")
        monkeypatch.setenv("EPOS_DATABASE_URL", "sqlite:///:memory:")
        with TestClient(create_app()) as client:
            response = client.get(f"{API_PREFIX}/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_readiness_discloses_no_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(settings.STARTUP_MIGRATION_ENV_VAR, "false")
        monkeypatch.setenv("EPOS_DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("JWT_SECRET", PRODUCTION_SECRET)
        with TestClient(create_app()) as client:
            body = client.get(f"{API_PREFIX}/ready").text.lower()
        for leak in ("secret", "password", "sqlite", "://", PRODUCTION_SECRET.lower()):
            assert leak not in body
