"""Inspect Alembic revision and application tables for PostgreSQL CI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_TABLES = frozenset(
    {"users", "external_identities", "analyses", "connector_accounts"}
)
ALLOWED_TABLES = APPLICATION_TABLES | {"alembic_version"}


def _safe_url() -> str:
    root = str(_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from tests.postgres.safety import (
        POSTGRES_TEST_DATABASE_URL_ENV,
        require_safe_postgres_test_database_url,
    )

    raw = os.environ.get(POSTGRES_TEST_DATABASE_URL_ENV)
    if raw is None or not raw.strip():
        raise SystemExit(
            "ECI_POSTGRES_TEST_DATABASE_URL is required for PostgreSQL CI checks."
        )
    try:
        return require_safe_postgres_test_database_url(raw)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None


def current_and_head_revisions(url: str) -> tuple[str | None, str | None]:
    """Return (database revision, script-directory head) without logging the URL.

    Head is always ``ScriptDirectory.get_current_head()`` from migration files.
    Current is always ``MigrationContext.get_current_revision()`` from the
    database. These sources must stay independent so a database that is one
    revision behind cannot satisfy ``assert_at_head``. Multiple Alembic heads
    cause ``get_current_head()`` to raise.
    """
    config = Config(str(_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    engine = create_engine(url, echo=False)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current = context.get_current_revision()
    finally:
        engine.dispose()
    return current, head


def application_tables(url: str) -> set[str]:
    """Return public table names visible to SQLAlchemy."""
    engine = create_engine(url, echo=False)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def assert_at_head(url: str) -> None:
    current, head = current_and_head_revisions(url)
    if current != head:
        raise SystemExit("Alembic current revision does not match head.")
    if current is None:
        raise SystemExit("Alembic current revision is empty after upgrade.")
    tables = application_tables(url)
    missing = APPLICATION_TABLES - tables
    if missing:
        raise SystemExit("Expected application tables are missing after upgrade.")
    unexpected = tables - ALLOWED_TABLES
    if unexpected:
        raise SystemExit("Unexpected tables are present after upgrade.")


def assert_empty(url: str) -> None:
    tables = application_tables(url)
    remaining = tables & APPLICATION_TABLES
    if remaining:
        raise SystemExit("Application tables remain after alembic downgrade base.")
    unexpected = tables - {"alembic_version"}
    if unexpected:
        raise SystemExit("Unexpected tables remain after alembic downgrade base.")
    current, _head = current_and_head_revisions(url)
    if current is not None:
        raise SystemExit("Alembic current revision must be empty after downgrade base.")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"assert-head", "assert-empty"}:
        raise SystemExit("Usage: alembic_checks.py assert-head|assert-empty")
    url = _safe_url()
    if argv[1] == "assert-head":
        assert_at_head(url)
    else:
        assert_empty(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
