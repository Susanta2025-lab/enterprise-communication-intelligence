"""PostgreSQL integration fixtures. Destructive work uses the dedicated test URL only."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.infrastructure.storage.database import (
    create_database_engine,
    create_session_factory,
)
from tests.postgres.safety import (
    POSTGRES_TEST_DATABASE_URL_ENV,
    UnsafePostgresTestDatabaseUrlError,
    require_safe_postgres_test_database_url,
)

_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def _temporary_database_url(url: str) -> Iterator[None]:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _upgrade_head(url: str) -> None:
    config = Config(str(_ROOT / "alembic.ini"))
    with _temporary_database_url(url):
        command.upgrade(config, "head")


def _truncate(engine: Engine) -> None:
    with engine.begin() as connection:
                connection.execute(
                    text(
                        "TRUNCATE TABLE mailbox_authorization_sessions, "
                        "workflow_actions, analyses, external_identities, "
                        "connector_accounts, users CASCADE"
                    )
                )


@pytest.fixture(scope="session")
def postgres_test_url() -> str:
    """Return the guarded PostgreSQL test URL, or skip when it is unset."""
    raw = os.environ.get(POSTGRES_TEST_DATABASE_URL_ENV)
    if raw is None or not raw.strip():
        pytest.skip(
            "ECI_POSTGRES_TEST_DATABASE_URL is not set; skipping PostgreSQL integration tests."
        )
    try:
        return require_safe_postgres_test_database_url(raw)
    except UnsafePostgresTestDatabaseUrlError as exc:
        pytest.fail(str(exc))


@pytest.fixture(scope="session")
def postgres_engine(postgres_test_url: str) -> Iterator[Engine]:
    """Engine against a database that has been migrated to head."""
    _upgrade_head(postgres_test_url)
    engine = create_database_engine(postgres_test_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def truncate_application_tables(postgres_engine: Engine) -> Iterator[None]:
    """Keep repository tests isolated without dropping schema."""
    _truncate(postgres_engine)
    yield
    _truncate(postgres_engine)


@pytest.fixture
def session_factory(postgres_engine: Engine) -> sessionmaker[Session]:
    """Session factory bound to the migrated PostgreSQL engine."""
    return create_session_factory(postgres_engine)
