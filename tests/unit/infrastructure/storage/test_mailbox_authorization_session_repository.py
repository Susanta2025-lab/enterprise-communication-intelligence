"""SQLite tests for mailbox authorization session persistence."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest
from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.oauth_state import generate_oauth_state, hash_oauth_state
from app.core.pkce import PkceS256
from app.domain.enums import (
    CommunicationCapability,
    MailboxAuthorizationProvider,
    MailboxAuthorizationPurpose,
)
from app.domain.interfaces.mailbox_authorization_session_repository import (
    NewMailboxAuthorizationSession,
)
from app.infrastructure.storage.models import MailboxAuthorizationSession
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository
from app.infrastructure.storage.repositories.mailbox_authorization_session import (
    SqlAlchemyMailboxAuthorizationSessionRepository,
)
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

_REPO_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "app"
    / "infrastructure"
    / "storage"
    / "repositories"
    / "mailbox_authorization_session.py"
)
_ISSUER = "https://issuer.example.invalid/"


def _new_session(
    user_id,
    *,
    provider: MailboxAuthorizationProvider = MailboxAuthorizationProvider.GMAIL,
    purpose: MailboxAuthorizationPurpose = MailboxAuthorizationPurpose.CONNECT,
    connector_account_id=None,
    raw_state: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[NewMailboxAuthorizationSession, str]:
    now = datetime.now(UTC)
    state = raw_state if raw_state is not None else generate_oauth_state()
    session = NewMailboxAuthorizationSession(
        user_id=user_id,
        provider=provider,
        purpose=purpose,
        connector_account_id=connector_account_id,
        state_hash=hash_oauth_state(state),
        pkce_verifier=PkceS256.generate_code_verifier(),
        requested_capabilities=(
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        ),
        created_at=now,
        expires_at=expires_at or (now + timedelta(minutes=10)),
    )
    return session, state


def _create_user(session_factory: sessionmaker):
    with session_factory() as session:
        user_id = SqlAlchemyIdentityRepository(session).create_user_with_external_identity(
            _ISSUER,
            "session-owner",
        )
        session.commit()
    return user_id


def test_create_persists_hash_not_raw_state(session_factory: sessionmaker) -> None:
    """Raw OAuth state is absent from the persisted row."""
    user_id = _create_user(session_factory)
    payload, raw_state = _new_session(user_id)
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        created = repository.create(payload)
        session.commit()
        row = session.get(MailboxAuthorizationSession, created.id)
    assert row is not None
    assert row.state_hash == hash_oauth_state(raw_state)
    assert raw_state not in (row.state_hash, row.pkce_verifier or "")
    assert getattr(row, "state", None) is None
    assert not hasattr(row, "access_token")
    assert not hasattr(row, "refresh_token")
    assert not hasattr(row, "authorization_code")
    columns = set(row.__mapper__.column_attrs.keys())
    assert "state" not in columns
    assert "raw_state" not in columns


def test_first_consume_succeeds_and_clears_verifier(session_factory: sessionmaker) -> None:
    """Successful consume is single-use and nulls the persisted verifier."""
    user_id = _create_user(session_factory)
    payload, raw_state = _new_session(user_id)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        created = uow.mailbox_authorization_sessions.create(payload)
        uow.commit()
    now = datetime.now(UTC)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        consumed = uow.mailbox_authorization_sessions.consume_valid(
            hash_oauth_state(raw_state),
            MailboxAuthorizationProvider.GMAIL,
            now,
        )
        uow.commit()
    assert consumed is not None
    assert consumed.pkce_verifier == payload.pkce_verifier
    assert consumed.authorization_session_id == created.id
    with session_factory() as session:
        row = session.get(MailboxAuthorizationSession, created.id)
    assert row is not None
    assert row.consumed_at is not None
    assert row.pkce_verifier is None


def test_second_consume_returns_none(session_factory: sessionmaker) -> None:
    """A second consume of the same hash fails closed."""
    user_id = _create_user(session_factory)
    payload, raw_state = _new_session(user_id)
    state_hash = hash_oauth_state(raw_state)
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        repository.create(payload)
        session.commit()
        first = repository.consume_valid(
            state_hash,
            MailboxAuthorizationProvider.GMAIL,
            datetime.now(UTC),
        )
        session.commit()
        second = repository.consume_valid(
            state_hash,
            MailboxAuthorizationProvider.GMAIL,
            datetime.now(UTC),
        )
        session.commit()
    assert first is not None
    assert second is None


def test_expired_and_provider_mismatch_and_malformed_hash_are_none(
    session_factory: sessionmaker,
) -> None:
    """Expired, mismatched, and unknown hashes share the same None result."""
    user_id = _create_user(session_factory)
    now = datetime.now(UTC)
    payload, raw_state = _new_session(user_id, expires_at=now - timedelta(seconds=1))
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        repository.create(payload)
        session.commit()
        expired = repository.consume_valid(
            hash_oauth_state(raw_state),
            MailboxAuthorizationProvider.GMAIL,
            now,
        )
        mismatched = repository.consume_valid(
            hash_oauth_state(raw_state),
            MailboxAuthorizationProvider.MICROSOFT_GRAPH,
            now,
        )
        unknown = repository.consume_valid(
            hash_oauth_state("other-state"),
            MailboxAuthorizationProvider.GMAIL,
            now,
        )
    assert expired is None
    assert mismatched is None
    assert unknown is None


def test_expired_at_now_cannot_be_consumed(session_factory: sessionmaker) -> None:
    """expires_at <= now is invalid even when consumed_at is still null."""
    user_id = _create_user(session_factory)
    now = datetime.now(UTC)
    payload, raw_state = _new_session(user_id, expires_at=now)
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        created = repository.create(payload)
        session.commit()
        expired = repository.consume_valid(
            hash_oauth_state(raw_state),
            MailboxAuthorizationProvider.GMAIL,
            now,
        )
        session.commit()
        row = session.get(MailboxAuthorizationSession, created.id)
    assert expired is None
    assert row is not None
    assert row.consumed_at is None
    assert row.pkce_verifier == payload.pkce_verifier


def test_cas_loser_does_not_receive_verifier_when_consumed_at_is_set(
    session_factory: sessionmaker,
) -> None:
    """A later consume cannot return the verifier after a winning CAS write."""
    user_id = _create_user(session_factory)
    payload, raw_state = _new_session(user_id)
    state_hash = hash_oauth_state(raw_state)
    now = datetime.now(UTC)
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        created = repository.create(payload)
        session.commit()
        session.execute(
            update(MailboxAuthorizationSession)
            .where(MailboxAuthorizationSession.id == created.id)
            .values(consumed_at=now)
        )
        session.commit()
        lost = repository.consume_valid(
            state_hash,
            MailboxAuthorizationProvider.GMAIL,
            datetime.now(UTC),
        )
        session.expire_all()
        row = session.get(MailboxAuthorizationSession, created.id)
    assert lost is None
    assert row is not None
    assert row.pkce_verifier == payload.pkce_verifier
    assert row.consumed_at is not None


def test_consume_uses_conditional_update_returning() -> None:
    """Consume must be a CAS UPDATE, not SELECT-then-unconditional UPDATE."""
    source = _REPO_SOURCE.read_text(encoding="utf-8")
    method = source.split("def consume_valid(", 1)[1].split("def delete_expired(", 1)[0]
    assert "select(MailboxAuthorizationSession)" not in method
    assert ".returning(" in method
    assert "MailboxAuthorizationSession.state_hash == state_hash" in method
    assert "MailboxAuthorizationSession.consumed_at.is_(None)" in method
    assert "MailboxAuthorizationSession.expires_at > now" in method
    assert "pkce_verifier=None" in method


def test_delete_expired(session_factory: sessionmaker) -> None:
    """Expired rows are removed; unexpired rows remain."""
    user_id = _create_user(session_factory)
    now = datetime.now(UTC)
    expired, _expired_state = _new_session(
        user_id,
        raw_state=generate_oauth_state(),
        expires_at=now - timedelta(minutes=1),
    )
    live, _live_state = _new_session(
        user_id,
        raw_state=generate_oauth_state(),
        expires_at=now + timedelta(minutes=10),
    )
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        dead = repository.create(expired)
        kept = repository.create(live)
        session.commit()
        deleted = repository.delete_expired(now)
        session.commit()
        assert deleted == 1
        assert session.get(MailboxAuthorizationSession, dead.id) is None
        assert session.get(MailboxAuthorizationSession, kept.id) is not None


def test_concurrent_consume_at_most_one_success(tmp_path) -> None:
    """Two concurrent consumes yield at most one success."""
    from sqlalchemy import create_engine, event

    from app.infrastructure.storage.models import Base

    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/sessions.db",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    user_id = _create_user(factory)
    payload, raw_state = _new_session(user_id)
    state_hash = hash_oauth_state(raw_state)
    with SqlAlchemyPersistenceUnitOfWork(factory) as uow:
        uow.mailbox_authorization_sessions.create(payload)
        uow.commit()

    results: list[object] = []

    def _consume() -> None:
        now = datetime.now(UTC)
        try:
            with SqlAlchemyPersistenceUnitOfWork(factory) as uow:
                consumed = uow.mailbox_authorization_sessions.consume_valid(
                    state_hash,
                    MailboxAuthorizationProvider.GMAIL,
                    now,
                )
                if consumed is not None:
                    uow.commit()
                results.append(consumed)
        except Exception:
            results.append(None)

    first = Thread(target=_consume)
    second = Thread(target=_consume)
    first.start()
    second.start()
    first.join()
    second.join()
    engine.dispose()
    successes = [item for item in results if item is not None]
    assert len(results) == 2
    assert len(successes) == 1


def test_session_table_has_no_token_columns(sqlite_engine: Engine) -> None:
    """Authorization sessions must not persist tokens or raw state."""
    from sqlalchemy import inspect

    inspector = inspect(sqlite_engine)
    columns = {
        column["name"] for column in inspector.get_columns("mailbox_authorization_sessions")
    }
    assert columns == {
        "id",
        "user_id",
        "provider",
        "purpose",
        "connector_account_id",
        "state_hash",
        "pkce_verifier",
        "requested_capabilities",
        "created_at",
        "expires_at",
        "consumed_at",
    }
    assert "state" not in columns
    assert "access_token" not in columns
    assert "refresh_token" not in columns
    assert "authorization_code" not in columns
    assert "client_secret" not in columns
    assert "credential_ref" not in columns


def test_purpose_account_check_rejects_connect_with_account(
    session_factory: sessionmaker,
) -> None:
    """Connect sessions cannot store a connector_account_id."""
    from app.core.exceptions import PersistenceError
    from app.domain.interfaces.connector_account_repository import NewConnectorAccount
    from app.infrastructure.storage.repositories.connector_account import (
        SqlAlchemyConnectorAccountRepository,
    )

    user_id = _create_user(session_factory)
    with session_factory() as session:
        accounts = SqlAlchemyConnectorAccountRepository(session)
        account = accounts.create(
            NewConnectorAccount(
                user_id=user_id,
                provider="gmail",
                external_account_id="mailbox-001",
            )
        )
        session.commit()
        account_id = account.id

    payload, _state = _new_session(
        user_id,
        purpose=MailboxAuthorizationPurpose.CONNECT,
        connector_account_id=account_id,
    )
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        with pytest.raises(PersistenceError):
            repository.create(payload)
            session.flush()


def test_purpose_account_check_rejects_reauthorize_without_account(
    session_factory: sessionmaker,
) -> None:
    """Reauthorize sessions must store a connector_account_id."""
    from app.core.exceptions import PersistenceError

    user_id = _create_user(session_factory)
    payload, _state = _new_session(
        user_id,
        purpose=MailboxAuthorizationPurpose.REAUTHORIZE,
        connector_account_id=None,
    )
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        with pytest.raises(PersistenceError):
            repository.create(payload)
            session.flush()


def test_purpose_account_check_rejects_connect_another_with_account(
    session_factory: sessionmaker,
) -> None:
    """Connect-another sessions cannot store a connector_account_id."""
    from app.core.exceptions import PersistenceError
    from app.domain.interfaces.connector_account_repository import NewConnectorAccount
    from app.infrastructure.storage.repositories.connector_account import (
        SqlAlchemyConnectorAccountRepository,
    )

    user_id = _create_user(session_factory)
    with session_factory() as session:
        accounts = SqlAlchemyConnectorAccountRepository(session)
        account = accounts.create(
            NewConnectorAccount(
                user_id=user_id,
                provider="gmail",
                external_account_id="mailbox-001",
            )
        )
        session.commit()
        account_id = account.id

    payload, _state = _new_session(
        user_id,
        purpose=MailboxAuthorizationPurpose.CONNECT_ANOTHER,
        connector_account_id=account_id,
    )
    with session_factory() as session:
        repository = SqlAlchemyMailboxAuthorizationSessionRepository(session)
        with pytest.raises(PersistenceError):
            repository.create(payload)
            session.flush()
