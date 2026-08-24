"""Owned connected-mailbox bounded message listing orchestration.

Ownership and mailbox usability are established in a short persistence unit
of work. Credential resolution and mailbox HTTP happen only after that unit
of work has closed. Listing does not persist messages, invoke AI, create
workflow actions, or send mail. This service does not import Gmail or
Microsoft Graph types.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import NoReturn
from uuid import UUID

from app.application.exceptions import (
    ConnectedMailboxNotAvailableError,
    ConnectorAccountNotFoundError,
    MailboxPaginationCursorInvalidError,
)
from app.application.services.connected_mailbox_access import (
    is_usable_for_mailbox_read,
    load_owned_connector_account,
    persist_mailbox_reauthorization_required,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import (
    CommunicationConnectorNotAvailableError,
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ConnectorAuthenticationError,
    ConnectorInvalidCursorError,
    ConnectorMessageContentError,
    ConnectorPermissionError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.interfaces import ConnectorMessageQuery, MessagePage
from app.domain.interfaces.communication_connector_factory import (
    CommunicationConnectorFactory,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models import CommunicationMessage
from app.schemas.mailbox import (
    ConnectorAccountMessageListItem,
    ConnectorAccountMessageListQuery,
    ConnectorAccountMessageListResponse,
)

logger = get_logger(__name__)

_PERSISTENCE_UNAVAILABLE = "Persistence is currently unavailable."
_TEMPORARY_UNAVAILABLE = "A required service dependency is currently unavailable."


class ConnectedMailboxMessageListingService:
    """List a bounded page of owned mailbox metadata through existing connectors."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
        connector_factory: CommunicationConnectorFactory,
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory
        self._connector_factory = connector_factory

    def list_messages(
        self,
        principal: AuthenticatedPrincipal,
        connector_account_id: UUID,
        query: ConnectorAccountMessageListQuery,
    ) -> ConnectorAccountMessageListResponse:
        """Return one bounded provider-neutral mailbox page."""
        started_at = time.perf_counter()
        account = self._load_usable_owned_account(
            principal,
            connector_account_id,
            started_at,
        )
        try:
            connector = self._connector_factory.create_for_account(account)
        except CommunicationCredentialReauthorizationRequiredError as exc:
            self._reject_reauthorization_required(account, started_at, exc)
        except CommunicationConnectorNotAvailableError as exc:
            self._log_rejected("connector_unroutable", account, started_at, exc)
            raise ConnectedMailboxNotAvailableError() from None

        try:
            page = connector.list_messages(
                ConnectorMessageQuery(limit=query.page_size, cursor=query.cursor)
            )
            response = _to_public_list(page)
        except ConnectorInvalidCursorError as exc:
            self._log_rejected("invalid_cursor", account, started_at, exc)
            raise MailboxPaginationCursorInvalidError() from None
        except CommunicationCredentialReauthorizationRequiredError as exc:
            self._reject_reauthorization_required(account, started_at, exc)
        except CommunicationConnectorNotAvailableError as exc:
            self._log_rejected("connector_unroutable", account, started_at, exc)
            raise ConnectedMailboxNotAvailableError() from None
        except (
            CommunicationCredentialUnavailableError,
            ConnectorUnavailableError,
            ConnectorRateLimitError,
            ConnectorAuthenticationError,
            ConnectorPermissionError,
        ) as exc:
            self._log_rejected("temporary_unavailable", account, started_at, exc)
            raise ServiceUnavailableError(_TEMPORARY_UNAVAILABLE) from None
        except ConnectorMessageContentError as exc:
            self._log_rejected("message_content_invalid", account, started_at, exc)
            raise
        logger.info(
            "connected_mailbox_list_completed",
            operation="list",
            provider=account.provider,
            connector_id=str(account.id),
            duration_ms=elapsed_ms(started_at),
        )
        return response

    def _load_usable_owned_account(
        self,
        principal: AuthenticatedPrincipal,
        connector_account_id: UUID,
        started_at: float,
    ) -> ConnectorAccountRecord:
        try:
            record = load_owned_connector_account(
                self._identity_resolver,
                self._unit_of_work_factory,
                principal,
                connector_account_id,
            )
        except PersistenceError as exc:
            logger.warning(
                "connected_mailbox_list_persistence_failed",
                operation="list",
                connector_id=str(connector_account_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_PERSISTENCE_UNAVAILABLE) from None

        if record is None:
            logger.info(
                "connected_mailbox_list_not_found",
                operation="list",
                connector_id=str(connector_account_id),
                duration_ms=elapsed_ms(started_at),
            )
            raise ConnectorAccountNotFoundError()
        if not is_usable_for_mailbox_read(record):
            logger.info(
                "connected_mailbox_list_not_available",
                operation="list",
                provider=record.provider,
                connector_id=str(record.id),
                duration_ms=elapsed_ms(started_at),
            )
            raise ConnectedMailboxNotAvailableError()
        return record

    def _reject_reauthorization_required(
        self,
        account: ConnectorAccountRecord,
        started_at: float,
        exc: Exception,
    ) -> NoReturn:
        self._log_rejected("reauthorization_required", account, started_at, exc)
        persist_mailbox_reauthorization_required(
            self._unit_of_work_factory,
            account,
            operation="list",
            started_at=started_at,
        )
        raise ConnectedMailboxNotAvailableError() from None

    def _log_rejected(
        self,
        reason: str,
        account: ConnectorAccountRecord,
        started_at: float,
        exc: Exception,
    ) -> None:
        logger.warning(
            "connected_mailbox_list_failed",
            operation="list",
            reason=reason,
            provider=account.provider,
            connector_id=str(account.id),
            duration_ms=elapsed_ms(started_at),
            error_class=error_class(exc),
        )


def _to_public_list(page: MessagePage) -> ConnectorAccountMessageListResponse:
    """Project normalized messages onto the frozen mailbox-list contract."""
    return ConnectorAccountMessageListResponse(
        items=[_to_public_item(message) for message in page.items],
        next_cursor=page.next_cursor,
    )


def _to_public_item(message: CommunicationMessage) -> ConnectorAccountMessageListItem:
    provider_message_id = message.message_id
    if provider_message_id is None:
        raise ConnectorMessageContentError()
    return ConnectorAccountMessageListItem(
        provider_message_id=provider_message_id,
        sender=message.metadata.sender,
        subject=message.metadata.subject,
        sent_at=message.metadata.sent_at,
        received_at=message.metadata.received_at,
    )
