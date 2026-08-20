"""Resolve DATABASE_URL for Alembic without loading application Settings.

Migration execution needs a PostgreSQL URL. It does not need OIDC, AI, or
FastAPI configuration, and this helper never opens a connection.
"""

import os
from urllib.parse import urlparse

_REQUIRED = "DATABASE_URL is required for migrations."
_MUST_USE_POSTGRES = "Migration DATABASE_URL must use PostgreSQL with psycopg."
_POSTGRES_PSYCOPG_SCHEME = "postgresql+psycopg"


def resolve_migration_database_url() -> str:
    """Return a stripped PostgreSQL psycopg URL from DATABASE_URL.

    Raises:
        RuntimeError: when DATABASE_URL is missing, blank, or not PostgreSQL
            with psycopg. Messages never include the URL or credentials.
    """
    raw = os.environ.get("DATABASE_URL")
    if raw is None:
        raise RuntimeError(_REQUIRED)
    url = raw.strip()
    if not url:
        raise RuntimeError(_REQUIRED)

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme != _POSTGRES_PSYCOPG_SCHEME or not parsed.netloc:
        raise RuntimeError(_MUST_USE_POSTGRES)
    return url
