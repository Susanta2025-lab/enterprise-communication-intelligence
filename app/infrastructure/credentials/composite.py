"""Composite resolver that routes OAuth locators separately from legacy locators.

Routing uses the server-generated ``oauth-`` locator prefix, not secret-store
paths. Legacy environment locators continue to use the environment resolver.
"""

from __future__ import annotations

from app.domain.interfaces.communication_credential_resolver import (
    AccessTokenProvider,
    CommunicationCredentialResolver,
)


class CompositeCommunicationCredentialResolver(CommunicationCredentialResolver):
    """Dispatch ``oauth-`` locators to the refreshable resolver."""

    def __init__(
        self,
        *,
        oauth_resolver: CommunicationCredentialResolver,
        environment_resolver: CommunicationCredentialResolver,
    ) -> None:
        self._oauth_resolver = oauth_resolver
        self._environment_resolver = environment_resolver

    def __repr__(self) -> str:
        return "CompositeCommunicationCredentialResolver()"

    def resolve(
        self,
        *,
        credential_ref: str,
        provider: str,
    ) -> AccessTokenProvider:
        payload = {"credential_ref": credential_ref, "provider": provider}
        if isinstance(credential_ref, str) and credential_ref.startswith("oauth-"):
            return self._oauth_resolver.resolve(**payload)
        return self._environment_resolver.resolve(**payload)
