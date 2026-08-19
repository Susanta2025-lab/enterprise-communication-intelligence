"""Process-scoped persistence engine and unit-of-work factory.

Importing this module does not create an engine or open a connection.
"""

from collections.abc import Callable

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.infrastructure.storage.database import create_database_engine, create_session_factory
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

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


def dispose_persistence_runtime() -> None:
    """Dispose the cached engine if one was created."""
    global _engine, _session_factory
    engine = _engine
    _engine = None
    _session_factory = None
    if engine is not None:
        engine.dispose()


def _session_factory_for(database_url: str) -> sessionmaker[Session]:
    global _engine, _session_factory
    if _session_factory is not None:
        return _session_factory
    engine = create_database_engine(database_url)
    factory = create_session_factory(engine)
    _engine = engine
    _session_factory = factory
    return factory
