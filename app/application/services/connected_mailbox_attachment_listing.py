"""Owned connected-mailbox attachment-metadata listing.

Ownership and mailbox usability are established in a short persistence unit
of work. Credential resolution and mailbox HTTP happen only after that unit
of work has closed. Listing returns metadata only: it does not retrieve
attachment bytes, invoke AI, persist analyses, create workflow actions, or
send mail.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import NoReturn
from uuid import UUID

from app.application.exceptions import (
    AttachmentNotSupportedError,
    ConnectedMailboxNotAvailableError,
    ConnectorAccountNotFoundError,
    MailboxMessageNotFoundError,
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
    ConnectorAttachmentMetadataError,
    ConnectorAuthenticationError,
    ConnectorMessageNotFoundError,
    ConnectorPermissionError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
    ConnectorUnsupportedAttachmentError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.interfaces.communication_connector import AttachmentMetadataPage
from app.domain.interfaces.communication_connector_factory import (
    CommunicationConnectorFactory,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models import AttachmentMetadata
from app.schemas.attachments import (
    ConnectorAccountAttachmentListItem,
    ConnectorAccountAttachmentListResponse,
)

logger = get_logger(__name__)

_PERSISTENCE_UNAVAILABLE = "Persistence is currently unavailable."
_TEMPORARY_UNAVAILABLE = "A required service dependency is currently unavailable."


class ConnectedMailboxAttachmentListingService:
    """List attachment metadata for one owned mailbox message."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
        connector_factory: CommunicationConnectorFactory,
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory
        self._connector_factory = connector_factory

    def list_attachments(
        self,
        principal: AuthenticatedPrincipal,
        connector_account_id: UUID,
        provider_message_id: str,
    ) -> ConnectorAccountAttachmentListResponse:
        """Return metadata for attachments on one owned mailbox message."""
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
            page = connector.list_attachments(provider_message_id)
            response = _to_public_list(page)
        except ConnectorMessageNotFoundError as exc:
            self._log_rejected("message_not_found", account, started_at, exc)
            raise MailboxMessageNotFoundError() from None
        except ConnectorUnsupportedAttachmentError as exc:
            self._log_rejected("unsupported_attachment", account, started_at, exc)
            raise AttachmentNotSupportedError() from None
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
        except ConnectorAttachmentMetadataError as exc:
            self._log_rejected("attachment_metadata_invalid", account, started_at, exc)
            raise

        logger.info(
            "attachment_metadata_listed",
            operation="list_attachments",
            provider=account.provider,
            connector_id=str(account.id),
            item_count=len(response.items),
            truncated=response.truncated,
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
                "connected_mailbox_attachment_list_persistence_failed",
                operation="list_attachments",
                connector_id=str(connector_account_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_PERSISTENCE_UNAVAILABLE) from None

        if record is None:
            logger.info(
                "connected_mailbox_attachment_list_not_found",
                operation="list_attachments",
                connector_id=str(connector_account_id),
                duration_ms=elapsed_ms(started_at),
            )
            raise ConnectorAccountNotFoundError()
        if not is_usable_for_mailbox_read(record):
            logger.info(
                "connected_mailbox_attachment_list_not_available",
                operation="list_attachments",
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
            operation="list_attachments",
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
            "connected_mailbox_attachment_list_failed",
            operation="list_attachments",
            reason=reason,
            provider=account.provider,
            connector_id=str(account.id),
            duration_ms=elapsed_ms(started_at),
            error_class=error_class(exc),
        )


def _to_public_list(page: AttachmentMetadataPage) -> ConnectorAccountAttachmentListResponse:
    return ConnectorAccountAttachmentListResponse(
        items=[_to_public_item(item) for item in page.items],
        truncated=page.truncated,
    )


def _to_public_item(item: AttachmentMetadata) -> ConnectorAccountAttachmentListItem:
    return ConnectorAccountAttachmentListItem(
        provider_attachment_id=item.provider_attachment_id,
        filename=item.filename,
        media_type=item.media_type,
        reported_size=item.reported_size,
        is_inline=item.is_inline,
        disposition=item.disposition,
    )
