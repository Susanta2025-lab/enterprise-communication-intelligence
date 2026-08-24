"""Resolver laziness, provider mismatch, and Phase 12 factory compatibility."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.domain.enums import ConnectorAccountStatus
from app.domain.interfaces import CommunicationCredentialResolver
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.oauth import (
    OAuthCommunicationCredentialResolver,
    build_oauth_communication_credential_resolver,
)
from app.infrastructure.executors.factory import ProviderCommunicationActionExecutorFactory
from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor
from tests.unit.infrastructure.credentials.conftest import (
    CountingStore,
    FakeRefreshAdapter,
    build_resolver,
    seed_credential,
)

_LOCATOR = "oauth-resolverlazy0001"


def test_resolver_implements_domain_port() -> None:
    resolver = build_resolver(InMemoryCommunicationCredentialStore(), {})
    assert isinstance(resolver, CommunicationCredentialResolver)


def test_resolve_performs_no_store_or_adapter_io() -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter()
    resolver = build_resolver(store, {"gmail": adapter})

    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")

    assert callable(provider)
    assert store.gets == 0
    assert store.creates == 1
    assert store.replaces == 0
    assert adapter.calls == []


def test_token_callable_performs_store_and_adapter_work() -> None:
    store = CountingStore()
    record = seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter(token="live-token")
    resolver = build_resolver(store, {"gmail": adapter})
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")

    assert store.gets == 0
    assert adapter.calls == []
    assert provider() == "live-token"
    assert store.gets == 1
    assert adapter.calls == [("gmail", record.secret_material)]


def test_unsupported_provider_fails_at_resolve_without_io() -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter()
    resolver = build_resolver(store, {"gmail": adapter})
    with pytest.raises(UnsupportedCommunicationCredentialProviderError):
        resolver.resolve(credential_ref=_LOCATOR, provider="fake")
    assert store.gets == 0
    assert adapter.calls == []


def test_missing_adapter_fails_closed_at_resolve() -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR)
    resolver = build_resolver(store, {})
    with pytest.raises(UnsupportedCommunicationCredentialProviderError):
        resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert store.gets == 0


def test_provider_mismatch_fails_without_adapter_call() -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR, provider="gmail")
    gmail_adapter = FakeRefreshAdapter(token="gmail-token")
    graph_adapter = FakeRefreshAdapter(token="graph-token")
    resolver = build_resolver(
        store,
        {"gmail": gmail_adapter, "microsoft_graph": graph_adapter},
    )
    graph_provider = resolver.resolve(
        credential_ref=_LOCATOR,
        provider="microsoft_graph",
    )
    assert store.gets == 0
    assert graph_adapter.calls == []
    with pytest.raises(CommunicationCredentialUnavailableError):
        graph_provider()
    assert graph_adapter.calls == []
    assert gmail_adapter.calls == []
    assert store.gets == 1


def test_cached_gmail_token_is_not_returned_for_graph_mismatch() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR, provider="gmail")
    gmail_adapter = FakeRefreshAdapter(token="gmail-only-token")
    graph_adapter = FakeRefreshAdapter(token="graph-only-token")
    resolver = build_resolver(
        store,
        {"gmail": gmail_adapter, "microsoft_graph": graph_adapter},
    )
    gmail_token = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")()
    assert gmail_token == "gmail-only-token"
    graph_provider = resolver.resolve(
        credential_ref=_LOCATOR,
        provider="microsoft_graph",
    )
    with pytest.raises(CommunicationCredentialUnavailableError):
        graph_provider()
    assert graph_adapter.calls == []


def test_unknown_locator_fails_on_invocation() -> None:
    store = CountingStore()
    adapter = FakeRefreshAdapter()
    resolver = build_resolver(store, {"gmail": adapter})
    provider = resolver.resolve(credential_ref="oauth-missinglocator001", provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        provider()
    assert adapter.calls == []
    assert store.gets == 1


def test_blank_adapter_token_is_rejected() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter(token="   ")
    resolver = build_resolver(store, {"gmail": adapter})
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        provider()


def test_already_unusable_expiry_is_rejected() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter(expires_at=datetime(2026, 8, 22, 12, 4, tzinfo=UTC))
    resolver = build_resolver(store, {"gmail": adapter})
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        provider()


def test_naive_expiry_is_rejected() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter(expires_at=datetime(2030, 1, 1))
    resolver = build_resolver(store, {"gmail": adapter})
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        provider()


def test_reauthorization_required_propagates_from_adapter() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter()
    adapter.error = CommunicationCredentialReauthorizationRequiredError()
    resolver = build_resolver(store, {"gmail": adapter})
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    with pytest.raises(CommunicationCredentialReauthorizationRequiredError):
        provider()
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == b"opaque-secret-v1"


def test_adapter_exception_becomes_unavailable() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter()
    adapter.error = RuntimeError("provider exploded with secret")
    resolver = build_resolver(store, {"gmail": adapter})
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        provider()
    assert "provider exploded" not in exc_info.value.message
    assert "secret" not in exc_info.value.message.lower()


def test_build_hook_constructs_resolver_without_making_it_runtime_default() -> None:
    store = InMemoryCommunicationCredentialStore()
    adapter = FakeRefreshAdapter()
    resolver = build_oauth_communication_credential_resolver(
        store,
        {"gmail": adapter},
    )
    assert isinstance(resolver, OAuthCommunicationCredentialResolver)
    source = (Path(__file__).resolve().parents[4] / "app" / "api" / "dependencies.py").read_text(
        encoding="utf-8"
    )
    assert "EnvironmentCommunicationCredentialResolver" in source
    assert "OAuthCommunicationCredentialResolver" not in source


def test_executor_factory_does_not_invoke_oauth_token_provider() -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter()
    resolver = build_resolver(store, {"gmail": adapter})
    transport_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        transport_calls["count"] += 1
        return httpx.Response(599)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    factory = ProviderCommunicationActionExecutorFactory(
        credential_resolver=resolver,
        http_client=client,
    )
    now = datetime.now(UTC)
    try:
        executor = factory.create_for_account(
            ConnectorAccountRecord(
                id=uuid4(),
                user_id=uuid4(),
                provider="gmail",
                external_account_id="opaque-mailbox",
                credential_ref=_LOCATOR,
                status=ConnectorAccountStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    finally:
        client.close()

    assert isinstance(executor, GmailCommunicationActionExecutor)
    assert store.gets == 0
    assert adapter.calls == []
    assert transport_calls["count"] == 0


def test_aliases_are_rejected() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR)
    adapter = FakeRefreshAdapter()
    resolver = build_resolver(store, {"gmail": adapter})
    for provider in ("google", "Google", "msgraph", "graph"):
        with pytest.raises(UnsupportedCommunicationCredentialProviderError):
            resolver.resolve(credential_ref=_LOCATOR, provider=provider)
    assert adapter.calls == []
