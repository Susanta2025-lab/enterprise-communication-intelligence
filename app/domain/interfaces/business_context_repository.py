"""SQLAlchemy-free BusinessContext persistence contract."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.enums import BusinessContextStatus, BusinessContextType
from app.domain.models.business_context import BusinessContext


class BusinessContextRepository(ABC):
    """Store and retrieve business contexts with ownership enforced in every query.

    Methods do not commit. The caller owns the transaction. Cross-user and
    unknown ids are indistinguishable (``None``). Platform Owner role does not
    widen these lookups.
    """

    @abstractmethod
    def add(self, context: BusinessContext) -> BusinessContext:
        """Persist ``context`` and return the stored domain object."""

    @abstractmethod
    def get_owned(self, context_id: UUID, user_id: UUID) -> BusinessContext | None:
        """Return the context only when it is owned by ``user_id``."""

    @abstractmethod
    def list_owned(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
        *,
        status: BusinessContextStatus | None = BusinessContextStatus.ACTIVE,
        type: BusinessContextType | None = None,
        reference: str | None = None,
    ) -> list[BusinessContext]:
        """Return a bounded page of contexts owned by ``user_id``, newest first.

        Default ``status`` is ``ACTIVE``. Pass ``None`` to include every status.
        Optional ``type`` and ``reference`` narrow the page with exact match.
        """

    @abstractmethod
    def save_owned(self, context: BusinessContext) -> BusinessContext | None:
        """Persist mutable and lifecycle fields for an owned context.

        Returns the stored object when ``context.id`` is owned by
        ``context.owner_user_id``. Returns ``None`` when the id is unknown or
        owned by a different user.
        """
