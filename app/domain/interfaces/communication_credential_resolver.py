"""Vendor-neutral port that turns an opaque credential locator into a token capability.

This interface does not decide account ownership, workflow executability, or
which provider should send a message. It does not store tokens on domain
entities. Implementations must not leak secret-store, environment, or vendor
SDK types through the returned callable.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable

AccessTokenProvider = Callable[[], str]


class CommunicationCredentialResolver(ABC):
    """Resolve mailbox credential locators into an on-demand access-token callable."""

    @abstractmethod
    def resolve(
        self,
        *,
        credential_ref: str,
        provider: str,
    ) -> AccessTokenProvider:
        """Return a callable that supplies the current access token.

        ``credential_ref`` is an opaque locator, not token material.
        ``provider`` is the mailbox provider identity from ConnectorAccount.
        Secret lookup happens when the returned callable is invoked.
        """
