"""Secret privacy tests for refreshable credential resolution."""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.refresh import RefreshableCredentialResult
from tests.unit.infrastructure.credentials.conftest import (
    FakeRefreshAdapter,
    MutableClock,
    build_resolver,
    seed_credential,
    usable_expiry,
)

_LOCATOR = "oauth-privacylocator001"
_ACCESS = "TOK_ACCESS_AAA_SECRET_111"
_REFRESH = b"TOK_REFRESH_BBB_SECRET_222"
_SERIALIZED = b"TOK_MSALCACHE_CCC_SECRET_333"
_MARKERS = (_ACCESS, _REFRESH.decode(), _SERIALIZED.decode(), _LOCATOR)


def _assert_opaque(blob: str) -> None:
    for marker in _MARKERS:
        assert marker not in blob


def test_repr_omits_token_and_secret_payload() -> None:
    store = InMemoryCommunicationCredentialStore()
    created = seed_credential(store, locator=_LOCATOR, secret_material=_SERIALIZED)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(
        token=_ACCESS,
        expires_at=usable_expiry(clock),
        replacement=_REFRESH,
    )
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    token = provider()
    found = store.get(_LOCATOR)
    blob = (
        f"{resolver!r}{store!r}{created!r}{found!r}{provider!r}{adapter!r}"
        f"{RefreshableCredentialResult(_ACCESS, usable_expiry(clock), _REFRESH)!r}"
    )
    _assert_opaque(blob)
    assert token == _ACCESS
    assert "OAuthCommunicationCredentialResolver()" in repr(resolver)


def test_exceptions_omit_secrets_and_locators() -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR, secret_material=_SERIALIZED)
    clock = MutableClock()
    adapter = FakeRefreshAdapter()
    adapter.error = RuntimeError(f"failed {_ACCESS} {_SERIALIZED.decode()}")
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError) as unavailable:
        provider()
    with pytest.raises(UnsupportedCommunicationCredentialProviderError) as unsupported:
        resolver.resolve(credential_ref=_LOCATOR, provider="google")
    adapter.error = CommunicationCredentialReauthorizationRequiredError()
    with pytest.raises(CommunicationCredentialReauthorizationRequiredError) as reauth:
        provider()
    blob = (
        f"{unavailable.value}{unavailable.value!r}{unavailable.value.message}"
        f"{unsupported.value}{unsupported.value!r}{reauth.value}{reauth.value!r}"
    )
    _assert_opaque(blob)
    assert "google" not in unsupported.value.message.lower()


def test_logs_omit_secrets_and_locators(log_events: list[dict]) -> None:
    store = InMemoryCommunicationCredentialStore()
    seed_credential(store, locator=_LOCATOR, secret_material=_SERIALIZED)
    clock = MutableClock()
    adapter = FakeRefreshAdapter(token=_ACCESS, expires_at=usable_expiry(clock))
    resolver = build_resolver(store, {"gmail": adapter}, clock=clock)
    provider = resolver.resolve(credential_ref=_LOCATOR, provider="gmail")
    assert provider() == _ACCESS
    with pytest.raises(UnsupportedCommunicationCredentialProviderError):
        resolver.resolve(credential_ref=_LOCATOR, provider="unknown")
    missing = resolver.resolve(credential_ref="oauth-missingprivacy001", provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        missing()
    blob = repr(log_events)
    _assert_opaque(blob)
    assert not any(event.get("credential_ref") for event in log_events)
    assert any(event.get("resolver_backend") == "oauth_refreshable" for event in log_events)
    assert any(event.get("store_backend") == "memory" for event in log_events)
    assert any(event.get("cache_status") == "miss" for event in log_events)
    assert any(
        event.get("event") == "communication_credential_token_acquired" for event in log_events
    )
    assert any(event.get("event") == "communication_credential_unavailable" for event in log_events)
    assert any(
        event.get("event") == "communication_credential_resolution_failed" for event in log_events
    )
