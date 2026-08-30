"""Gmail mailbox OAuth start and callback orchestration.

Mailbox consent is separate from ECI application-user OIDC. Google HTTP never
runs while a database unit of work is open. Tokens are never returned.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.exceptions import (
    ConnectorAccountConflictError,
    MailboxAuthorizationSessionInvalidError,
    MailboxOAuthAuthorizationDeniedError,
)
from app.application.services.identity import IdentityResolver
from app.application.services.mailbox_authorization_sessions import (
    MailboxAuthorizationSessionService,
)
from app.application.services.mailbox_oauth_reauthorization import (
    load_reauthorization_target,
    persist_reauthorized_connector_account,
)
from app.core.exceptions import (
    CommunicationCredentialUnavailableError,
    MailboxOAuthAuthorizationFailedError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import (
    CommunicationCapability,
    ConnectorAccountStatus,
    MailboxAuthorizationProvider,
    MailboxAuthorizationPurpose,
)
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    CommunicationCredentialStore,
)
from app.domain.interfaces.connector_account_repository import (
    ConnectorAccountRecord,
    NewConnectorAccount,
)
from app.domain.interfaces.mailbox_authorization_session_repository import (
    ConsumedMailboxAuthorizationSession,
)
from app.domain.interfaces.mailbox_oauth_client import (
    MailboxOAuthAuthorizationResult,
    MailboxOAuthClient,
)
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

logger = get_logger(__name__)

CreateStoredMailboxCredential = Callable[[bytes], CommunicationCredentialRecord]

_UNAVAILABLE = "Gmail mailbox authorization is unavailable."
_PROVIDER = MailboxAuthorizationProvider.GMAIL
_PROVIDER_SLUG = _PROVIDER.value


@dataclass(frozen=True, slots=True)
class GmailMailboxAuthorizationStartResult:
    """Browser redirect target for Gmail mailbox consent."""

    authorization_url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class GmailMailboxAuthorizationCallbackResult:
    """Sanitized Gmail connection result. Omits locators and tokens."""

    connector_account_id: UUID
    provider: str
    external_account_id: str
    status: ConnectorAccountStatus
    granted_capabilities: tuple[CommunicationCapability, ...]
    reused_existing: bool = False


class GmailMailboxOAuthService:
    """Start Gmail consent and complete the unauthenticated Google callback."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
        oauth_client: MailboxOAuthClient,
        credential_store: CommunicationCredentialStore,
        create_stored_credential: CreateStoredMailboxCredential,
        *,
        session_ttl_seconds: int = 600,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions = MailboxAuthorizationSessionService(
            identity_resolver,
            unit_of_work_factory,
            session_ttl_seconds=session_ttl_seconds,
            clock=clock,
        )
        self._unit_of_work_factory = unit_of_work_factory
        self._oauth_client = oauth_client
        self._credential_store = credential_store
        self._create_stored_credential = create_stored_credential

    def start_authorization(
        self,
        principal: AuthenticatedPrincipal,
    ) -> GmailMailboxAuthorizationStartResult:
        """Create a connect session and return the Google authorization URL."""
        return self._start_authorization(
            principal,
            purpose=MailboxAuthorizationPurpose.CONNECT.value,
            connector_account_id=None,
        )

    def start_reauthorization(
        self,
        principal: AuthenticatedPrincipal,
        connector_account_id: UUID,
    ) -> GmailMailboxAuthorizationStartResult:
        """Create a reauthorize session bound to the owned Gmail account."""
        return self._start_authorization(
            principal,
            purpose=MailboxAuthorizationPurpose.REAUTHORIZE.value,
            connector_account_id=connector_account_id,
        )

    def start_connect_another(
        self,
        principal: AuthenticatedPrincipal,
    ) -> GmailMailboxAuthorizationStartResult:
        """Create a connect-another session that requests Google account selection."""
        return self._start_authorization(
            principal,
            purpose=MailboxAuthorizationPurpose.CONNECT_ANOTHER.value,
            connector_account_id=None,
        )

    def _start_authorization(
        self,
        principal: AuthenticatedPrincipal,
        *,
        purpose: str,
        connector_account_id: UUID | None,
    ) -> GmailMailboxAuthorizationStartResult:
        started_at = time.perf_counter()
        session = self._sessions.start_authorization(
            principal,
            provider=_PROVIDER_SLUG,
            purpose=purpose,
            connector_account_id=connector_account_id,
        )
        try:
            authorization_url = self._oauth_client.build_authorization_url(
                state=session.state,
                code_challenge=session.code_challenge,
                code_challenge_method=session.code_challenge_method,
                account_selection=purpose == MailboxAuthorizationPurpose.CONNECT_ANOTHER.value,
            )
        except (MailboxOAuthAuthorizationFailedError, ServiceUnavailableError):
            raise
        except Exception as exc:
            logger.warning(
                "gmail_oauth_start_failed",
                operation="start",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise MailboxOAuthAuthorizationFailedError() from None
        logger.info(
            "gmail_oauth_authorization_started",
            operation="start",
            authorization_session_id=str(session.authorization_session_id),
            duration_ms=elapsed_ms(started_at),
        )
        return GmailMailboxAuthorizationStartResult(
            authorization_url=authorization_url,
            expires_at=session.expires_at,
        )

    def complete_authorization(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> GmailMailboxAuthorizationCallbackResult:
        """Consume state, then exchange the code outside any database transaction."""
        started_at = time.perf_counter()
        if error:
            self._consume_provider_error(state=state, started_at=started_at)
        if not isinstance(state, str) or not state or not isinstance(code, str) or not code:
            raise MailboxOAuthAuthorizationFailedError()
        consumed = self._sessions.consume_authorization_state(
            provider=_PROVIDER_SLUG,
            state=state,
        )
        if consumed.purpose is MailboxAuthorizationPurpose.REAUTHORIZE:
            return self._complete_reauthorization(
                consumed=consumed,
                code=code,
                started_at=started_at,
            )
        if consumed.purpose not in {
            MailboxAuthorizationPurpose.CONNECT,
            MailboxAuthorizationPurpose.CONNECT_ANOTHER,
        }:
            raise MailboxOAuthAuthorizationFailedError()
        try:
            exchanged = self._oauth_client.exchange_authorization_code(
                code=code,
                code_verifier=consumed.pkce_verifier,
            )
        except (MailboxOAuthAuthorizationFailedError, ServiceUnavailableError):
            raise
        except Exception as exc:
            logger.warning(
                "gmail_oauth_callback_exchange_failed",
                operation="callback",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise MailboxOAuthAuthorizationFailedError() from None
        if CommunicationCapability.MAIL_READ not in exchanged.granted_capabilities:
            logger.info(
                "gmail_oauth_required_read_grant_missing",
                operation="callback",
                duration_ms=elapsed_ms(started_at),
            )
            raise MailboxOAuthAuthorizationFailedError()
        stored = self._store_credential(exchanged)
        try:
            account, reused = self._persist_connector_account(
                user_id=consumed.user_id,
                external_account_id=exchanged.external_account_id,
                credential_ref=stored.credential_ref,
                granted_capabilities=exchanged.granted_capabilities,
                display_identity=exchanged.display_identity,
            )
        except Exception as exc:
            self._compensate_stored_credential(stored.credential_ref, started_at)
            if isinstance(exc, ServiceUnavailableError):
                raise
            logger.warning(
                "gmail_oauth_callback_persist_failed",
                operation="callback",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None
        if reused:
            self._compensate_stored_credential(stored.credential_ref, started_at)
        logger.info(
            "gmail_oauth_authorization_completed",
            operation="callback",
            connector_account_id=str(account.id),
            reused_existing=reused,
            duration_ms=elapsed_ms(started_at),
        )
        return GmailMailboxAuthorizationCallbackResult(
            connector_account_id=account.id,
            provider=account.provider,
            external_account_id=account.external_account_id,
            status=account.status,
            granted_capabilities=account.granted_capabilities or exchanged.granted_capabilities,
            reused_existing=reused,
        )

    def _complete_reauthorization(
        self,
        *,
        consumed: ConsumedMailboxAuthorizationSession,
        code: str,
        started_at: float,
    ) -> GmailMailboxAuthorizationCallbackResult:
        if consumed.connector_account_id is None:
            raise MailboxOAuthAuthorizationFailedError()
        try:
            exchanged = self._oauth_client.exchange_authorization_code(
                code=code,
                code_verifier=consumed.pkce_verifier,
            )
        except (MailboxOAuthAuthorizationFailedError, ServiceUnavailableError):
            raise
        except Exception as exc:
            logger.warning(
                "gmail_oauth_callback_exchange_failed",
                operation="callback",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise MailboxOAuthAuthorizationFailedError() from None
        if CommunicationCapability.MAIL_READ not in exchanged.granted_capabilities:
            logger.info(
                "gmail_oauth_required_read_grant_missing",
                operation="callback",
                duration_ms=elapsed_ms(started_at),
            )
            raise MailboxOAuthAuthorizationFailedError()
        stored = self._store_credential(exchanged)
        try:
            bound = load_reauthorization_target(
                self._unit_of_work_factory,
                user_id=consumed.user_id,
                connector_account_id=consumed.connector_account_id,
                provider=_PROVIDER_SLUG,
                external_account_id=exchanged.external_account_id,
                unavailable_message=_UNAVAILABLE,
            )
            previous_locator = bound.credential_ref
            if previous_locator and previous_locator != stored.credential_ref:
                self._compensate_stored_credential(previous_locator, started_at)
            account = persist_reauthorized_connector_account(
                self._unit_of_work_factory,
                user_id=consumed.user_id,
                connector_account_id=consumed.connector_account_id,
                provider=_PROVIDER_SLUG,
                external_account_id=exchanged.external_account_id,
                credential_ref=stored.credential_ref,
                granted_capabilities=exchanged.granted_capabilities,
                unavailable_message=_UNAVAILABLE,
                display_identity=exchanged.display_identity,
            )
        except Exception as exc:
            self._compensate_stored_credential(stored.credential_ref, started_at)
            if isinstance(
                exc,
                (
                    ServiceUnavailableError,
                    MailboxOAuthAuthorizationFailedError,
                    ConnectorAccountConflictError,
                ),
            ):
                raise
            logger.warning(
                "gmail_oauth_callback_persist_failed",
                operation="callback",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None
        logger.info(
            "gmail_oauth_reauthorization_completed",
            operation="callback",
            connector_account_id=str(account.id),
            reused_existing=False,
            duration_ms=elapsed_ms(started_at),
        )
        return GmailMailboxAuthorizationCallbackResult(
            connector_account_id=account.id,
            provider=account.provider,
            external_account_id=account.external_account_id,
            status=account.status,
            granted_capabilities=account.granted_capabilities or exchanged.granted_capabilities,
            reused_existing=False,
        )

    def _consume_provider_error(self, *, state: str | None, started_at: float) -> None:
        if not isinstance(state, str) or not state:
            raise MailboxOAuthAuthorizationDeniedError()
        try:
            self._sessions.consume_authorization_state(
                provider=_PROVIDER_SLUG,
                state=state,
            )
        except MailboxAuthorizationSessionInvalidError:
            logger.info(
                "gmail_oauth_provider_error_state_invalid",
                operation="callback",
                duration_ms=elapsed_ms(started_at),
            )
            raise
        except ServiceUnavailableError:
            raise
        logger.info(
            "gmail_oauth_authorization_denied",
            operation="callback",
            duration_ms=elapsed_ms(started_at),
        )
        raise MailboxOAuthAuthorizationDeniedError()

    def _store_credential(
        self,
        exchanged: MailboxOAuthAuthorizationResult,
    ) -> CommunicationCredentialRecord:
        try:
            return self._create_stored_credential(exchanged.secret_material)
        except CommunicationCredentialUnavailableError:
            raise ServiceUnavailableError(_UNAVAILABLE) from None
        except Exception:
            raise ServiceUnavailableError(_UNAVAILABLE) from None

    def _persist_connector_account(
        self,
        *,
        user_id: UUID,
        external_account_id: str,
        credential_ref: str,
        granted_capabilities: tuple[CommunicationCapability, ...],
        display_identity: str | None,
    ) -> tuple[ConnectorAccountRecord, bool]:
        try:
            with self._unit_of_work_factory() as uow:
                existing = uow.connector_accounts.find_by_owner_provider_external_account(
                    user_id,
                    _PROVIDER_SLUG,
                    external_account_id,
                )
                if existing is None:
                    created = uow.connector_accounts.create(
                        NewConnectorAccount(
                            user_id=user_id,
                            provider=_PROVIDER_SLUG,
                            external_account_id=external_account_id,
                            credential_ref=credential_ref,
                            granted_capabilities=granted_capabilities,
                            display_identity=display_identity,
                        )
                    )
                    uow.commit()
                    return created, False
                if existing.status is ConnectorAccountStatus.ACTIVE:
                    return existing, True
                if existing.status in {
                    ConnectorAccountStatus.DISCONNECTED,
                    ConnectorAccountStatus.REAUTH_REQUIRED,
                }:
                    reactivated = uow.connector_accounts.reactivate_owned(
                        existing.id,
                        user_id,
                        credential_ref,
                        granted_capabilities=granted_capabilities,
                        replace_granted_capabilities=True,
                        display_identity=display_identity,
                        replace_display_identity=display_identity is not None,
                    )
                    if reactivated is None:
                        raise PersistenceError("Could not persist connector account.")
                    uow.commit()
                    return reactivated, False
                raise PersistenceError("Could not persist connector account.")
        except PersistenceError as exc:
            logger.warning(
                "gmail_oauth_connector_account_persistence_failed",
                operation="callback",
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

    def _compensate_stored_credential(self, locator: str, started_at: float) -> None:
        try:
            self._credential_store.delete(locator)
        except Exception as exc:
            logger.warning(
                "gmail_oauth_credential_cleanup_failed",
                operation="callback",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None
