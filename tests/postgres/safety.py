"""Guards for destructive PostgreSQL integration tests."""

from urllib.parse import urlparse

POSTGRES_TEST_DATABASE_URL_ENV = "ECI_POSTGRES_TEST_DATABASE_URL"
_REQUIRED_SCHEME = "postgresql+psycopg"
_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1"})
_TEST_DATABASE_MARKER = "eci_test"

_UNSAFE_SCHEME = (
    "PostgreSQL integration tests require ECI_POSTGRES_TEST_DATABASE_URL "
    "to use postgresql+psycopg."
)
_UNSAFE_HOST = (
    "PostgreSQL integration tests require ECI_POSTGRES_TEST_DATABASE_URL "
    "to use host localhost or 127.0.0.1."
)
_UNSAFE_DATABASE = (
    "PostgreSQL integration tests require the database name to contain eci_test."
)


class UnsafePostgresTestDatabaseUrlError(RuntimeError):
    """Raised when a PostgreSQL test URL is present but not a disposable test database."""


def require_safe_postgres_test_database_url(url: str) -> str:
    """Validate a PostgreSQL test URL without connecting or echoing credentials."""
    stripped = url.strip()
    parsed = urlparse(stripped)
    scheme = parsed.scheme.lower()
    if scheme != _REQUIRED_SCHEME or not parsed.netloc:
        raise UnsafePostgresTestDatabaseUrlError(_UNSAFE_SCHEME)
    hostname = (parsed.hostname or "").lower()
    if hostname not in _ALLOWED_HOSTS:
        raise UnsafePostgresTestDatabaseUrlError(_UNSAFE_HOST)
    database_name = parsed.path.lstrip("/").split("/")[0]
    if _TEST_DATABASE_MARKER not in database_name:
        raise UnsafePostgresTestDatabaseUrlError(_UNSAFE_DATABASE)
    return stripped
