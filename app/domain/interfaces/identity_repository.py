"""SQLAlchemy-free identity persistence contract."""

from abc import ABC, abstractmethod
from uuid import UUID


class IdentityRepository(ABC):
    """Map an OIDC issuer and subject to an internal user UUID."""

    @abstractmethod
    def get_user_id_by_external_identity(self, issuer: str, subject: str) -> UUID | None:
        """Return the internal user id for ``(issuer, subject)``, if one exists."""

    @abstractmethod
    def create_user_with_external_identity(self, issuer: str, subject: str) -> UUID:
        """Create a user and unique external identity mapping.

        Returns:
            The new internal user id.

        Raises:
            PersistenceError: if the ``(issuer, subject)`` pair is already registered
            or the write cannot be completed.
        """
