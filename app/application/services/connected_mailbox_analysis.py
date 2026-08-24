"""Owned connected-mailbox message analysis orchestration.

Ownership and mailbox usability are established in a short persistence unit of
work. Credential resolution, mailbox HTTP, and AI inference happen only after
that unit of work has closed. This service does not import Gmail or Microsoft
Graph types and does not send mail.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import NoReturn
from uuid import UUID

from app.application.exceptions import (
    ConnectedMailboxNotAvailableError,
    ConnectorAccountNotFoundError,
    MailboxMessageNotFoundError,
)
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
    PersistedAnalysisOutcome,
)
from app.application.services.communication_ingestion import CommunicationIngestionService
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
    ConnectorMessageContentError,
    ConnectorMessageNotFoundError,
    ConnectorPermissionError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.interfaces.communication_connector_factory import (
    CommunicationConnectorFactory,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

logger = get_logger(__name__)

_PERSISTENCE_UNAVAILABLE = "Persistence is currently unavailable."
_TEMPORARY_UNAVAILABLE = "A required service dependency is currently unavailable."


class ConnectedMailboxAnalysisService:
    """Analyze one owned mailbox message through existing ingestion/analysis."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
        connector_factory: CommunicationConnectorFactory,
        analysis_workflow: CommunicationAnalysisWorkflowService,
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory
        self._connector_factory = connector_factory
        self._analysis_workflow = analysis_workflow

    def analyze(
        self,
        principal: AuthenticatedPrincipal,
        connector_account_id: UUID,
        provider_message_id: str,
    ) -> PersistedAnalysisOutcome:
        """Fetch an owned mailbox message and return existing analysis output."""
        started_at = time.perf_counter()
        account = self._load_usable_owned_account(principal, connector_account_id, started_at)
        try:
            connector = self._connector_factory.create_for_account(account)
        except CommunicationCredentialReauthorizationRequiredError as exc:
            self._reject_reauthorization_required(account, started_at, exc)
        except CommunicationConnectorNotAvailableError as exc:
            self._log_rejected("connector_unroutable", account, started_at, exc)
            raise ConnectedMailboxNotAvailableError() from None

        ingestion = CommunicationIngestionService(
            connector,
            self._analysis_workflow,
            connector_account_id=account.id,
        )
        try:
            outcome = ingestion.analyze_message(provider_message_id)
        except MailboxMessageNotFoundError:
            raise
        except ConnectedMailboxNotAvailableError:
            raise
        except ConnectorAccountNotFoundError:
            raise
        except ServiceUnavailableError:
            raise
        except ConnectorMessageNotFoundError as exc:
            self._log_rejected("message_not_found", account, started_at, exc)
            raise MailboxMessageNotFoundError() from None
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
            "connected_mailbox_analysis_completed",
            operation="analyze",
            provider=account.provider,
            connector_id=str(account.id),
            duration_ms=elapsed_ms(started_at),
        )
        return outcome

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
                "connected_mailbox_analysis_persistence_failed",
                operation="analyze",
                connector_id=str(connector_account_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_PERSISTENCE_UNAVAILABLE) from None

        if record is None:
            logger.info(
                "connected_mailbox_analysis_not_found",
                operation="analyze",
                connector_id=str(connector_account_id),
                duration_ms=elapsed_ms(started_at),
            )
            raise ConnectorAccountNotFoundError()
        if not is_usable_for_mailbox_read(record):
            logger.info(
                "connected_mailbox_analysis_not_available",
                operation="analyze",
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
            operation="analyze",
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
            "connected_mailbox_analysis_failed",
            operation="analyze",
            reason=reason,
            provider=account.provider,
            connector_id=str(account.id),
            duration_ms=elapsed_ms(started_at),
            error_class=error_class(exc),
        )
