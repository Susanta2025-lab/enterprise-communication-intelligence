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
    profile_payload: object | None = None,
    profile_error: Exception | None = None,
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

    def profile(access_token: str) -> object:
        holder["profile_access_token"] = access_token
        if profile_error is not None:
            raise profile_error
        return profile_payload

    kwargs: dict[str, object] = {
        "client_id": _CLIENT_ID,
        "client_secret": _CLIENT_SECRET,
        "redirect_uri": _REDIRECT,
        "token_fetcher": fetch,
        "id_token_verifier": verify,
    }
    if profile_payload is not None or profile_error is not None:
        kwargs["profile_fetcher"] = profile
    return GoogleMailboxOAuthClient(**kwargs)  # type: ignore[arg-type]


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
    assert result.display_identity is None


def test_gmail_profile_email_is_display_only() -> None:
    captured: dict[str, str] = {}
    client = _client(
        token_response=_success_response(),
        captured=captured,
        profile_payload={"emailAddress": "ops.mailbox@contoso.example"},
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert captured["profile_access_token"] == _ACCESS
    assert result.external_account_id == _SUB
    assert result.display_identity == "ops.mailbox@contoso.example"
    assert result.external_account_id != result.display_identity
    assert b"ops.mailbox@contoso.example" not in result.secret_material


def test_gmail_profile_failure_keeps_display_identity_null() -> None:
    client = _client(
        token_response=_success_response(),
        profile_error=RuntimeError("profile down"),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.external_account_id == _SUB
    assert result.display_identity is None


def test_gmail_email_claim_is_not_used_as_display_identity() -> None:
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
    assert result.display_identity is None


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
    assert result.display_identity is None


def _exchange_failure_event(log_events: list[dict]) -> dict:
    matches = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_code_exchange_failed"
    ]
    assert len(matches) == 1
    return matches[0]


class _TokenRejected(Exception):
    error = "invalid_grant"


def test_google_error_code_is_logged_on_token_rejection(log_events: list[dict]) -> None:
    client = _client(token_error=_TokenRejected("rejected"))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    event = _exchange_failure_event(log_events)
    assert event["oauth_error"] == "invalid_grant"
    assert event["refresh_token_present"] is False
    assert event["id_token_present"] is False
    assert event["provider"] == "gmail"
    assert event["operation"] == "exchange_authorization_code"
    assert event["error_class"] == "MailboxOAuthAuthorizationFailedError"


def test_google_error_body_code_is_logged_without_tokens(log_events: list[dict]) -> None:
    client = _client(
        token_response={
            "error": "redirect_uri_mismatch",
            "error_description": "See Google Cloud Console",
        }
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    event = _exchange_failure_event(log_events)
    assert event["oauth_error"] == "redirect_uri_mismatch"
    assert event["refresh_token_present"] is False
    assert event["id_token_present"] is False
    assert "error_description" not in event


def test_missing_refresh_token_logs_presence_booleans(log_events: list[dict]) -> None:
    client = _client(token_response=_success_response(refresh_token=""))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    event = _exchange_failure_event(log_events)
    assert event["oauth_error"] is None
    assert event["refresh_token_present"] is False
    assert event["id_token_present"] is True
    assert event["refresh_token_present"] is not _REFRESH
    assert event["id_token_present"] is not _ID_TOKEN


def test_missing_id_token_logs_presence_booleans(log_events: list[dict]) -> None:
    client = _client(token_response=_success_response(id_token=None))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    event = _exchange_failure_event(log_events)
    assert event["oauth_error"] is None
    assert event["refresh_token_present"] is True
    assert event["id_token_present"] is False


def test_successful_exchange_omits_failure_diagnostics(log_events: list[dict]) -> None:
    client = _client(token_response=_success_response())
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.external_account_id == _SUB
    failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_code_exchange_failed"
    ]
    assert failed == []
    success = [
        event for event in log_events if event.get("event") == "gmail_oauth_code_exchanged"
    ]
    assert len(success) == 1
    assert "oauth_error" not in success[0]
    assert "refresh_token_present" not in success[0]
    assert "id_token_present" not in success[0]
    verify_failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_id_token_verify_failed"
    ]
    assert verify_failed == []


def _verify_failure_event(log_events: list[dict]) -> dict:
    matches = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_id_token_verify_failed"
    ]
    assert len(matches) == 1
    return matches[0]


def test_verification_exception_class_is_logged_safely(log_events: list[dict]) -> None:
    client = _client(
        token_response=_success_response(),
        verify_error=ValueError(f"invalid {_ID_TOKEN} sub={_SUB}"),
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    event = _verify_failure_event(log_events)
    assert event["provider"] == "gmail"
    assert event["operation"] == "verify_id_token"
    assert event["verify_error_class"] == "ValueError"
    assert "verify_error_reason" not in event
    assert event["subject_present"] is False
    assert "issuer_present" not in event
    assert "audience_present" not in event
    assert event["oauth_error"] is None
    assert event["refresh_token_present"] is True
    assert event["id_token_present"] is True
    assert _ID_TOKEN not in repr(event)
    assert _SUB not in repr(event)
    assert "invalid" not in str(event.get("verify_error_class"))


def test_missing_sub_records_subject_absent_from_verified_claims(
    log_events: list[dict],
) -> None:
    client = _client(
        token_response=_success_response(),
        claims={
            "iss": "https://accounts.google.com",
            "aud": _CLIENT_ID,
            "email": "mailbox@example.com",
        },
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    event = _verify_failure_event(log_events)
    assert event["verify_error_class"] == "MailboxOAuthAuthorizationFailedError"
    assert event["subject_present"] is False
    assert event["issuer_present"] is True
    assert event["audience_present"] is True
    assert "mailbox@example.com" not in repr(log_events)
    assert _SUB not in repr(event)


def test_blank_sub_records_subject_absent(log_events: list[dict]) -> None:
    client = _client(
        token_response=_success_response(),
        claims={"sub": "   ", "iss": "https://accounts.google.com", "aud": _CLIENT_ID},
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    event = _verify_failure_event(log_events)
    assert event["subject_present"] is False
    assert event["issuer_present"] is True
    assert event["audience_present"] is True
