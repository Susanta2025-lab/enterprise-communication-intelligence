"""SQLAlchemy-free identity persistence contract."""

from abc import ABC, abstractmethod
from uuid import UUID


class IdentityRepository(ABC):
    """Map an OIDC issuer and subject to an internal user UUID."""

    @abstractmethod
    def get_user_id_by_external_identity(self, issuer: str, subject: str) -> UUID | None:
        """Return the internal user id for ``(issuer, subject)``, if one exists."""

    @abstractmethod
    def get_application_role_for_user(self, user_id: UUID) -> str | None:
        """Return persisted ``application_role`` for ``user_id``, or ``None`` if missing.

        Returns the stored role string only. Callers must treat anything other
        than ``owner`` as non-owner. This method never infers role from JWT
        claims, email, mailbox identity, or client input.
        """

    @abstractmethod
    def user_has_external_identity(self, user_id: UUID) -> bool:
        """Return True when ``user_id`` has at least one External ID mapping."""

    @abstractmethod
    def count_users_with_application_role(self, role: str) -> int:
        """Return how many users currently have ``application_role=role``."""

    @abstractmethod
    def promote_user_role_from_user_to_owner(self, user_id: UUID) -> bool:
        """Conditionally set ``application_role`` from ``user`` to ``owner``.

        Updates exactly one row when ``user_id`` exists with role ``user``.
        Returns True when a row was updated. Never creates users. Never accepts
        arbitrary roles. Not for request-path authorization.
        """

    @abstractmethod
    def create_user_with_external_identity(self, issuer: str, subject: str) -> UUID:
        """Create a user and unique external identity mapping.

        Implementations must persist ordinary ``application_role=user`` only.
        This method must never accept, infer, or write ``owner``.

        Returns:
            The new internal user id.

        Raises:
            PersistenceError: if the ``(issuer, subject)`` pair is already registered
            or the write cannot be completed.
        """
