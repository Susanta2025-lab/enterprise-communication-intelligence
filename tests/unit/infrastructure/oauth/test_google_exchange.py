"""Google authorization-code exchange and ID-token verification tests."""

from __future__ import annotations

import pytest

from app.core.exceptions import MailboxOAuthAuthorizationFailedError, ServiceUnavailableError
from app.domain.enums import CommunicationCapability
from app.infrastructure.oauth.google import (
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
    GoogleMailboxOAuthClient,
    deserialize_google_mailbox_secret,
)

_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_CLIENT_SECRET = "test-client-secret-sentinel"
_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/gmail"
_CODE = "AUTH_CODE_SENTINEL_111"
_VERIFIER = "pkce-verifier-sentinel-222-xxxxxxxxxxxxxxxxxxxx"
_REFRESH = "REFRESH_TOKEN_SENTINEL_333"
_ID_TOKEN = "ID_TOKEN_SENTINEL_444"
_ACCESS = "ACCESS_TOKEN_SENTINEL_555"
_SUB = "google-subject-stable-001"


def _client(
    *,
    token_response: dict | None = None,
    token_error: Exception | None = None,
    claims: dict | None = None,
    verify_error: Exception | None = None,
    captured: dict | None = None,
) -> GoogleMailboxOAuthClient:
    holder = captured if captured is not None else {}

    def fetch(code: str, verifier: str) -> dict:
        holder["code"] = code
        holder["verifier"] = verifier
        if token_error is not None:
            raise token_error
        return token_response or {}

    def verify(token: str) -> dict:
        holder["id_token"] = token
        if verify_error is not None:
            raise verify_error
        return claims or {"sub": _SUB, "iss": "https://accounts.google.com", "aud": _CLIENT_ID}

    return GoogleMailboxOAuthClient(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        redirect_uri=_REDIRECT,
        token_fetcher=fetch,
        id_token_verifier=verify,
    )


def _success_response(**overrides: object) -> dict:
    payload: dict[str, object] = {
        "refresh_token": _REFRESH,
        "id_token": _ID_TOKEN,
        "access_token": _ACCESS,
        "scope": f"openid {GMAIL_READONLY_SCOPE} {GMAIL_SEND_SCOPE}",
    }
    payload.update(overrides)
    return payload


def test_exchange_uses_consumed_verifier_and_verified_sub() -> None:
    captured: dict[str, str] = {}
    client = _client(token_response=_success_response(), captured=captured)
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert captured["code"] == _CODE
    assert captured["verifier"] == _VERIFIER
    assert captured["id_token"] == _ID_TOKEN
    assert result.external_account_id == _SUB
    assert result.granted_capabilities == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )
    stored = deserialize_google_mailbox_secret(result.secret_material)
    assert stored.refresh_token == _REFRESH
    assert stored.subject == _SUB
    assert GMAIL_READONLY_SCOPE in stored.scopes
    assert GMAIL_SEND_SCOPE in stored.scopes
    assert _ACCESS.encode() not in result.secret_material
    assert _ID_TOKEN.encode() not in result.secret_material
    assert _CODE.encode() not in result.secret_material
    assert _CLIENT_SECRET.encode() not in result.secret_material


def test_invalid_id_token_is_rejected() -> None:
    client = _client(
        token_response=_success_response(),
        verify_error=ValueError("invalid token"),
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_wrong_audience_is_rejected() -> None:
    client = _client(
        token_response=_success_response(),
        verify_error=ValueError("Token has wrong audience"),
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_wrong_issuer_is_rejected() -> None:
    client = _client(
        token_response=_success_response(),
        verify_error=ValueError("Wrong issuer."),
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_missing_refresh_token_is_rejected() -> None:
    client = _client(token_response=_success_response(refresh_token=""))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_missing_id_token_is_rejected() -> None:
    client = _client(token_response=_success_response(id_token=None))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_partial_grant_maps_read_only_capabilities() -> None:
    client = _client(
        token_response=_success_response(scope=f"openid {GMAIL_READONLY_SCOPE}"),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.granted_capabilities == (CommunicationCapability.MAIL_READ,)
    assert CommunicationCapability.MAIL_SEND not in result.granted_capabilities


def test_send_without_read_does_not_invent_read_capability() -> None:
    client = _client(
        token_response=_success_response(scope=f"openid {GMAIL_SEND_SCOPE}"),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.granted_capabilities == (CommunicationCapability.MAIL_SEND,)


def test_transport_failure_during_exchange_is_unavailable() -> None:
    from google.auth.exceptions import TransportError

    client = _client(
        token_response=_success_response(),
        token_error=TransportError("network down"),
    )
    with pytest.raises(ServiceUnavailableError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_email_claim_is_not_used_as_identity() -> None:
    client = _client(
        token_response=_success_response(),
        claims={
            "sub": _SUB,
            "email": "mailbox@example.com",
            "iss": "https://accounts.google.com",
            "aud": _CLIENT_ID,
        },
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.external_account_id == _SUB
    assert result.external_account_id != "mailbox@example.com"
    assert b"mailbox@example.com" not in result.secret_material
