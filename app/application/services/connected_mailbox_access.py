"""Shared owned-mailbox access checks and read-path lifecycle helpers.

Ownership lookup and mailbox-read eligibility live here so listing and
analyze keep the same pre-I/O policy. Confirmed permanent refresh failure
uses the existing Phase 13 owned ``mark_reauth_required_owned`` persistence
boundary. This module does not import Gmail or Microsoft Graph types and
does not perform credential or provider I/O.
"""

from collections.abc import Callable
from uuid import UUID

from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import ConnectorAccountStatus
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models.capabilities import is_mail_read_allowed

logger = get_logger(__name__)

_ROUTABLE_PROVIDERS = frozenset({"gmail", "microsoft_graph"})
_PERSISTENCE_UNAVAILABLE = "Persistence is currently unavailable."


def load_owned_connector_account(
    identity_resolver: IdentityResolver,
    unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    principal: AuthenticatedPrincipal,
    connector_account_id: UUID,
) -> ConnectorAccountRecord | None:
    """Return the exact owned account, or ``None`` when unknown or not owned.

    Missing internal users and unknown or cross-user accounts are
    indistinguishable. The unit of work is closed before this function
    returns. Persistence failures propagate as ``PersistenceError``.
    """
    user_id = identity_resolver.find_existing(principal)
    if user_id is None:
        return None
    with unit_of_work_factory() as uow:
        return uow.connector_accounts.get_owned(connector_account_id, user_id)


def is_usable_for_mailbox_read(account: ConnectorAccountRecord) -> bool:
    """Return whether an owned account may proceed to mailbox-read I/O."""
    if account.status is not ConnectorAccountStatus.ACTIVE:
        return False
    if account.provider not in _ROUTABLE_PROVIDERS:
        return False
    if not is_mail_read_allowed(account.granted_capabilities):
        return False
    locator = account.credential_ref
    return isinstance(locator, str) and bool(locator.strip())


def persist_mailbox_reauthorization_required(
    unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    account: ConnectorAccountRecord,
    *,
    operation: str,
    started_at: float,
) -> None:
    """Mark the exact owned ACTIVE account ``REAUTH_REQUIRED``.

    Uses a short mutation unit of work after credential I/O has already
    failed with confirmed permanent refresh failure. Mutates only
    ``connector_account_id`` + ``user_id`` from the ownership snapshot.
    Non-ACTIVE owned rows, including concurrent disconnect, are left
    unchanged. Persistence failure raises ``ServiceUnavailableError``
    without mailbox HTTP, AI, or credential replacement.
    """
    marked = None
    try:
        with unit_of_work_factory() as uow:
            marked = uow.connector_accounts.mark_reauth_required_owned(
                account.id,
                account.user_id,
            )
            if marked is not None:
                uow.commit()
    except PersistenceError as exc:
        logger.warning(
            "connected_mailbox_reauth_persist_failed",
            operation=operation,
            provider=account.provider,
            connector_id=str(account.id),
            duration_ms=elapsed_ms(started_at),
            error_class=error_class(exc),
        )
        raise ServiceUnavailableError(_PERSISTENCE_UNAVAILABLE) from None

    logger.info(
        "connected_mailbox_reauth_required",
        operation=operation,
        provider=account.provider,
        connector_id=str(account.id),
        duration_ms=elapsed_ms(started_at),
        mutated=marked is not None,
    )
