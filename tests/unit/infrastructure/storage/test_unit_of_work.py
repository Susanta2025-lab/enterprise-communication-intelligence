"""Unit tests for the SQLAlchemy persistence unit of work."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
from app.infrastructure.storage.models import User
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

_ISSUER = "https://issuer.example.invalid/"
_SUBJECT = "uow-subject"


def test_successful_commit_persists_identity(session_factory: sessionmaker) -> None:
    """Repository work is visible only after an explicit commit."""
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        user_id = uow.identity_repository.create_user_with_external_identity(_ISSUER, _SUBJECT)
        uow.commit()

    with session_factory() as session:
        assert session.get(User, user_id) is not None
        repository = SqlAlchemyIdentityRepository(session)
        assert repository.get_user_id_by_external_identity(_ISSUER, _SUBJECT) == user_id


def test_work_is_not_committed_until_commit(session_factory: sessionmaker) -> None:
    """Closing without commit must discard repository writes."""
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        user_id = uow.identity_repository.create_user_with_external_identity(_ISSUER, _SUBJECT)

    with session_factory() as session:
        assert session.get(User, user_id) is None


def test_exception_before_commit_rolls_back(session_factory: sessionmaker) -> None:
    """An exception inside the unit of work must not persist rows."""
    try:
        with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
            uow.identity_repository.create_user_with_external_identity(_ISSUER, _SUBJECT)
            raise RuntimeError("forced-failure")
    except RuntimeError:
        pass

    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(User))
        assert count == 0


def test_session_is_closed_after_context(session_factory: sessionmaker) -> None:
    """The Session must close even after a successful commit."""
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        session = uow._session
        uow.identity_repository.create_user_with_external_identity(_ISSUER, _SUBJECT)
        uow.commit()

    assert session is not None
    assert session.get_transaction() is None


def test_repositories_share_the_same_session(session_factory: sessionmaker) -> None:
    """Identity, analysis, and connector account repositories share one Session."""
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        identity_session = uow.identity_repository._session  # type: ignore[attr-defined]
        analysis_session = uow.analysis_repository._session  # type: ignore[attr-defined]
        connector_session = uow.connector_accounts._session  # type: ignore[attr-defined]
        assert identity_session is analysis_session
        assert analysis_session is connector_session
        assert identity_session is uow._session


def test_commit_failure_becomes_persistence_error(session_factory: sessionmaker) -> None:
    """Driver commit failures must become PersistenceError without leaking SQL."""
    sentinel = "password=supersecret host=db.internal.sqlalchemy-test"
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.identity_repository.create_user_with_external_identity(_ISSUER, _SUBJECT)

        def _fail_commit() -> None:
            raise OperationalError("SELECT 1 FROM users", {}, Exception(sentinel))

        assert uow._session is not None
        uow._session.commit = _fail_commit  # type: ignore[method-assign]
        try:
            uow.commit()
            raised = None
        except PersistenceError as exc:
            raised = exc

    assert raised is not None
    assert raised.message == "Could not commit persistence changes."
    assert sentinel not in raised.message
    assert "supersecret" not in str(raised)
    assert "db.internal" not in str(raised)
    assert raised.__cause__ is None


def test_enter_failure_becomes_persistence_error() -> None:
    """Session begin failures must not expose driver or credential text."""
    sentinel = "password=supersecret host=db.internal.sqlalchemy-test"

    class _BrokenSessionFactory:
        def __call__(self) -> object:
            session = type("Session", (), {})()
            session.in_transaction = lambda: False  # type: ignore[attr-defined]

            def _begin() -> None:
                raise OperationalError("BEGIN", {}, Exception(sentinel))

            session.begin = _begin  # type: ignore[attr-defined]
            session.close = lambda: None  # type: ignore[attr-defined]
            return session

    uow = SqlAlchemyPersistenceUnitOfWork(_BrokenSessionFactory())  # type: ignore[arg-type]
    with pytest.raises(PersistenceError) as exc_info:
        with uow:
            pass

    assert exc_info.value.message == "Could not complete persistence operation."
    assert sentinel not in exc_info.value.message
    assert "supersecret" not in str(exc_info.value)
    assert "db.internal" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
