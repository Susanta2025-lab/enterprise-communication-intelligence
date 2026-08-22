"""SQLAlchemy-free mailbox authorization session persistence contract.

A mailbox authorization session is delegated mailbox consent, not ECI login.
Raw OAuth state is never persisted. Tokens are never persisted.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.enums import (
    CommunicationCapability,
    MailboxAuthorizationProvider,
    MailboxAuthorizationPurpose,
)


@dataclass(frozen=True, slots=True)
class NewMailboxAuthorizationSession:
    """Persistence-neutral input for a short-lived mailbox authorization session."""

    user_id: UUID
    provider: MailboxAuthorizationProvider
    purpose: MailboxAuthorizationPurpose
    connector_account_id: UUID | None
    state_hash: str
    pkce_verifier: str
    requested_capabilities: tuple[CommunicationCapability, ...]
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MailboxAuthorizationSessionRecord:
    """Persistence-neutral stored mailbox authorization session.

    ``state_hash`` is SHA-256(hex) of the raw OAuth state. The raw state is
    not stored. ``pkce_verifier`` is short-lived and must be cleared on consume.
    """

    id: UUID
    user_id: UUID
    provider: MailboxAuthorizationProvider
    purpose: MailboxAuthorizationPurpose
    connector_account_id: UUID | None
    state_hash: str
    pkce_verifier: str | None
    requested_capabilities: tuple[CommunicationCapability, ...]
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConsumedMailboxAuthorizationSession:
    """In-memory result of a successful single-use session consume.

    ``pkce_verifier`` exists only in process memory for a later code exchange.
    It must not be written back or logged.
    """

    authorization_session_id: UUID
    user_id: UUID
    provider: MailboxAuthorizationProvider
    purpose: MailboxAuthorizationPurpose
    connector_account_id: UUID | None
    pkce_verifier: str
    requested_capabilities: tuple[CommunicationCapability, ...]


class MailboxAuthorizationSessionRepository(ABC):
    """Store short-lived mailbox authorization sessions.

    Methods do not commit. The caller owns the transaction. Lookup is by
    ``state_hash``, never by raw state.
    """

    @abstractmethod
    def create(
        self,
        session: NewMailboxAuthorizationSession,
    ) -> MailboxAuthorizationSessionRecord:
        """Insert an unconsumed authorization session."""

    @abstractmethod
    def consume_valid(
        self,
        state_hash: str,
        provider: MailboxAuthorizationProvider,
        now: datetime,
    ) -> ConsumedMailboxAuthorizationSession | None:
        """Atomically consume a matching unexpired, unconsumed session.

        The persistence operation must require matching ``state_hash``,
        matching provider, ``consumed_at IS NULL``, and ``expires_at > now``
        in the same compare-and-set that marks the row consumed. Missing,
        expired, consumed, or provider-mismatched rows return ``None``.
        Concurrent callers must observe at most one success. The losing
        caller must not receive the PKCE verifier. Successful consume
        clears the persisted verifier in the same unit of work.
        """

    @abstractmethod
    def delete_expired(self, before: datetime) -> int:
        """Delete sessions whose ``expires_at`` is at or before ``before``."""
