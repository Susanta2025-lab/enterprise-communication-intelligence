"""Secret-marker privacy tests for Google OAuth objects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import MailboxOAuthAuthorizationFailedError
from app.domain.enums import CommunicationCapability
from app.domain.interfaces.mailbox_oauth_client import MailboxOAuthAuthorizationResult
from app.infrastructure.oauth.google import (
    GMAIL_READONLY_SCOPE,
    GoogleMailboxOAuthClient,
    GoogleRefreshableCredentialAdapter,
    deserialize_google_mailbox_secret,
    serialize_google_mailbox_secret,
)

_CLIENT_SECRET = "PRIV_CLIENT_SECRET_SENTINEL_AAA"
_CODE = "PRIV_AUTH_CODE_SENTINEL_BBB"
_VERIFIER = "PRIV_PKCE_VERIFIER_SENTINEL_CCC_xxxxxxxx"
_STATE = "PRIV_OAUTH_STATE_SENTINEL_DDD"
_REFRESH = "PRIV_REFRESH_TOKEN_SENTINEL_EEE"
_ACCESS = "PRIV_ACCESS_TOKEN_SENTINEL_FFF"
_ID_TOKEN = "PRIV_ID_TOKEN_SENTINEL_GGG"
_SUB = "google-sub-privacy-001"
_MARKERS = (
    _CLIENT_SECRET,
    _CODE,
    _VERIFIER,
    _STATE,
    _REFRESH,
    _ACCESS,
    _ID_TOKEN,
)


def _assert_opaque(blob: str) -> None:
    for marker in _MARKERS:
        assert marker not in blob


def test_google_oauth_objects_omit_secrets_from_repr() -> None:
    material = serialize_google_mailbox_secret(
        refresh_token=_REFRESH,
        scopes=(GMAIL_READONLY_SCOPE,),
        subject=_SUB,
    )
    stored = deserialize_google_mailbox_secret(material)
    result = MailboxOAuthAuthorizationResult(
        external_account_id=_SUB,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
        secret_material=material,
    )
    client = GoogleMailboxOAuthClient(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        redirect_uri="https://eci.example.invalid/callback",
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
    )
    blob = f"{client!r}{adapter!r}{result!r}{stored!r}"
    _assert_opaque(blob)
    assert "GoogleMailboxOAuthClient()" in repr(client)
    assert "GoogleRefreshableCredentialAdapter()" in repr(adapter)


def test_google_revoke_omits_token_from_logs_and_repr(
    log_events: list[dict],
) -> None:
    from app.infrastructure.oauth.google import GoogleMailboxTokenRevoker

    seen: list[str] = []

    def transport(refresh_token: str) -> None:
        seen.append(refresh_token)

    revoker = GoogleMailboxTokenRevoker(transport=transport)
    material = serialize_google_mailbox_secret(
        refresh_token=_REFRESH,
        scopes=(GMAIL_READONLY_SCOPE,),
        subject=_SUB,
    )
    revoker.revoke(material)
    assert seen == [_REFRESH]
    blob = f"{revoker!r}{log_events!r}"
    _assert_opaque(blob)
    assert "GoogleMailboxTokenRevoker()" in repr(revoker)


def test_exchange_failures_omit_secrets(
    log_events: list[dict],
) -> None:
    def fetch(code: str, verifier: str) -> dict:
        raise RuntimeError(f"provider {_CODE} {_VERIFIER} {_CLIENT_SECRET}")

    client = GoogleMailboxOAuthClient(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        redirect_uri="https://eci.example.invalid/callback",
        token_fetcher=fetch,
        id_token_verifier=lambda _token: {},
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError) as exc_info:
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    blob = f"{exc_info.value}{exc_info.value!r}{exc_info.value.message}{log_events!r}"
    _assert_opaque(blob)


def test_refresh_failures_omit_secrets(
    monkeypatch: pytest.MonkeyPatch,
    log_events: list[dict],
) -> None:
    from google.auth.exceptions import RefreshError

    class _Boom:
        token = _ACCESS
        expiry = datetime.now(UTC) + timedelta(hours=1)
        refresh_token = _REFRESH

        def refresh(self, _request: object) -> None:
            raise RefreshError(
                f"invalid_grant {_REFRESH} {_ACCESS}",
                {"error": "invalid_grant", "error_description": f"revoked {_REFRESH}"},
                retryable=False,
            )

    monkeypatch.setattr(
        "app.infrastructure.oauth.google._google_refresh_credentials",
        lambda **_kwargs: _Boom(),
    )
    adapter = GoogleRefreshableCredentialAdapter(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        request_factory=lambda: object(),
    )
    material = serialize_google_mailbox_secret(
        refresh_token=_REFRESH,
        scopes=(GMAIL_READONLY_SCOPE,),
        subject=_SUB,
    )
    with pytest.raises(Exception) as exc_info:
        adapter.acquire_access_token(provider="gmail", secret_material=material)
    blob = f"{exc_info.value}{exc_info.value!r}{log_events!r}"
    _assert_opaque(blob)
    assert "error_description" not in blob
