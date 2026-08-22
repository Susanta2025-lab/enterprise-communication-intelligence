"""Account-driven production executor factory.

This module selects Graph or Gmail writers from an already-owned connector
account. It does not query persistence, retrieve tokens, or call provider HTTP.
"""

from __future__ import annotations

import httpx

from app.core.exceptions import (
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.core.logging import get_logger
from app.core.telemetry import error_class
from app.domain.interfaces.communication_action_executor import CommunicationActionExecutor
from app.domain.interfaces.communication_action_executor_factory import (
    CommunicationActionExecutorFactory,
)
from app.domain.interfaces.communication_credential_resolver import (
    CommunicationCredentialResolver,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor
from app.infrastructure.executors.microsoft_graph import (
    MicrosoftGraphCommunicationActionExecutor,
)

logger = get_logger(__name__)

_SUPPORTED_PROVIDERS = frozenset({"gmail", "microsoft_graph"})


class ProviderCommunicationActionExecutorFactory(CommunicationActionExecutorFactory):
    """Configure a Graph or Gmail executor from owned account routing data.

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
    ) -> CommunicationActionExecutor | None:
        """Return a configured production executor, or ``None`` if not routable."""
        provider = account.provider
        if provider not in _SUPPORTED_PROVIDERS:
            return None
        credential_ref = account.credential_ref
        if not isinstance(credential_ref, str) or not credential_ref.strip():
            return None
        try:
            access_token_provider = self._credential_resolver.resolve(
                credential_ref=credential_ref,
                provider=provider,
            )
        except (
            CommunicationCredentialUnavailableError,
            UnsupportedCommunicationCredentialProviderError,
        ):
            return None
        except Exception as exc:
            logger.warning(
                "communication_action_executor_unroutable",
                operation="create_for_account",
                provider=provider,
                error_class=error_class(exc),
            )
            return None
        if provider == "gmail":
            return GmailCommunicationActionExecutor(
                http_client=self._http_client,
                access_token_provider=access_token_provider,
            )
        return MicrosoftGraphCommunicationActionExecutor(
            http_client=self._http_client,
            access_token_provider=access_token_provider,
        )
