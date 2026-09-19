"""SQLAlchemy-free BusinessContext communication-link persistence contract."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.models.business_context_communication_link import (
    BusinessContextCommunicationLink,
)


class BusinessContextCommunicationLinkRepository(ABC):
    """Store and retrieve provenance links with ownership enforced in every query.

    Methods do not commit. The caller owns the transaction. Cross-user and
    unknown ids are indistinguishable (``None`` / ``False``). Platform Owner
    role does not widen these lookups.
    """

    @abstractmethod
    def add(
        self, link: BusinessContextCommunicationLink
    ) -> BusinessContextCommunicationLink:
        """Persist ``link`` and return the stored domain object.

        Implementations must reject duplicate
        ``(business_context_id, connector_account_id, provider_message_id)``
        via the unique constraint. Callers translate uniqueness failures to
        application conflict errors.
        """

    @abstractmethod
    def get_owned(
        self, link_id: UUID, user_id: UUID
    ) -> BusinessContextCommunicationLink | None:
        """Return the link only when it is owned by ``user_id``."""

    @abstractmethod
    def get_by_provenance_owned(
        self,
        business_context_id: UUID,
        connector_account_id: UUID,
        provider_message_id: str,
        user_id: UUID,
    ) -> BusinessContextCommunicationLink | None:
        """Return the owned link for the unique provenance triple, if any."""

    @abstractmethod
    def list_for_context_owned(
        self,
        business_context_id: UUID,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> list[BusinessContextCommunicationLink]:
        """Return a bounded page of links for an owned context, newest first.

        Rows are filtered by both ``business_context_id`` and ``user_id``.
        Unknown or cross-user contexts yield an empty page.
        """

    @abstractmethod
    def remove_owned(self, link_id: UUID, user_id: UUID) -> bool:
        """Delete the association row only when owned by ``user_id``.

        Returns True when a row was deleted. False when the id is unknown or
        owned by a different user. Those cases are indistinguishable. Never
        deletes analyses, workflows, connectors, or provider mail.
        """
