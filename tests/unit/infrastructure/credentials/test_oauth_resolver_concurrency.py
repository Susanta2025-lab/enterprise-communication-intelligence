"""Per-credential locking tests for the refreshable resolver."""

from __future__ import annotations

import threading
import time

from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.refresh import RefreshableCredentialResult
from tests.unit.infrastructure.credentials.conftest import (
    FakeRefreshAdapter,
    MutableClock,
    build_resolver,
    seed_credential,
    usable_expiry,
)

_LOCATOR = "oauth-locklocator0000001"
_OTHER = "oauth-locklocator0000002"


def test_same_credential_concurrent_calls_acquire_once() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR, secret_material=b"shared-secret")
    clock = MutableClock()
    started = threading.Barrier(10)
    hold = threading.Event()
    entered = threading.Event()

    def factory(_provider: str, material: bytes) -> RefreshableCredentialResult:
        entered.set()
        hold.wait(timeout=2)
        return RefreshableCredentialResult(
            "shared-token",
            usable_expiry(clock),
            None,
        )

    adapter = FakeRefreshAdapter(factory=factory)
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    tokens: list[str] = []

    def worker() -> None:
        started.wait()
        tokens.append(provider())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    assert entered.wait(timeout=2)
    time.sleep(0.05)
    hold.set()
    for thread in threads:
        thread.join(timeout=2)
    assert len(tokens) == 10
    assert set(tokens) == {"shared-token"}
    assert len(adapter.calls) == 1


def test_different_credentials_are_not_globally_serialized() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR, secret_material=b"slow-secret")
    seed_credential(store, locator=_OTHER, secret_material=b"fast-secret")
    clock = MutableClock()
    slow_entered = threading.Event()
    fast_started = threading.Event()
    release_slow = threading.Event()
    order: list[str] = []

    def factory(_provider: str, material: bytes) -> RefreshableCredentialResult:
        if material == b"slow-secret":
            order.append("slow-enter")
            slow_entered.set()
            assert release_slow.wait(timeout=2)
            order.append("slow-exit")
            token = "slow-token"
        else:
            order.append("fast")
            fast_started.set()
            token = "fast-token"
        return RefreshableCredentialResult(token, usable_expiry(clock), None)

    adapter = FakeRefreshAdapter(factory=factory)
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    slow = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    fast = resolver.resolve(credential_ref=_OTHER, provider="gmail")
    results: dict[str, str] = {}

    def run_slow() -> None:
        results["slow"] = slow()

    def run_fast() -> None:
        assert slow_entered.wait(timeout=2)
        results["fast"] = fast()

    slow_thread = threading.Thread(target=run_slow)
    fast_thread = threading.Thread(target=run_fast)
    slow_thread.start()
    fast_thread.start()
    assert fast_started.wait(timeout=2)
    release_slow.set()
    slow_thread.join(timeout=2)
    fast_thread.join(timeout=2)
    assert results == {"slow": "slow-token", "fast": "fast-token"}
    assert "fast" in order
    assert order.index("fast") < order.index("slow-exit")
    assert len(adapter.calls) == 2
