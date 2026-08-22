"""Mailbox delegated authorization sessions. This is not ECI login.

Server-side start and consume of a short-lived authorization transaction.
No provider HTTP, token exchange, or public OAuth routes occur here.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.application.exceptions import (
    ConnectorAccountNotFoundError,
    MailboxAuthorizationSessionInvalidError,
    UnsupportedMailboxAuthorizationProviderError,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.oauth_state import generate_oauth_state, hash_oauth_state
from app.core.pkce import PkceS256
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import (
    CommunicationCapability,
    MailboxAuthorizationProvider,
    MailboxAuthorizationPurpose,
)
from app.domain.interfaces.mailbox_authorization_session_repository import (
    ConsumedMailboxAuthorizationSession,
    NewMailboxAuthorizationSession,
)
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models.capabilities import require_requested_communication_capabilities

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_CODE_CHALLENGE_METHOD = PkceS256.method
DEFAULT_MAILBOX_AUTHORIZATION_CAPABILITIES: tuple[CommunicationCapability, ...] = (
    CommunicationCapability.MAIL_READ,
    CommunicationCapability.MAIL_SEND,
)
_REACTIVATABLE_PURPOSES = frozenset({MailboxAuthorizationPurpose.REAUTHORIZE})


@dataclass(frozen=True, slots=True)
class MailboxAuthorizationStartResult:
    """Persistence-neutral start result returned to the immediate caller.

    Contains raw ``state`` and the PKCE challenge. Omits user id, credential
    locators, the PKCE verifier, and tokens.
    """

    authorization_session_id: UUID
    provider: MailboxAuthorizationProvider
    state: str
    code_challenge: str
    code_challenge_method: str
    requested_capabilities: tuple[CommunicationCapability, ...]
    expires_at: datetime


class MailboxAuthorizationSessionService:
    """Create and consume mailbox authorization sessions."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
        *,
        session_ttl_seconds: int = 600,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if session_ttl_seconds < 60 or session_ttl_seconds > 1800:
            raise ValueError("Mailbox authorization session TTL is out of range.")
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory
        self._session_ttl_seconds = session_ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def start_authorization(
        self,
        principal: AuthenticatedPrincipal,
        *,
        provider: str,
        purpose: str,
        connector_account_id: UUID | None = None,
    ) -> MailboxAuthorizationStartResult:
        """Start a mailbox consent session for the authenticated ECI user.

        Requested capabilities come from server-side policy, not the caller.
        """
        started_at = time.perf_counter()
        provider_value = _parse_provider(provider)
        purpose_value = _parse_purpose(purpose)
        requested = require_requested_communication_capabilities(
            DEFAULT_MAILBOX_AUTHORIZATION_CAPABILITIES
        )
        user_id = self._identity_resolver.resolve_or_create(principal)
        bound_account_id = self._bind_reauthorize_account(
            user_id=user_id,
            provider=provider_value,
            purpose=purpose_value,
            connector_account_id=connector_account_id,
            started_at=started_at,
        )
        raw_state = generate_oauth_state()
        state_hash = hash_oauth_state(raw_state)
        verifier = PkceS256.generate_code_verifier()
        challenge = PkceS256.code_challenge(verifier)
        now = self._clock()
        expires_at = now + timedelta(seconds=self._session_ttl_seconds)
        try:
            with self._unit_of_work_factory() as uow:
                record = uow.mailbox_authorization_sessions.create(
                    NewMailboxAuthorizationSession(
                        user_id=user_id,
                        provider=provider_value,
                        purpose=purpose_value,
                        connector_account_id=bound_account_id,
                        state_hash=state_hash,
                        pkce_verifier=verifier,
                        requested_capabilities=requested,
                        created_at=now,
                        expires_at=expires_at,
                    )
                )
                uow.commit()
        except PersistenceError as exc:
            logger.warning(
                "mailbox_authorization_session_persistence_failed",
                operation="start",
                provider=provider_value.value,
                purpose=purpose_value.value,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "mailbox_authorization_session_started",
            operation="start",
            provider=provider_value.value,
            purpose=purpose_value.value,
            authorization_session_id=str(record.id),
            duration_ms=elapsed_ms(started_at),
        )
        return MailboxAuthorizationStartResult(
            authorization_session_id=record.id,
            provider=provider_value,
            state=raw_state,
            code_challenge=challenge,
            code_challenge_method=_CODE_CHALLENGE_METHOD,
            requested_capabilities=requested,
            expires_at=record.expires_at,
        )

    def consume_authorization_state(
        self,
        *,
        provider: str,
        state: str,
    ) -> ConsumedMailboxAuthorizationSession:
        """Consume a single-use session by raw state. No ECI bearer is required.

        The consume transaction ends before any future provider HTTP.
        """
        started_at = time.perf_counter()
        provider_value = _parse_provider(provider)
        if not isinstance(state, str) or not state:
            raise MailboxAuthorizationSessionInvalidError()
        state_hash = hash_oauth_state(state)
        now = self._clock()
        try:
            with self._unit_of_work_factory() as uow:
                consumed = uow.mailbox_authorization_sessions.consume_valid(
                    state_hash,
                    provider_value,
                    now,
                )
                if consumed is not None:
                    uow.commit()
        except PersistenceError as exc:
            logger.warning(
                "mailbox_authorization_session_persistence_failed",
                operation="consume",
                provider=provider_value.value,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        if consumed is None:
            logger.info(
                "mailbox_authorization_session_rejected",
                operation="consume",
                provider=provider_value.value,
                duration_ms=elapsed_ms(started_at),
                error_class="MailboxAuthorizationSessionInvalidError",
            )
            raise MailboxAuthorizationSessionInvalidError()

        logger.info(
            "mailbox_authorization_session_consumed",
            operation="consume",
            provider=consumed.provider.value,
            purpose=consumed.purpose.value,
            authorization_session_id=str(consumed.authorization_session_id),
            duration_ms=elapsed_ms(started_at),
        )
        return consumed

    def delete_expired(self, *, before: datetime | None = None) -> int:
        """Delete sessions whose expiry is at or before ``before``."""
        started_at = time.perf_counter()
        cutoff = before if before is not None else self._clock()
        try:
            with self._unit_of_work_factory() as uow:
                deleted = uow.mailbox_authorization_sessions.delete_expired(cutoff)
                uow.commit()
        except PersistenceError as exc:
            logger.warning(
                "mailbox_authorization_session_persistence_failed",
                operation="delete_expired",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "mailbox_authorization_sessions_expired_deleted",
            operation="delete_expired",
            duration_ms=elapsed_ms(started_at),
        )
        return deleted

    def _bind_reauthorize_account(
        self,
        *,
        user_id: UUID,
        provider: MailboxAuthorizationProvider,
        purpose: MailboxAuthorizationPurpose,
        connector_account_id: UUID | None,
        started_at: float,
    ) -> UUID | None:
        if purpose is MailboxAuthorizationPurpose.CONNECT:
            if connector_account_id is not None:
                raise MailboxAuthorizationSessionInvalidError()
            return None
        if purpose not in _REACTIVATABLE_PURPOSES:
            raise MailboxAuthorizationSessionInvalidError()
        if connector_account_id is None:
            raise MailboxAuthorizationSessionInvalidError()
        try:
            with self._unit_of_work_factory() as uow:
                record = uow.connector_accounts.get_owned(connector_account_id, user_id)
        except PersistenceError as exc:
            logger.warning(
                "mailbox_authorization_session_persistence_failed",
                operation="start",
                provider=provider.value,
                purpose=purpose.value,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None
        if record is None or record.provider != provider.value:
            raise ConnectorAccountNotFoundError()
        return record.id


def _parse_provider(provider: str) -> MailboxAuthorizationProvider:
    try:
        return MailboxAuthorizationProvider(provider.strip())
    except ValueError:
        raise UnsupportedMailboxAuthorizationProviderError() from None


def _parse_purpose(purpose: str) -> MailboxAuthorizationPurpose:
    try:
        return MailboxAuthorizationPurpose(purpose.strip())
    except ValueError:
        raise MailboxAuthorizationSessionInvalidError() from None
