"""PostgreSQL mailbox authorization session consume and constraint tests."""

from datetime import UTC, datetime, timedelta
from threading import Thread
from uuid import UUID

from sqlalchemy import update
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

_ISSUER = "https://issuer.example.invalid/"


def _new_session(
    user_id: UUID,
    *,
    raw_state: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[NewMailboxAuthorizationSession, str]:
    now = datetime.now(UTC)
    state = raw_state if raw_state is not None else generate_oauth_state()
    session = NewMailboxAuthorizationSession(
        user_id=user_id,
        provider=MailboxAuthorizationProvider.GMAIL,
        purpose=MailboxAuthorizationPurpose.CONNECT,
        connector_account_id=None,
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


def _create_user(session_factory: sessionmaker) -> UUID:
    with session_factory() as session:
        user_id = SqlAlchemyIdentityRepository(session).create_user_with_external_identity(
            _ISSUER,
            "session-owner",
        )
        session.commit()
    return user_id


def test_postgres_consume_is_single_use_and_clears_verifier(
    session_factory: sessionmaker,
) -> None:
    """PostgreSQL consume must CAS-consume once and null the verifier."""
    user_id = _create_user(session_factory)
    payload, raw_state = _new_session(user_id)
    state_hash = hash_oauth_state(raw_state)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        created = uow.mailbox_authorization_sessions.create(payload)
        uow.commit()
    now = datetime.now(UTC)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        consumed = uow.mailbox_authorization_sessions.consume_valid(
            state_hash,
            MailboxAuthorizationProvider.GMAIL,
            now,
        )
        uow.commit()
    assert consumed is not None
    assert consumed.pkce_verifier == payload.pkce_verifier
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        second = uow.mailbox_authorization_sessions.consume_valid(
            state_hash,
            MailboxAuthorizationProvider.GMAIL,
            datetime.now(UTC),
        )
        uow.commit()
    assert second is None
    with session_factory() as session:
        row = session.get(MailboxAuthorizationSession, created.id)
    assert row is not None
    assert row.consumed_at is not None
    assert row.pkce_verifier is None


def test_postgres_cas_loser_does_not_receive_verifier(
    session_factory: sessionmaker,
) -> None:
    """A consumed_at write without clearing the verifier still blocks consume."""
    user_id = _create_user(session_factory)
    payload, raw_state = _new_session(user_id)
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
            hash_oauth_state(raw_state),
            MailboxAuthorizationProvider.GMAIL,
            datetime.now(UTC),
        )
        session.expire_all()
        row = session.get(MailboxAuthorizationSession, created.id)
    assert lost is None
    assert row is not None
    assert row.pkce_verifier == payload.pkce_verifier


def test_postgres_concurrent_consume_at_most_one_success(
    session_factory: sessionmaker,
) -> None:
    """Two concurrent PostgreSQL consumers yield at most one success."""
    user_id = _create_user(session_factory)
    payload, raw_state = _new_session(user_id)
    state_hash = hash_oauth_state(raw_state)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.mailbox_authorization_sessions.create(payload)
        uow.commit()

    results: list[object] = []

    def _consume() -> None:
        try:
            with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
                consumed = uow.mailbox_authorization_sessions.consume_valid(
                    state_hash,
                    MailboxAuthorizationProvider.GMAIL,
                    datetime.now(UTC),
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
    successes = [item for item in results if item is not None]
    assert len(results) == 2
    assert len(successes) == 1
