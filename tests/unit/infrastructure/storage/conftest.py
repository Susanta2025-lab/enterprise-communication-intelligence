"""Shared SQLite persistence fixtures for Phase 9A unit tests."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.storage.database import (
    create_database_engine,
    create_session_factory,
)
from app.infrastructure.storage.models import Base

_SQLITE_MEMORY_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """In-memory SQLite engine with schema created via create_all (tests only)."""
    engine = create_database_engine(_SQLITE_MEMORY_URL)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine: Engine) -> sessionmaker[Session]:
    """Session factory sharing the in-memory SQLite engine via StaticPool."""
    return create_session_factory(sqlite_engine)
