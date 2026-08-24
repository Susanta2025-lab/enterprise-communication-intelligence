"""Shared owned-mailbox access checks for listing and analyze.

Ownership lookup and mailbox-read eligibility live here so listing and
analyze keep the same pre-I/O policy. This module does not import Gmail or
Microsoft Graph types and does not perform credential or provider I/O.
"""

from collections.abc import Callable
from uuid import UUID

from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import ConnectorAccountStatus
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models.capabilities import is_mail_read_allowed

_ROUTABLE_PROVIDERS = frozenset({"gmail", "microsoft_graph"})


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
