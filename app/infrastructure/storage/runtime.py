"""Process-scoped persistence engine and unit-of-work factory.

Importing this module does not create an engine or open a connection.
"""

from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.core.telemetry import error_class
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.infrastructure.storage.database import create_database_engine, create_session_factory
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

logger = get_logger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_unit_of_work_factory(database_url: str) -> Callable[[], PersistenceUnitOfWork]:
    """Return a factory that opens a unit of work against the process engine.

    The engine is created on first use and reused until ``dispose_persistence_runtime``.
    """
    factory = _session_factory_for(database_url)

    def _create() -> PersistenceUnitOfWork:
        return SqlAlchemyPersistenceUnitOfWork(factory)

    return _create


def probe_database_readiness(database_url: str) -> bool:
    """Return True when a bounded ``SELECT 1`` probe succeeds.

    Opens a short connection, executes a static query, and closes immediately.
    Driver failures become False. Logs only ``component`` and ``error_class``.
    """
    try:
        engine = _engine_for(database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.warning(
            "database_readiness_failed",
            component="database",
            error_class=error_class(exc),
        )
        return False


def get_persistence_session_factory(database_url: str) -> sessionmaker[Session]:
    """Return the process-scoped SQLAlchemy session factory.

    Reuses the same engine as ``get_unit_of_work_factory``. Importing this
    module still does not open a connection; the engine is created on first use.
    """
    return _session_factory_for(database_url)


def dispose_persistence_runtime() -> None:
    """Dispose the cached engine if one was created."""
    global _engine, _session_factory
    engine = _engine
    _engine = None
    _session_factory = None
    if engine is not None:
        engine.dispose()


def _engine_for(database_url: str) -> Engine:
    global _engine, _session_factory
    if _engine is not None:
        return _engine
    engine = create_database_engine(database_url)
    _engine = engine
    _session_factory = create_session_factory(engine)
    return engine


def _session_factory_for(database_url: str) -> sessionmaker[Session]:
    _engine_for(database_url)
    assert _session_factory is not None
    return _session_factory
