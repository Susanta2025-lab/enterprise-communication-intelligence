"""Shared persist path for mailbox REAUTHORIZE callbacks.

CONNECT persist stays on each provider OAuth service. This helper only attaches
a new credential to the exact bound connector account after identity match.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.exceptions import ConnectorAccountConflictError
from app.core.exceptions import (
    MailboxOAuthAuthorizationFailedError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.logging import get_logger
from app.core.telemetry import error_class
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

logger = get_logger(__name__)


def load_reauthorization_target(
    unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    *,
    user_id: UUID,
    connector_account_id: UUID,
    provider: str,
    external_account_id: str,
    unavailable_message: str,
) -> ConnectorAccountRecord:
    """Load the exact bound account and validate identity before attach.

    Does not mutate the account. Raises ``MailboxOAuthAuthorizationFailedError``
    when identity, provider, or binding validation fails. Raises
    ``ConnectorAccountConflictError`` when the account is not reactivatable.
    """
    try:
        with unit_of_work_factory() as uow:
            bound = uow.connector_accounts.get_owned(connector_account_id, user_id)
    except PersistenceError as exc:
        logger.warning(
            "mailbox_oauth_reauthorize_load_failed",
            operation="callback",
            error_class=error_class(exc),
        )
        raise ServiceUnavailableError(unavailable_message) from None
    if bound is None:
        raise MailboxOAuthAuthorizationFailedError()
    if bound.provider != provider:
        raise MailboxOAuthAuthorizationFailedError()
    if bound.external_account_id != external_account_id:
        raise MailboxOAuthAuthorizationFailedError()
    if bound.status not in {
        ConnectorAccountStatus.DISCONNECTED,
        ConnectorAccountStatus.REAUTH_REQUIRED,
    }:
        raise ConnectorAccountConflictError()
    return bound


def persist_reauthorized_connector_account(
    unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    *,
    user_id: UUID,
    connector_account_id: UUID,
    provider: str,
    external_account_id: str,
    credential_ref: str,
    granted_capabilities: tuple[CommunicationCapability, ...],
    unavailable_message: str,
) -> ConnectorAccountRecord:
    """Attach a new locator to the exact bound account.

    Compare-and-set reactivation yields at most one winner. A concurrent
    loser observes None and must compensate its newly created credential.
    """
    try:
        with unit_of_work_factory() as uow:
            bound = uow.connector_accounts.get_owned(connector_account_id, user_id)
            if bound is None:
                raise MailboxOAuthAuthorizationFailedError()
            if bound.provider != provider:
                raise MailboxOAuthAuthorizationFailedError()
            if bound.external_account_id != external_account_id:
                raise MailboxOAuthAuthorizationFailedError()
            if bound.status not in {
                ConnectorAccountStatus.DISCONNECTED,
                ConnectorAccountStatus.REAUTH_REQUIRED,
            }:
                raise ConnectorAccountConflictError()
            reactivated = uow.connector_accounts.reactivate_owned(
                bound.id,
                user_id,
                credential_ref,
                granted_capabilities=granted_capabilities,
                replace_granted_capabilities=True,
            )
            if reactivated is None:
                raise ConnectorAccountConflictError()
            uow.commit()
            return reactivated
    except (MailboxOAuthAuthorizationFailedError, ConnectorAccountConflictError):
        raise
    except PersistenceError as exc:
        logger.warning(
            "mailbox_oauth_reauthorize_persist_failed",
            operation="callback",
            error_class=error_class(exc),
        )
        raise ServiceUnavailableError(unavailable_message) from None
    except ServiceUnavailableError:
        raise
    except Exception as exc:
        logger.warning(
            "mailbox_oauth_reauthorize_persist_failed",
            operation="callback",
            error_class=error_class(exc),
        )
        raise ServiceUnavailableError(unavailable_message) from None
