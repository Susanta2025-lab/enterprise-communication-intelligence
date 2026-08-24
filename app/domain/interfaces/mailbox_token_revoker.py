"""Provider-neutral best-effort mailbox grant revocation.

Infrastructure adapters implement this port. Google SDK types must not appear
on this contract. Microsoft Graph has no app-scoped equivalent in ECI;
local credential deletion remains the disconnect guarantee there.
"""

from abc import ABC, abstractmethod


class MailboxTokenRevoker(ABC):
    """Revoke the delegated grant represented by stored secret material."""

    @abstractmethod
    def revoke(self, secret_material: bytes) -> None:
        """Revoke the provider grant encoded in ``secret_material``.

        Implementations must not log tokens or secret bytes. Remote failure
        is reported to the caller; the caller decides whether it is
        best-effort after a successful local disconnect.
        """
