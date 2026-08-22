"""Compare-and-set rotation tests for the refreshable resolver."""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    CommunicationCredentialConflictError,
    CommunicationCredentialUnavailableError,
)
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    NewCommunicationCredential,
)
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

_LOCATOR = "oauth-caslocator0000001"
_V1 = b"opaque-cas-material-v1"
_V2 = b"opaque-cas-material-v2"
_WINNER = b"opaque-cas-winner-v2"
_STALE = b"opaque-cas-stale-loser"


class _OtherWriterStore(CountingStore):
    def __init__(self, winner_material: bytes) -> None:
        super().__init__(InMemoryCommunicationCredentialStore())
        self.winner_material = winner_material

    def replace_if_version(
        self,
        credential_ref: str,
        expected_version: str,
        secret_material: bytes,
    ) -> CommunicationCredentialRecord | None:
        current = self.inner.get(credential_ref)
        if current is not None and current.secret_material == _V1:
            self.inner.replace_if_version(
                credential_ref,
                current.version,
                self.winner_material,
            )
        return super().replace_if_version(
            credential_ref,
            expected_version,
            secret_material,
        )


class _AlwaysContendStore(CountingStore):
    def replace_if_version(
        self,
        credential_ref: str,
        expected_version: str,
        secret_material: bytes,
    ) -> CommunicationCredentialRecord | None:
        current = self.inner.get(credential_ref)
        if current is not None:
            self.inner.replace_if_version(
                credential_ref,
                current.version,
                _WINNER,
            )
        return super().replace_if_version(
            credential_ref,
            expected_version,
            secret_material,
        )


def test_cas_success_persists_rotated_material() -> None:
    store = InMemoryCommunicationCredentialStore()
    created = seed_credential(store, locator=_LOCATOR, secret_material=_V1)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(
        token="rotated-token",
        expires_at=usable_expiry(clock),
        replacement=_V2,
    )
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert provider() == "rotated-token"
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == _V2
    assert found.version != created.version
    assert found.provider == "gmail"
    assert len(adapter.calls) == 1


def test_unchanged_material_does_not_replace() -> None:
    store = CountingStore()
    created = seed_credential(store, locator=_LOCATOR, secret_material=_V1)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(
        token="same-material-token",
        expires_at=usable_expiry(clock),
        replacement=_V1,
    )
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert provider() == "same-material-token"
    assert store.replaces == 0
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.version == created.version
    assert found.secret_material == _V1


def test_stale_cas_rereads_winner_and_does_not_overwrite() -> None:
    store = _OtherWriterStore(_WINNER)
    seed_credential(store, locator=_LOCATOR, secret_material=_V1)
    clock = MutableClock()

    def factory(_provider: str, material: bytes) -> RefreshableCredentialResult:
        if material == _V1:
            return RefreshableCredentialResult(
                "stale-token",
                usable_expiry(clock),
                _STALE,
            )
        return RefreshableCredentialResult("winner-token", usable_expiry(clock), None)

    adapter = FakeRefreshAdapter(factory=factory)
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert provider() == "winner-token"
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == _WINNER
    assert found.secret_material != _STALE
    assert [material for _provider, material in adapter.calls] == [_V1, _WINNER]


def test_repeated_cas_contention_fails_closed_without_overwrite() -> None:
    store = _AlwaysContendStore()
    original = seed_credential(store, locator=_LOCATOR, secret_material=_V1)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(
        token="loser-token",
        expires_at=usable_expiry(clock),
        replacement=_STALE,
    )
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        provider()
    assert len(adapter.calls) == 2
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == _WINNER
    assert found.secret_material != _STALE
    assert found.version != original.version


def test_empty_replacement_is_rejected() -> None:
    store = InMemoryCommunicationCredentialStore()
    created = seed_credential(store, locator=_LOCATOR, secret_material=_V1)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(
        token="token",
        expires_at=usable_expiry(clock),
        replacement=b"",
    )
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        provider()
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == _V1
    assert found.version == created.version


def test_store_create_collision_never_used_as_blind_overwrite() -> None:
    store = InMemoryCommunicationCredentialStore()
    store.create(NewCommunicationCredential(_LOCATOR, "gmail", _V1))
    with pytest.raises(CommunicationCredentialConflictError):
        store.create(NewCommunicationCredential(_LOCATOR, "gmail", _STALE))
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == _V1
