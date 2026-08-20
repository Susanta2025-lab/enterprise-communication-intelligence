"""Unit tests for the dedicated PostgreSQL test URL safety guard."""

import pytest

from tests.postgres.safety import (
    UnsafePostgresTestDatabaseUrlError,
    require_safe_postgres_test_database_url,
)

_VALID = "postgresql+psycopg://eci_test:eci_test@localhost:5432/eci_test"


def test_localhost_psycopg_eci_test_url_is_accepted() -> None:
    """The GitHub service-container URL shape is accepted without connecting."""
    assert require_safe_postgres_test_database_url(f"  {_VALID}  ") == _VALID


def test_loopback_host_is_accepted() -> None:
    """127.0.0.1 is an allowed host for the current service-container design."""
    url = "postgresql+psycopg://eci_test:eci_test@127.0.0.1:5432/eci_test"
    assert require_safe_postgres_test_database_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://eci_test:eci_test@localhost:5432/eci_test",
        "sqlite+pysqlite:///:memory:",
        "postgresql+psycopg://",
    ],
)
def test_non_psycopg_url_is_rejected(url: str) -> None:
    """Destructive tests must not run against a non-psycopg URL."""
    with pytest.raises(UnsafePostgresTestDatabaseUrlError, match="postgresql\\+psycopg"):
        require_safe_postgres_test_database_url(url)


def test_non_local_host_is_rejected() -> None:
    """Remote hosts are not valid for destructive migration tests."""
    url = "postgresql+psycopg://eci_test:supersecret@db.internal.example:5432/eci_test"
    with pytest.raises(UnsafePostgresTestDatabaseUrlError, match="localhost"):
        require_safe_postgres_test_database_url(url)
    with pytest.raises(UnsafePostgresTestDatabaseUrlError) as exc_info:
        require_safe_postgres_test_database_url(url)
    assert "supersecret" not in str(exc_info.value)
    assert "db.internal" not in str(exc_info.value)


def test_database_name_must_contain_eci_test() -> None:
    """The database name must advertise that it is a test database."""
    url = "postgresql+psycopg://eci_test:supersecret@localhost:5432/production"
    with pytest.raises(UnsafePostgresTestDatabaseUrlError, match="eci_test"):
        require_safe_postgres_test_database_url(url)
    with pytest.raises(UnsafePostgresTestDatabaseUrlError) as exc_info:
        require_safe_postgres_test_database_url(url)
    assert "supersecret" not in str(exc_info.value)
    assert "production" not in str(exc_info.value)
