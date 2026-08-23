"""Composite credential resolver routing tests."""

from __future__ import annotations

from app.infrastructure.credentials.composite import CompositeCommunicationCredentialResolver
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.oauth import OAuthCommunicationCredentialResolver
from tests.unit.infrastructure.credentials.conftest import FakeRefreshAdapter, seed_credential


class _RecordingEnv(EnvironmentCommunicationCredentialResolver):
    def __init__(self) -> None:
        super().__init__(environ={})
        self.calls: list[tuple[str, str]] = []

    def resolve(self, *, credential_ref: str, provider: str):
        self.calls.append((credential_ref, provider))
        return super().resolve(credential_ref=credential_ref, provider=provider)


def test_oauth_prefix_routes_to_oauth_resolver_not_environment() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator="oauth-sharedlocator0001", secret_material=b"secret")
    adapter = FakeRefreshAdapter(token="oauth-token")
    oauth = OAuthCommunicationCredentialResolver(store, {"gmail": adapter})
    environment = _RecordingEnv()
    resolver = CompositeCommunicationCredentialResolver(
        oauth_resolver=oauth,
        environment_resolver=environment,
    )
    provider = resolver.resolve(credential_ref="oauth-sharedlocator0001", provider="gmail")
    assert provider() == "oauth-token"
    assert environment.calls == []
    assert adapter.calls


def test_legacy_locator_uses_environment_resolver() -> None:
    store = InMemoryCommunicationCredentialStore()
    adapter = FakeRefreshAdapter()
    oauth = OAuthCommunicationCredentialResolver(store, {"gmail": adapter})
    environment = EnvironmentCommunicationCredentialResolver(
        environ={"ECI_COMMUNICATION_CREDENTIAL_GMAIL_DEMO_ACCOUNT_ACCESS_TOKEN": "env-token"}
    )
    resolver = CompositeCommunicationCredentialResolver(
        oauth_resolver=oauth,
        environment_resolver=environment,
    )
    provider = resolver.resolve(credential_ref="demo-account", provider="gmail")
    assert provider() == "env-token"
    assert adapter.calls == []
