"""Google authorization URL uses Phase 13A state and PKCE exactly."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.core.oauth_state import generate_oauth_state
from app.core.pkce import PkceS256
from app.infrastructure.oauth.google import (
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
    OPENID_SCOPE,
    GoogleMailboxOAuthClient,
)

_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_CLIENT_SECRET = "test-client-secret-sentinel"
_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/gmail"


def _client() -> GoogleMailboxOAuthClient:
    return GoogleMailboxOAuthClient(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        redirect_uri=_REDIRECT,
    )


def test_authorization_url_uses_exact_state_pkce_and_redirect() -> None:
    """google-auth-oauthlib must not replace Phase 13A state or S256 challenge."""
    state = generate_oauth_state()
    verifier = PkceS256.generate_code_verifier()
    challenge = PkceS256.code_challenge(verifier)
    url = _client().build_authorization_url(
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    params = parse_qs(urlparse(url).query)
    assert params["state"] == [state]
    assert params["code_challenge"] == [challenge]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == [_REDIRECT]
    assert params["client_id"] == [_CLIENT_ID]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["include_granted_scopes"] == ["true"]
    assert params["response_type"] == ["code"]
    scopes = params["scope"][0].split()
    assert scopes == [OPENID_SCOPE, GMAIL_READONLY_SCOPE, GMAIL_SEND_SCOPE]
    assert "profile" not in scopes
    assert "email" not in scopes
    assert "https://mail.google.com/" not in scopes
    assert "https://www.googleapis.com/auth/gmail.modify" not in scopes
    assert "https://www.googleapis.com/auth/gmail.compose" not in scopes
    assert verifier not in url
    assert _CLIENT_SECRET not in url


def test_account_selection_url_keeps_offline_access_and_consent() -> None:
    state = generate_oauth_state()
    verifier = PkceS256.generate_code_verifier()
    challenge = PkceS256.code_challenge(verifier)
    url = _client().build_authorization_url(
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
        account_selection=True,
    )
    params = parse_qs(urlparse(url).query)
    assert params["prompt"] == ["select_account consent"]
    assert params["access_type"] == ["offline"]
    assert params["include_granted_scopes"] == ["true"]
    scopes = params["scope"][0].split()
    assert scopes == [OPENID_SCOPE, GMAIL_READONLY_SCOPE, GMAIL_SEND_SCOPE]
    assert "email" not in scopes
    reconnect = _client().build_authorization_url(
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
        account_selection=False,
    )
    assert parse_qs(urlparse(reconnect).query)["prompt"] == ["consent"]
    assert "select_account" not in parse_qs(urlparse(reconnect).query)["prompt"][0]


def test_authorization_url_does_not_expose_client_secret_in_repr() -> None:
    client = _client()
    assert _CLIENT_SECRET not in repr(client)
    assert "GoogleMailboxOAuthClient()" == repr(client)
