"""Account-driven production read-connector factory.

This module selects Graph or Gmail readers from an already-owned connector
account. It does not query persistence, retrieve tokens, or call provider HTTP.
Ownership, ACTIVE status, and ``mail.read`` stay outside this factory.
"""

from __future__ import annotations

import httpx

from app.core.exceptions import (
    CommunicationConnectorNotAvailableError,
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.core.logging import get_logger
from app.core.telemetry import error_class
from app.domain.interfaces.communication_connector import CommunicationConnector
from app.domain.interfaces.communication_connector_factory import (
    CommunicationConnectorFactory,
)
from app.domain.interfaces.communication_credential_resolver import (
    CommunicationCredentialResolver,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.infrastructure.connectors.gmail import GmailCommunicationConnector
from app.infrastructure.connectors.microsoft_graph import (
    MicrosoftGraphCommunicationConnector,
)

logger = get_logger(__name__)

_SUPPORTED_PROVIDERS = frozenset({"gmail", "microsoft_graph"})


class ProviderCommunicationConnectorFactory(CommunicationConnectorFactory):
    """Configure a Graph or Gmail read connector from owned account routing data.

    ``credential_ref`` is resolved into an on-demand token callable. The callable
    is not invoked here. Fake and unknown providers are not routed.
    """

    def __init__(
        self,
        *,
        credential_resolver: CommunicationCredentialResolver,
        http_client: httpx.Client,
    ) -> None:
        self._credential_resolver = credential_resolver
        self._http_client = http_client

    def create_for_account(
        self,
        account: ConnectorAccountRecord,
    ) -> CommunicationConnector:
        """Return a configured production read connector for a routable account."""
        provider = account.provider
        if provider not in _SUPPORTED_PROVIDERS:
            raise CommunicationConnectorNotAvailableError()
        credential_ref = account.credential_ref
        if not isinstance(credential_ref, str) or not credential_ref.strip():
            raise CommunicationConnectorNotAvailableError()
        try:
            access_token_provider = self._credential_resolver.resolve(
                credential_ref=credential_ref,
                provider=provider,
            )
        except CommunicationCredentialReauthorizationRequiredError:
            raise
        except (
            CommunicationCredentialUnavailableError,
            UnsupportedCommunicationCredentialProviderError,
        ):
            raise CommunicationConnectorNotAvailableError() from None
        except Exception as exc:
            logger.warning(
                "communication_connector_unroutable",
                operation="create_for_account",
                provider=provider,
                error_class=error_class(exc),
            )
            raise CommunicationConnectorNotAvailableError() from None
        if provider == "gmail":
            return GmailCommunicationConnector(
                http_client=self._http_client,
                access_token_provider=access_token_provider,
            )
        return MicrosoftGraphCommunicationConnector(
            http_client=self._http_client,
            access_token_provider=access_token_provider,
        )
