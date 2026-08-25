"""Offline Google ID-token verification diagnostics and validation tests."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from google.auth import jwt as google_jwt
from google.auth.crypt import RSASigner
from google.auth.exceptions import GoogleAuthError, InvalidValue, MalformedError

from app.core.exceptions import MailboxOAuthAuthorizationFailedError, ServiceUnavailableError
from app.infrastructure.oauth.google import (
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
    GoogleMailboxOAuthClient,
    deserialize_google_mailbox_secret,
)

_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_CLIENT_SECRET = "test-client-secret-sentinel"
_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/gmail"
_CODE = "AUTH_CODE_SENTINEL_VERIFY_111"
_VERIFIER = "pkce-verifier-sentinel-verify-222-xxxxxxxx"
_REFRESH = "REFRESH_TOKEN_SENTINEL_VERIFY_333"
_ACCESS = "ACCESS_TOKEN_SENTINEL_VERIFY_555"
_SUB = "google-subject-verify-001"
_EMAIL = "mailbox-verify@example.com"
_KID = "eci-google-test-kid"
_GOOGLE_ISSUER = "https://accounts.google.com"


def _private_key_pem() -> bytes:
    key = generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_pem_from_private(private_pem: bytes) -> str:
    key = serialization.load_pem_private_key(private_pem, password=None)
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def _sign_id_token(
    private_pem: bytes,
    *,
    audience: str = _CLIENT_ID,
    issuer: str = _GOOGLE_ISSUER,
    subject: str | None = _SUB,
    now: int | None = None,
    lifetime_seconds: int = 3600,
    issued_offset_seconds: int = 0,
    extra_claims: dict[str, object] | None = None,
) -> str:
    signer = RSASigner.from_string(private_pem, key_id=_KID)
    issued_at = (now if now is not None else int(time.time())) + issued_offset_seconds
    payload: dict[str, object] = {
        "iss": issuer,
        "aud": audience,
        "iat": issued_at,
        "exp": issued_at + lifetime_seconds,
    }
    if subject is not None:
        payload["sub"] = subject
    if extra_claims:
        payload.update(extra_claims)
    encoded = google_jwt.encode(signer, payload, key_id=_KID)
    if isinstance(encoded, bytes):
        return encoded.decode("ascii")
    return encoded


def _install_cert_request(
    monkeypatch: pytest.MonkeyPatch,
    public_pem: str,
    *,
    calls: list[str] | None = None,
) -> None:
    certs = {_KID: public_pem}

    class _CertRequest:
        def __call__(self, url: str, method: str = "GET", **_kwargs: object) -> SimpleNamespace:
            if calls is not None:
                calls.append(url)
            return SimpleNamespace(status=200, data=json.dumps(certs).encode("utf-8"))

    monkeypatch.setattr("google.auth.transport.requests.Request", _CertRequest)


def _client(*, id_token: str) -> GoogleMailboxOAuthClient:
    def fetch(_code: str, _verifier: str) -> dict[str, object]:
        return {
            "refresh_token": _REFRESH,
            "id_token": id_token,
            "access_token": _ACCESS,
            "scope": f"openid {GMAIL_READONLY_SCOPE} {GMAIL_SEND_SCOPE}",
        }

    return GoogleMailboxOAuthClient(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        redirect_uri=_REDIRECT,
        token_fetcher=fetch,
    )


def _verify_failure_event(log_events: list[dict]) -> dict:
    matches = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_id_token_verify_failed"
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_logs_omit_secrets(log_events: list[dict], *extra: str) -> None:
    blob = repr(log_events)
    markers = (
        _CLIENT_SECRET,
        _CODE,
        _VERIFIER,
        _REFRESH,
        _ACCESS,
        _SUB,
        _EMAIL,
        *extra,
    )
    for marker in markers:
        assert marker not in blob
    for event in log_events:
        assert event.get("id_token") is None
        assert event.get("sub") is None
        assert event.get("email") is None
        assert event.get("code") is None
        assert event.get("code_verifier") is None
        assert event.get("state") is None
        assert event.get("client_secret") is None
        assert event.get("credential_ref") is None


def test_valid_verified_token_extracts_subject_without_verify_failure_log(
    monkeypatch: pytest.MonkeyPatch,
    log_events: list[dict],
) -> None:
    private_pem = _private_key_pem()
    token = _sign_id_token(private_pem, extra_claims={"email": _EMAIL})
    _install_cert_request(monkeypatch, _public_pem_from_private(private_pem))
    result = _client(id_token=token).exchange_authorization_code(
        code=_CODE,
        code_verifier=_VERIFIER,
    )
    assert result.external_account_id == _SUB
    stored = deserialize_google_mailbox_secret(result.secret_material)
    assert stored.subject == _SUB
    assert _EMAIL.encode() not in result.secret_material
    assert token.encode() not in result.secret_material
    verify_failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_id_token_verify_failed"
    ]
    assert verify_failed == []
    success = [
        event for event in log_events if event.get("event") == "gmail_oauth_code_exchanged"
    ]
    assert len(success) == 1
    _assert_logs_omit_secrets(log_events, token)


def test_verify_oauth2_token_uses_client_id_audience_and_cert_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    cert_urls: list[str] = []
    private_pem = _private_key_pem()
    token = _sign_id_token(private_pem)
    _install_cert_request(
        monkeypatch,
        _public_pem_from_private(private_pem),
        calls=cert_urls,
    )
    import google.oauth2.id_token as google_id_token

    original_verify = google_id_token.verify_oauth2_token

    def wrapped(id_token: str, request: object, audience: object = None, **kwargs: object):
        captured["audience"] = audience
        captured["clock_skew"] = kwargs.get("clock_skew_in_seconds", "unset")
        return original_verify(id_token, request, audience, **kwargs)

    monkeypatch.setattr(google_id_token, "verify_oauth2_token", wrapped)
    result = _client(id_token=token).exchange_authorization_code(
        code=_CODE,
        code_verifier=_VERIFIER,
    )
    assert result.external_account_id == _SUB
    assert captured["audience"] == _CLIENT_ID
    assert captured["clock_skew"] == "unset"
    assert cert_urls
    assert all("oauth2/v1/certs" in url for url in cert_urls)


def test_wrong_audience_fails_and_logs_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
    log_events: list[dict],
) -> None:
    private_pem = _private_key_pem()
    token = _sign_id_token(private_pem, audience="other-client-id.apps.googleusercontent.com")
    _install_cert_request(monkeypatch, _public_pem_from_private(private_pem))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        _client(id_token=token).exchange_authorization_code(
            code=_CODE,
            code_verifier=_VERIFIER,
        )
    event = _verify_failure_event(log_events)
    assert event["verify_error_class"] == InvalidValue.__name__
    assert event["subject_present"] is False
    assert "issuer_present" not in event
    assert "audience_present" not in event
    _assert_logs_omit_secrets(log_events, token, "other-client-id.apps.googleusercontent.com")


def test_wrong_issuer_fails_and_logs_google_auth_error(
    monkeypatch: pytest.MonkeyPatch,
    log_events: list[dict],
) -> None:
    private_pem = _private_key_pem()
    token = _sign_id_token(private_pem, issuer="https://evil.example.invalid")
    _install_cert_request(monkeypatch, _public_pem_from_private(private_pem))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        _client(id_token=token).exchange_authorization_code(
            code=_CODE,
            code_verifier=_VERIFIER,
        )
    event = _verify_failure_event(log_events)
    assert event["verify_error_class"] == GoogleAuthError.__name__
    assert event["subject_present"] is False
    assert "issuer_present" not in event
    _assert_logs_omit_secrets(log_events, token, "https://evil.example.invalid")


def test_invalid_signature_fails_and_logs_malformed_error(
    monkeypatch: pytest.MonkeyPatch,
    log_events: list[dict],
) -> None:
    signer_pem = _private_key_pem()
    other_pem = _private_key_pem()
    token = _sign_id_token(signer_pem)
    _install_cert_request(monkeypatch, _public_pem_from_private(other_pem))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        _client(id_token=token).exchange_authorization_code(
            code=_CODE,
            code_verifier=_VERIFIER,
        )
    event = _verify_failure_event(log_events)
    assert event["verify_error_class"] == MalformedError.__name__
    assert event["subject_present"] is False
    _assert_logs_omit_secrets(log_events, token)


def test_expired_token_fails_and_logs_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
    log_events: list[dict],
) -> None:
    private_pem = _private_key_pem()
    token = _sign_id_token(
        private_pem,
        now=int(time.time()) - 7200,
        lifetime_seconds=60,
    )
    _install_cert_request(monkeypatch, _public_pem_from_private(private_pem))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        _client(id_token=token).exchange_authorization_code(
            code=_CODE,
            code_verifier=_VERIFIER,
        )
    event = _verify_failure_event(log_events)
    assert event["verify_error_class"] == InvalidValue.__name__
    assert event["subject_present"] is False
    _assert_logs_omit_secrets(log_events, token)


def test_verified_token_missing_sub_logs_presence_flags(
    monkeypatch: pytest.MonkeyPatch,
    log_events: list[dict],
) -> None:
    private_pem = _private_key_pem()
    token = _sign_id_token(private_pem, subject=None, extra_claims={"email": _EMAIL})
    _install_cert_request(monkeypatch, _public_pem_from_private(private_pem))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        _client(id_token=token).exchange_authorization_code(
            code=_CODE,
            code_verifier=_VERIFIER,
        )
    event = _verify_failure_event(log_events)
    assert event["verify_error_class"] == "MailboxOAuthAuthorizationFailedError"
    assert event["subject_present"] is False
    assert event["issuer_present"] is True
    assert event["audience_present"] is True
    _assert_logs_omit_secrets(log_events, token)


def test_transport_failure_during_cert_fetch_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    log_events: list[dict],
) -> None:
    from google.auth.exceptions import TransportError

    private_pem = _private_key_pem()
    token = _sign_id_token(private_pem)

    class _FailingRequest:
        def __call__(self, url: str, method: str = "GET", **_kwargs: object) -> SimpleNamespace:
            raise TransportError("certs unavailable")

    monkeypatch.setattr("google.auth.transport.requests.Request", _FailingRequest)
    with pytest.raises(ServiceUnavailableError):
        _client(id_token=token).exchange_authorization_code(
            code=_CODE,
            code_verifier=_VERIFIER,
        )
    verify_failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_id_token_verify_failed"
    ]
    assert verify_failed == []
    _assert_logs_omit_secrets(log_events, token, "certs unavailable")
