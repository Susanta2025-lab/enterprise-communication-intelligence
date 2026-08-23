"""Google refresh adapter success and failure taxonomy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.infrastructure.oauth.google import (
    GMAIL_READONLY_SCOPE,
    GoogleRefreshableCredentialAdapter,
    deserialize_google_mailbox_secret,
    serialize_google_mailbox_secret,
)

_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_CLIENT_SECRET = "test-client-secret-sentinel"
_REFRESH = "REFRESH_TOKEN_SENTINEL_REFRESH_001"
_ACCESS = "ACCESS_TOKEN_SENTINEL_REFRESH_002"
_SUB = "google-subject-stable-001"


class _StaticGoogleCredentials:
    def __init__(
        self,
        *,
        token: str,
        expiry: datetime,
        refresh_token: str,
    ) -> None:
        self.token = token
        self.expiry = expiry
        self.refresh_token = refresh_token
        self.refresh_calls: list[object] = []

    def refresh(self, request: object) -> None:
        self.refresh_calls.append(request)


def _material(*, refresh: str = _REFRESH) -> bytes:
    return serialize_google_mailbox_secret(
        refresh_token=refresh,
        scopes=(GMAIL_READONLY_SCOPE,),
        subject=_SUB,
    )


def test_refresh_success_returns_access_token_without_persisting_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expiry = datetime.now(UTC) + timedelta(hours=1)
    creds = _StaticGoogleCredentials(
        token=_ACCESS,
        expiry=expiry,
        refresh_token=_REFRESH,
    )
    monkeypatch.setattr(
        "app.infrastructure.oauth.google._google_refresh_credentials",
        lambda **_kwargs: creds,
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        request_factory=lambda: object(),
    )
    result = adapter.acquire_access_token(provider="gmail", secret_material=_material())
    assert result.access_token == _ACCESS
    assert result.expires_at == expiry
    assert result.replacement_secret_material is None
    blob = f"{result!r}{adapter!r}"
    assert _ACCESS not in blob
    assert _REFRESH not in blob
    assert _CLIENT_SECRET not in blob


def test_rotated_refresh_token_returns_replacement_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rotated = "ROTATED_REFRESH_TOKEN_SENTINEL_003"
    expiry = datetime.now(UTC) + timedelta(hours=1)
    creds = _StaticGoogleCredentials(
        token=_ACCESS,
        expiry=expiry,
        refresh_token=rotated,
    )
    monkeypatch.setattr(
        "app.infrastructure.oauth.google._google_refresh_credentials",
        lambda **_kwargs: creds,
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        request_factory=lambda: object(),
    )
    result = adapter.acquire_access_token(provider="gmail", secret_material=_material())
    assert result.replacement_secret_material is not None
    stored = deserialize_google_mailbox_secret(result.replacement_secret_material)
    assert stored.refresh_token == rotated
    assert _ACCESS.encode() not in result.replacement_secret_material


def test_temporary_refresh_failure_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google.auth.exceptions import TransportError

    class _Boom:
        expiry = datetime.now(UTC) + timedelta(hours=1)
        token = _ACCESS
        refresh_token = _REFRESH

        def refresh(self, _request: object) -> None:
            raise TransportError("temporarily unreachable")

    monkeypatch.setattr(
        "app.infrastructure.oauth.google._google_refresh_credentials",
        lambda **_kwargs: _Boom(),
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        request_factory=lambda: object(),
    )
    with pytest.raises(CommunicationCredentialUnavailableError):
        adapter.acquire_access_token(provider="gmail", secret_material=_material())


def test_confirmed_invalid_grant_requires_reauthorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google.auth.exceptions import RefreshError

    class _Boom:
        expiry = datetime.now(UTC) + timedelta(hours=1)
        token = _ACCESS
        refresh_token = _REFRESH

        def refresh(self, _request: object) -> None:
            raise RefreshError(
                "invalid_grant: Token has been expired or revoked.",
                {"error": "invalid_grant"},
                retryable=False,
            )

    monkeypatch.setattr(
        "app.infrastructure.oauth.google._google_refresh_credentials",
        lambda **_kwargs: _Boom(),
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        request_factory=lambda: object(),
    )
    with pytest.raises(CommunicationCredentialReauthorizationRequiredError):
        adapter.acquire_access_token(provider="gmail", secret_material=_material())


def test_ambiguous_refresh_error_is_not_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google.auth.exceptions import RefreshError

    class _Boom:
        expiry = datetime.now(UTC) + timedelta(hours=1)
        token = _ACCESS
        refresh_token = _REFRESH

        def refresh(self, _request: object) -> None:
            raise RefreshError("something went wrong")

    monkeypatch.setattr(
        "app.infrastructure.oauth.google._google_refresh_credentials",
        lambda **_kwargs: _Boom(),
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        request_factory=lambda: object(),
    )
    with pytest.raises(CommunicationCredentialUnavailableError):
        adapter.acquire_access_token(provider="gmail", secret_material=_material())


def test_retryable_refresh_error_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google.auth.exceptions import RefreshError

    class _Boom:
        expiry = datetime.now(UTC) + timedelta(hours=1)
        token = _ACCESS
        refresh_token = _REFRESH

        def refresh(self, _request: object) -> None:
            raise RefreshError(
                "temporarily_unavailable",
                {"error": "temporarily_unavailable"},
                retryable=True,
            )

    monkeypatch.setattr(
        "app.infrastructure.oauth.google._google_refresh_credentials",
        lambda **_kwargs: _Boom(),
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        request_factory=lambda: object(),
    )
    with pytest.raises(CommunicationCredentialUnavailableError):
        adapter.acquire_access_token(provider="gmail", secret_material=_material())


def test_unsupported_provider_is_rejected() -> None:
    adapter = GoogleRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
    )
    with pytest.raises(UnsupportedCommunicationCredentialProviderError):
        adapter.acquire_access_token(provider="microsoft_graph", secret_material=_material())


def test_naive_expiry_is_made_timezone_aware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
    creds = _StaticGoogleCredentials(
        token=_ACCESS,
        expiry=expiry,
        refresh_token=_REFRESH,
    )
    monkeypatch.setattr(
        "app.infrastructure.oauth.google._google_refresh_credentials",
        lambda **_kwargs: creds,
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        request_factory=lambda: object(),
    )
    result = adapter.acquire_access_token(provider="gmail", secret_material=_material())
    assert result.expires_at.tzinfo is not None
