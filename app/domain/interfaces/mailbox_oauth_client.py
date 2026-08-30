"""Provider-neutral mailbox authorization-code client.

Infrastructure adapters implement this port. Google SDK types must not appear
on this contract. Application code uses the returned opaque secret material
and provider-neutral capabilities only.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.domain.enums import CommunicationCapability


@dataclass(frozen=True, slots=True)
class MailboxOAuthAuthorizationResult:
    """Verified mailbox identity plus opaque refreshable credential material.

    ``display_identity`` is presentation-only and may be missing. It is never
    the durable ``external_account_id``.
    """

    external_account_id: str
    granted_capabilities: tuple[CommunicationCapability, ...]
    secret_material: bytes = field(repr=False)
    display_identity: str | None = None

    def __repr__(self) -> str:
        return (
            "MailboxOAuthAuthorizationResult("
            f"granted_capabilities={self.granted_capabilities!r}, "
            f"display_identity_present={self.display_identity is not None})"
        )


class MailboxOAuthClient(ABC):
    """Build a provider authorization URL and exchange a one-time code."""

    @abstractmethod
    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
        account_selection: bool = False,
    ) -> str:
        """Return the provider authorization URL for the supplied session.

        ``account_selection`` requests an explicit provider account picker.
        Reconnect must call this with ``False``.
        """

    @abstractmethod
    def exchange_authorization_code(
        self,
        *,
        code: str,
        code_verifier: str,
    ) -> MailboxOAuthAuthorizationResult:
        """Exchange a one-time code using the consumed PKCE verifier.

        Implementations must verify the provider identity assertion and must
        not return access tokens, ID tokens, or authorization codes.
        """
