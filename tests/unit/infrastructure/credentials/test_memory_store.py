"""Unit tests for the in-memory CommunicationCredentialStore."""

from __future__ import annotations

import threading

import pytest

from app.core.exceptions import (
    CommunicationCredentialConflictError,
    CommunicationCredentialUnavailableError,
)
from app.domain.interfaces import (
    CommunicationCredentialRecord,
    CommunicationCredentialStore,
    NewCommunicationCredential,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore

_LOCATOR = "oauth-memorystoretest01"
_PROVIDER = "gmail"
_SECRET = b"opaque-memory-secret-AAA"
_SECRET_TWO = b"opaque-memory-secret-BBB"


def _store() -> InMemoryCommunicationCredentialStore:
    return InMemoryCommunicationCredentialStore()


def _create(
    store: CommunicationCredentialStore,
    locator: str = _LOCATOR,
    provider: str = _PROVIDER,
    secret: bytes = _SECRET,
) -> CommunicationCredentialRecord:
    return store.create(NewCommunicationCredential(locator, provider, secret))


def test_store_implements_domain_port() -> None:
    assert isinstance(_store(), CommunicationCredentialStore)


def test_create_then_get_returns_material_provider_and_version() -> None:
    store = _store()
    created = _create(store)
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.credential_ref == _LOCATOR
    assert found.provider == _PROVIDER
    assert found.secret_material == _SECRET
    assert created.version == found.version
    assert isinstance(found.version, str)
    assert found.version


def test_unknown_locator_returns_none() -> None:
    assert _store().get("oauth-does-not-exist-01") is None


def test_duplicate_create_raises_conflict_and_does_not_overwrite() -> None:
    store = _store()
    first = _create(store)
    with pytest.raises(CommunicationCredentialConflictError) as exc_info:
        _create(store, secret=_SECRET_TWO)
    assert exc_info.value.message == "Communication credential could not be stored."
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == _SECRET
    assert found.version == first.version


def test_cas_replace_success_writes_new_version() -> None:
    store = _store()
    created = _create(store)
    replaced = store.replace_if_version(_LOCATOR, created.version, _SECRET_TWO)
    assert replaced is not None
    assert replaced.secret_material == _SECRET_TWO
    assert replaced.provider == _PROVIDER
    assert replaced.version != created.version
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == _SECRET_TWO
    assert found.version == replaced.version


def test_cas_stale_version_is_rejected() -> None:
    store = _store()
    created = _create(store)
    winner = store.replace_if_version(_LOCATOR, created.version, _SECRET_TWO)
    assert winner is not None
    stale = store.replace_if_version(_LOCATOR, created.version, b"stale-loser-material")
    assert stale is None
    found = store.get(_LOCATOR)
    assert found is not None
    assert found.secret_material == _SECRET_TWO
    assert found.version == winner.version


def test_replace_unknown_locator_returns_none() -> None:
    store = _store()
    assert store.replace_if_version(_LOCATOR, "missing-version", _SECRET_TWO) is None


def test_delete_removes_material() -> None:
    store = _store()
    _create(store)
    store.delete(_LOCATOR)
    assert store.get(_LOCATOR) is None


def test_repeated_delete_is_idempotent() -> None:
    store = _store()
    _create(store)
    store.delete(_LOCATOR)
    store.delete(_LOCATOR)
    store.delete("oauth-never-created-0001")
    assert store.get(_LOCATOR) is None


def test_provider_is_preserved_across_replacement() -> None:
    store = _store()
    created = _create(store, provider="microsoft_graph")
    replaced = store.replace_if_version(_LOCATOR, created.version, _SECRET_TWO)
    assert replaced is not None
    assert replaced.provider == "microsoft_graph"
    assert store.get(_LOCATOR) is not None
    assert store.get(_LOCATOR).provider == "microsoft_graph"


def test_secret_privacy_in_repr() -> None:
    store = _store()
    created = _create(store)
    blob = f"{store!r}{created!r}{store.get(_LOCATOR)!r}"
    assert _SECRET.decode() not in blob
    assert "opaque-memory-secret" not in blob
    assert created.secret_material not in blob.encode()
    assert "InMemoryCommunicationCredentialStore()" in repr(store)


def test_concurrent_creates_one_winner() -> None:
    store = _store()
    errors: list[Exception] = []
    winners: list[CommunicationCredentialRecord] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        try:
            winners.append(_create(store))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(winners) == 1
    assert winners[0].secret_material == _SECRET
    assert all(isinstance(exc, CommunicationCredentialConflictError) for exc in errors)
    assert len(errors) == 7


def test_malformed_locator_is_unavailable() -> None:
    store = _store()
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.get("bad locator")
    with pytest.raises(CommunicationCredentialUnavailableError):
        _create(store, locator="1leading-number")
