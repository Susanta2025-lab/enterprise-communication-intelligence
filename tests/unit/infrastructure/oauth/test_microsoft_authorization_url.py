"""Microsoft authorization URL uses Phase 13A state and PKCE exactly."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from app.core.oauth_state import generate_oauth_state
from app.core.pkce import PkceS256
from app.infrastructure.oauth.microsoft import (
    GRAPH_MAIL_READ_SCOPE,
    GRAPH_MAIL_SEND_SCOPE,
    MICROSOFT_AUTHORIZE_PATH,
    MICROSOFT_LOGIN_HOST,
    OFFLINE_ACCESS_SCOPE,
    OPENID_SCOPE,
    PROFILE_SCOPE,
    MicrosoftMailboxOAuthClient,
)

_CLIENT_ID = "11111111-1111-1111-1111-111111111111"
_CLIENT_SECRET = "test-microsoft-client-secret-sentinel"
_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/microsoft_graph"
_TENANT = "consumers"


def _client(*, tenant: str = _TENANT) -> MicrosoftMailboxOAuthClient:
    return MicrosoftMailboxOAuthClient(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        redirect_uri=_REDIRECT,
        tenant=tenant,
    )


def test_authorization_url_uses_exact_state_pkce_and_redirect() -> None:
    """Microsoft URL construction must not replace Phase 13A state or S256 challenge."""
    state = generate_oauth_state()
    verifier = PkceS256.generate_code_verifier()
    challenge = PkceS256.code_challenge(verifier)
    url = _client().build_authorization_url(
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.hostname == MICROSOFT_LOGIN_HOST
    assert parsed.path == f"/{_TENANT}{MICROSOFT_AUTHORIZE_PATH}"
    params = parse_qs(parsed.query)
    assert params["state"] == [state]
    assert params["code_challenge"] == [challenge]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == [_REDIRECT]
    assert params["client_id"] == [_CLIENT_ID]
    assert params["response_type"] == ["code"]
    assert params["prompt"] == ["consent"]
    assert params["response_mode"] == ["query"]
    scopes = unquote(params["scope"][0]).split()
    assert scopes == [
        OPENID_SCOPE,
        PROFILE_SCOPE,
        OFFLINE_ACCESS_SCOPE,
        GRAPH_MAIL_READ_SCOPE,
        GRAPH_MAIL_SEND_SCOPE,
    ]
    assert "User.Read" not in scopes
    assert "Mail.ReadWrite" not in scopes
    assert "email" not in scopes
    assert verifier not in url
    assert _CLIENT_SECRET not in url
    assert "client_secret" not in parsed.query


def test_authorization_url_embeds_configured_tenant() -> None:
    tenant = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    url = _client(tenant=tenant).build_authorization_url(
        state="state-value",
        code_challenge="challenge-value",
        code_challenge_method="S256",
    )
    assert urlparse(url).path == f"/{tenant}{MICROSOFT_AUTHORIZE_PATH}"


def test_authorization_url_does_not_expose_client_secret_in_repr() -> None:
    client = _client()
    assert _CLIENT_SECRET not in repr(client)
    assert "MicrosoftMailboxOAuthClient()" == repr(client)
