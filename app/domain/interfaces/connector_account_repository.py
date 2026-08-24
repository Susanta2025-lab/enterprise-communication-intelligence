"""SQLAlchemy-free connector-account persistence contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.enums import CommunicationCapability, ConnectorAccountStatus


@dataclass(frozen=True, slots=True)
class NewConnectorAccount:
    """Persistence-neutral input for storing a user-owned connector account."""

    user_id: UUID
    provider: str
    external_account_id: str
    credential_ref: str | None = None
    granted_capabilities: tuple[CommunicationCapability, ...] | None = None


@dataclass(frozen=True, slots=True)
class ConnectorAccountRecord:
    """Persistence-neutral stored connector account owned by a user.

    ``credential_ref`` is an opaque locator only. It must not leave the
    persistence boundary in application-facing results.
    """

    id: UUID
    user_id: UUID
    provider: str
    external_account_id: str
    credential_ref: str | None
    status: ConnectorAccountStatus
    created_at: datetime
    updated_at: datetime
    granted_capabilities: tuple[CommunicationCapability, ...] | None = None


class ConnectorAccountRepository(ABC):
    """Store and retrieve connector accounts with ownership enforced in every query.

    Methods do not commit. The caller owns the transaction.
    """

    @abstractmethod
    def create(self, account: NewConnectorAccount) -> ConnectorAccountRecord:
        """Insert an active connector account for ``account.user_id``."""

    @abstractmethod
    def find_by_owner_provider_external_account(
        self,
        user_id: UUID,
        provider: str,
        external_account_id: str,
    ) -> ConnectorAccountRecord | None:
        """Return the account for the owner and provider-native identity, if any."""

    @abstractmethod
    def get_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
    ) -> ConnectorAccountRecord | None:
        """Return the account only when it is owned by ``user_id``."""

    @abstractmethod
    def list_owned(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ConnectorAccountRecord]:
        """Return a bounded page of accounts owned by ``user_id``, newest first."""

    @abstractmethod
    def disconnect_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
    ) -> ConnectorAccountRecord | None:
        """Mark the owned account disconnected and clear locator plus grants.

        Repeated disconnect of an owned row remains disconnected with a null
        locator and unknown (``NULL``) ``granted_capabilities``. Capability
        metadata must not describe a grant after the credential is removed.
        Implementations may update ``updated_at`` on each owned write.

        Returns:
            The updated record when the id is owned by ``user_id``. None when the
            id is unknown or owned by a different user. Those cases are
            indistinguishable.
        """

    @abstractmethod
    def mark_reauth_required_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
    ) -> ConnectorAccountRecord | None:
        """Mark an owned ACTIVE account as reauthorization-required.

        Preserves ``credential_ref`` and ``granted_capabilities``. Does not
        match by locator alone. Non-ACTIVE owned rows are left unchanged
        and return None.

        Returns:
            The updated record when the owned row was ACTIVE. None when the
            id is unknown, not owned, or not ACTIVE.
        """

    @abstractmethod
    def reactivate_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
        credential_ref: str | None,
        *,
        granted_capabilities: tuple[CommunicationCapability, ...] | None = None,
        replace_granted_capabilities: bool = False,
    ) -> ConnectorAccountRecord | None:
        """Reactivate an owned disconnected or reauth-required account.

        Replaces ``credential_ref``. ``granted_capabilities`` stay unchanged
        unless ``replace_granted_capabilities`` is true.
        """
