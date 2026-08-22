"""Access-token cache and same-process invalidation tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.exceptions import CommunicationCredentialUnavailableError
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.refresh import RefreshableCredentialResult
from tests.unit.infrastructure.credentials.conftest import (
    CountingStore,
    FakeRefreshAdapter,
    MutableClock,
    build_resolver,
    seed_credential,
    usable_expiry,
)

_LOCATOR = "oauth-cachelocator00001"
_OTHER = "oauth-cachelocator00002"


def test_second_call_before_skew_is_a_cache_hit() -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(expires_at=usable_expiry(clock))
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")

    assert provider() == "access-token"
    assert adapter.calls == [("gmail", b"opaque-secret-v1")]
    assert store.gets == 1
    clock.now = clock.now + timedelta(minutes=1)
    assert provider() == "access-token"
    assert len(adapter.calls) == 1
    assert store.gets == 1


def test_near_expiry_token_is_refreshed() -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(expires_at=usable_expiry(clock, minutes=10))
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert provider() == "access-token"
    clock.now = clock.now + timedelta(minutes=6)
    adapter.token = "refreshed-token"
    adapter.expires_at = usable_expiry(clock, minutes=10)
    assert provider() == "refreshed-token"
    assert len(adapter.calls) == 2


def test_expired_token_is_refreshed() -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(expires_at=usable_expiry(clock, minutes=10))
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert provider() == "access-token"
    clock.now = clock.now + timedelta(minutes=11)
    adapter.token = "after-expiry"
    adapter.expires_at = usable_expiry(clock, minutes=10)
    assert provider() == "after-expiry"
    assert len(adapter.calls) == 2


def test_different_credential_refs_do_not_share_cache() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR, secret_material=b"secret-one")
    seed_credential(store, locator=_OTHER, secret_material=b"secret-two")
    clock = MutableClock()

    def factory(_provider: str, material: bytes) -> RefreshableCredentialResult:
        token = "token-one" if material == b"secret-one" else "token-two"
        return RefreshableCredentialResult(token, usable_expiry(clock), None)

    adapter = FakeRefreshAdapter(factory=factory, expires_at=usable_expiry(clock))
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    one = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    two = resolver.resolve(credential_ref=_OTHER, provider="gmail")
    assert one() == "token-one"
    assert two() == "token-two"
    assert len(adapter.calls) == 2
    assert one() == "token-one"
    assert two() == "token-two"
    assert len(adapter.calls) == 2


def test_different_providers_do_not_share_cache() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR, provider="gmail", secret_material=b"gmail-secret")
    seed_credential(
        store,
        locator=_OTHER,
        provider="microsoft_graph",
        secret_material=b"graph-secret",
    )
    clock = MutableClock()
    gmail = FakeRefreshAdapter(token="gmail-token", expires_at=usable_expiry(clock))
    graph = FakeRefreshAdapter(token="graph-token", expires_at=usable_expiry(clock))
    resolver = build_resolver(
        store,
        {"gmail": gmail, "microsoft_graph": graph},
        clock=clock,
    )
    gmail_provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    graph_provider = resolver.resolve(credential_ref=_OTHER, provider="microsoft_graph")
    assert gmail_provider() == "gmail-token"
    assert graph_provider() == "graph-token"
    assert len(gmail.calls) == 1
    assert len(graph.calls) == 1
    assert gmail_provider() == "gmail-token"
    assert graph_provider() == "graph-token"
    assert len(gmail.calls) == 1
    assert len(graph.calls) == 1


def test_delete_invalidates_cached_token() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(expires_at=usable_expiry(clock, minutes=60))
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert provider() == "access-token"
    store.delete(_LOCATOR)
    with pytest.raises(CommunicationCredentialUnavailableError):
        provider()
    assert len(adapter.calls) == 1


def test_store_replace_invalidates_cached_token() -> None:
    store = InMemoryCommunicationCredentialStore()
    created = seed_credential(store, locator=_LOCATOR, secret_material=b"v1-material")
    clock = MutableClock()

    def factory(_provider: str, material: bytes):
        token = "token-v1" if material == b"v1-material" else "token-v2"
        return FakeRefreshAdapter(
            token=token,
            expires_at=usable_expiry(clock, minutes=60),
        ).acquire_access_token(provider=_provider, secret_material=material)

    adapter = FakeRefreshAdapter(factory=factory)
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert provider() == "token-v1"
    store.replace_if_version(_LOCATOR, created.version, b"v2-material")
    assert provider() == "token-v2"
    assert len(adapter.calls) == 2
