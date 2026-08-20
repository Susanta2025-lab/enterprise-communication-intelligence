"""Offline tests for Alembic DATABASE_URL resolution. Do not connect."""

from pathlib import Path

import pytest

from app.infrastructure.storage.migration_config import resolve_migration_database_url

_VALID = "postgresql+psycopg://eci_test:eci_test_secret@localhost:5432/eci_test"
_REQUIRED = "DATABASE_URL is required for migrations."
_MUST_USE_POSTGRES = "Migration DATABASE_URL must use PostgreSQL with psycopg."
_MODULE = (
    Path(__file__).resolve().parents[4]
    / "app"
    / "infrastructure"
    / "storage"
    / "migration_config.py"
)


def test_migration_config_module_is_isolated() -> None:
    """The resolver must not import Settings, FastAPI, or OIDC configuration."""
    source = _MODULE.read_text(encoding="utf-8")
    assert "get_settings" not in source
    assert "from app.core.config" not in source
    assert "from fastapi" not in source
    assert "import fastapi" not in source
    assert "OIDC_ISSUER" not in source
    assert "create_engine" not in source
    assert "sqlalchemy" not in source.lower()


def test_resolve_migration_url_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Surrounding whitespace is stripped without opening a connection."""
    monkeypatch.setenv("DATABASE_URL", f"  {_VALID}  ")
    assert resolve_migration_database_url() == _VALID


def test_resolve_migration_url_does_not_require_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production OIDC settings are irrelevant to migration URL resolution."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", _VALID)
    assert resolve_migration_database_url() == _VALID


def test_missing_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing DATABASE_URL fails with a generic message."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match=_REQUIRED):
        resolve_migration_database_url()


def test_blank_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace-only DATABASE_URL is treated as missing."""
    monkeypatch.setenv("DATABASE_URL", "   ")
    with pytest.raises(RuntimeError, match=_REQUIRED):
        resolve_migration_database_url()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+pysqlite:///:memory:",
        "postgresql://eci_test:eci_test_secret@localhost:5432/eci_test",
        "postgresql+psycopg://",
        "mysql://eci_test:eci_test_secret@localhost:3306/eci_test",
    ],
)
def test_non_postgres_psycopg_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    """Only postgresql+psycopg URLs with a network location are accepted."""
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(RuntimeError, match=_MUST_USE_POSTGRES):
        resolve_migration_database_url()


def test_rejected_url_does_not_echo_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Migration configuration errors must not include credentials or the URL."""
    secret = "eci-migration-password-sentinel"
    monkeypatch.setenv("DATABASE_URL", f"postgresql://eci:{secret}@localhost:5432/eci")
    with pytest.raises(RuntimeError) as exc_info:
        resolve_migration_database_url()
    message = str(exc_info.value)
    assert message == _MUST_USE_POSTGRES
    assert secret not in message
    assert "localhost" not in message
    assert "postgresql://" not in message
