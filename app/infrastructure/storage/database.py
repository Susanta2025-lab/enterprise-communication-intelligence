"""SQLAlchemy engine and session factories.

Callers construct engines explicitly. Importing this module does not open
connections or create schema.
"""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_SQLITE_PREFIXES = ("sqlite:", "sqlite+")


def create_database_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine without echoing SQL or logging credentials."""
    if database_url.startswith(_SQLITE_PREFIXES):
        engine = create_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            isolation_level="SERIALIZABLE",
        )
        _configure_sqlite(engine)
        return engine

    return create_engine(database_url, echo=False)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _configure_sqlite(engine: Engine) -> None:
    """Enable foreign keys and real SAVEPOINT transactions on SQLite only.

    pysqlite does not emit BEGIN in a way that makes SAVEPOINT inner
    transactions roll back. SQLAlchemy's documented serializable recipe is
    required so unit-of-work rollback and identity savepoints work in tests.
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.isolation_level = None  # type: ignore[attr-defined]
        cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection: object) -> None:
        connection.exec_driver_sql("BEGIN")  # type: ignore[union-attr]
