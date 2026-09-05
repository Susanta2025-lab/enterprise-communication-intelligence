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
    failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_code_exchange_failed"
    ]
    assert len(failed) == 1
    assert failed[0]["oauth_error"] is None
    assert failed[0]["refresh_token_present"] is False
    assert failed[0]["id_token_present"] is False
    verify_failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_id_token_verify_failed"
    ]
    assert verify_failed == []


def test_token_exchange_diagnostics_omit_secrets_and_descriptions(
    log_events: list[dict],
) -> None:
    from google.auth.exceptions import RefreshError

    class _ErrorBody:
        def json(self) -> dict[str, str]:
            return {
                "error": "invalid_client",
                "error_description": (
                    f"secret {_CLIENT_SECRET} {_CODE} {_VERIFIER} {_STATE} "
                    f"{_REFRESH} {_ACCESS} {_ID_TOKEN}"
                ),
            }

    class _HttpRejected(Exception):
        def __init__(self) -> None:
            super().__init__(f"token rejected {_REFRESH}")
            self.response = _ErrorBody()

    def fetch(_code: str, _verifier: str) -> dict:
        raise RefreshError(
            f"invalid_grant {_CODE} {_VERIFIER}",
            {
                "error": "invalid_grant",
                "error_description": f"revoked {_REFRESH} {_ACCESS} {_ID_TOKEN}",
            },
            retryable=False,
        )

    client = GoogleMailboxOAuthClient(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        redirect_uri="https://eci.example.invalid/callback",
        token_fetcher=fetch,
        id_token_verifier=lambda _token: {},
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)

    def fetch_http(_code: str, _verifier: str) -> dict:
        raise _HttpRejected()

    http_client = GoogleMailboxOAuthClient(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        redirect_uri="https://eci.example.invalid/callback",
        token_fetcher=fetch_http,
        id_token_verifier=lambda _token: {},
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        http_client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)

    missing = GoogleMailboxOAuthClient(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        redirect_uri="https://eci.example.invalid/callback",
        token_fetcher=lambda _code, _verifier: {
            "refresh_token": _REFRESH,
            "id_token": "",
            "access_token": _ACCESS,
            "error_description": f"missing {_ID_TOKEN}",
        },
        id_token_verifier=lambda _token: {},
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        missing.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)

    blob = repr(log_events)
    _assert_opaque(blob)
    assert "error_description" not in blob
    failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_code_exchange_failed"
    ]
    assert len(failed) == 3
    assert failed[0]["oauth_error"] == "invalid_grant"
    assert failed[0]["refresh_token_present"] is False
    assert failed[0]["id_token_present"] is False
    assert failed[1]["oauth_error"] == "invalid_client"
    assert failed[1]["refresh_token_present"] is False
    assert failed[1]["id_token_present"] is False
    assert failed[2]["oauth_error"] is None
    assert failed[2]["refresh_token_present"] is True
    assert failed[2]["id_token_present"] is False
    for event in failed:
        assert event["refresh_token_present"] in {True, False}
        assert event["id_token_present"] in {True, False}
        assert event.get("refresh_token") is None
        assert event.get("id_token") is None
        assert event.get("access_token") is None
        assert event.get("code") is None
        assert event.get("state") is None
        assert event.get("code_verifier") is None
        assert event.get("credential_ref") is None


def test_id_token_verify_failure_omits_token_claims_and_secrets(
    log_events: list[dict],
) -> None:
    email = "priv-mailbox@example.com"
    client = GoogleMailboxOAuthClient(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        redirect_uri="https://eci.example.invalid/callback",
        token_fetcher=lambda _code, _verifier: {
            "refresh_token": _REFRESH,
            "id_token": _ID_TOKEN,
            "access_token": _ACCESS,
        },
        id_token_verifier=lambda _token: (_ for _ in ()).throw(
            ValueError(
                f"invalid {_ID_TOKEN} sub={_SUB} email={email} "
                f"{_CODE} {_VERIFIER} {_STATE} {_CLIENT_SECRET} {_REFRESH}"
            )
        ),
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError) as exc_info:
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    blob = f"{exc_info.value}{exc_info.value!r}{exc_info.value.message}{log_events!r}"
    _assert_opaque(blob)
    assert email not in blob
    assert _SUB not in blob
    verify_failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_id_token_verify_failed"
    ]
    assert len(verify_failed) == 1
    event = verify_failed[0]
    assert event["verify_error_class"] == "ValueError"
    assert event.get("verify_error_reason") is None
    assert event["subject_present"] is False
    assert "issuer_present" not in event
    assert event.get("id_token") is None
    assert "invalid" not in event["verify_error_class"]
    for value in event.values():
        if isinstance(value, str):
            _assert_opaque(value)
            assert email not in value
            assert _SUB not in value


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
