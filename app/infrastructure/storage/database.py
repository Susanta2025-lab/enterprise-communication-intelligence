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
        )
        _enable_sqlite_foreign_keys(engine)
        return engine

    return create_engine(database_url, echo=False)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Enforce foreign keys on every SQLite connection."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
