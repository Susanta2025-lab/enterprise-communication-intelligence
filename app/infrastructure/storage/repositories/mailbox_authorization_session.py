"""SQLAlchemy MailboxAuthorizationSessionRepository implementation."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.enums import MailboxAuthorizationProvider, MailboxAuthorizationPurpose
from app.domain.interfaces.mailbox_authorization_session_repository import (
    ConsumedMailboxAuthorizationSession,
    MailboxAuthorizationSessionRecord,
    MailboxAuthorizationSessionRepository,
    NewMailboxAuthorizationSession,
)
from app.domain.models.capabilities import (
    parse_stored_communication_capabilities,
    require_requested_communication_capabilities,
    serialize_communication_capabilities,
)
from app.infrastructure.storage.models import MailboxAuthorizationSession

_GENERIC_FAILURE = "Could not persist mailbox authorization session."
_REACTIVATABLE = (
    MailboxAuthorizationPurpose.CONNECT.value,
    MailboxAuthorizationPurpose.REAUTHORIZE.value,
    MailboxAuthorizationPurpose.CONNECT_ANOTHER.value,
)


class SqlAlchemyMailboxAuthorizationSessionRepository(MailboxAuthorizationSessionRepository):
    """Persist mailbox authorization sessions with atomic single-use consume."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        session: NewMailboxAuthorizationSession,
    ) -> MailboxAuthorizationSessionRecord:
        """Insert an unconsumed authorization session."""
        capabilities = require_requested_communication_capabilities(
            session.requested_capabilities
        )
        serialized = serialize_communication_capabilities(capabilities)
        if serialized is None:
            raise PersistenceError(_GENERIC_FAILURE)
        row = MailboxAuthorizationSession(
            id=uuid4(),
            user_id=session.user_id,
            provider=session.provider.value,
            purpose=session.purpose.value,
            connector_account_id=session.connector_account_id,
            state_hash=session.state_hash,
            pkce_verifier=session.pkce_verifier,
            requested_capabilities=serialized,
            created_at=session.created_at,
            expires_at=session.expires_at,
            consumed_at=None,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise PersistenceError(_GENERIC_FAILURE) from exc
        return _to_record(row)

    def consume_valid(
        self,
        state_hash: str,
        provider: MailboxAuthorizationProvider,
        now: datetime,
    ) -> ConsumedMailboxAuthorizationSession | None:
        """Atomically consume a matching unexpired, unconsumed session.

        A single conditional ``UPDATE ... RETURNING`` is the compare-and-set.
        Only the winning statement receives the PKCE verifier. The verifier is
        then nulled in the same transaction so commit persists both writes.
        """
        consume = (
            update(MailboxAuthorizationSession)
            .where(
                MailboxAuthorizationSession.state_hash == state_hash,
                MailboxAuthorizationSession.provider == provider.value,
                MailboxAuthorizationSession.consumed_at.is_(None),
                MailboxAuthorizationSession.expires_at > now,
                MailboxAuthorizationSession.pkce_verifier.is_not(None),
            )
            .values(consumed_at=now)
            .returning(
                MailboxAuthorizationSession.id,
                MailboxAuthorizationSession.user_id,
                MailboxAuthorizationSession.provider,
                MailboxAuthorizationSession.purpose,
                MailboxAuthorizationSession.connector_account_id,
                MailboxAuthorizationSession.pkce_verifier,
                MailboxAuthorizationSession.requested_capabilities,
            )
            .execution_options(synchronize_session=False)
        )
        try:
            row = self._session.execute(consume).one_or_none()
        except SQLAlchemyError as exc:
            raise PersistenceError(_GENERIC_FAILURE) from exc
        if row is None:
            return None
        verifier = row.pkce_verifier
        if not isinstance(verifier, str) or not verifier:
            return None
        try:
            capabilities = parse_stored_communication_capabilities(
                row.requested_capabilities
            )
            bound_provider = MailboxAuthorizationProvider(row.provider)
            purpose = MailboxAuthorizationPurpose(row.purpose)
        except ValueError:
            return None
        if capabilities is None:
            return None
        clear = (
            update(MailboxAuthorizationSession)
            .where(MailboxAuthorizationSession.id == row.id)
            .values(pkce_verifier=None)
            .execution_options(synchronize_session=False)
        )
        try:
            cleared = self._session.execute(clear)
        except SQLAlchemyError as exc:
            raise PersistenceError(_GENERIC_FAILURE) from exc
        if cleared.rowcount != 1:
            raise PersistenceError(_GENERIC_FAILURE)
        return ConsumedMailboxAuthorizationSession(
            authorization_session_id=row.id,
            user_id=row.user_id,
            provider=bound_provider,
            purpose=purpose,
            connector_account_id=row.connector_account_id,
            pkce_verifier=verifier,
            requested_capabilities=capabilities,
        )

    def delete_expired(self, before: datetime) -> int:
        """Delete sessions whose ``expires_at`` is at or before ``before``."""
        statement = delete(MailboxAuthorizationSession).where(
            MailboxAuthorizationSession.expires_at <= before
        )
        result = self._session.execute(
            statement.execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)


def _to_record(row: MailboxAuthorizationSession) -> MailboxAuthorizationSessionRecord:
    try:
        capabilities = parse_stored_communication_capabilities(row.requested_capabilities)
    except ValueError as exc:
        raise PersistenceError(_GENERIC_FAILURE) from exc
    if capabilities is None:
        raise PersistenceError(_GENERIC_FAILURE)
    if row.purpose not in _REACTIVATABLE:
        raise PersistenceError(_GENERIC_FAILURE)
    return MailboxAuthorizationSessionRecord(
        id=row.id,
        user_id=row.user_id,
        provider=MailboxAuthorizationProvider(row.provider),
        purpose=MailboxAuthorizationPurpose(row.purpose),
        connector_account_id=row.connector_account_id,
        state_hash=row.state_hash,
        pkce_verifier=row.pkce_verifier,
        requested_capabilities=capabilities,
        created_at=row.created_at,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
    )
