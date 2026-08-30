"""Microsoft authorization-code exchange and ID-token identity tests."""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import MailboxOAuthAuthorizationFailedError, ServiceUnavailableError
from app.domain.enums import CommunicationCapability
from app.infrastructure.oauth.microsoft import (
    GRAPH_MAIL_READ_SCOPE,
    GRAPH_MAIL_SEND_SCOPE,
    MSA_TENANT_ID,
    MicrosoftMailboxOAuthClient,
    deserialize_microsoft_mailbox_secret,
)

_CLIENT_ID = "11111111-1111-1111-1111-111111111111"
_CLIENT_SECRET = "test-microsoft-client-secret-sentinel"
_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/microsoft_graph"
_TENANT = "consumers"
_CODE = "AUTH_CODE_SENTINEL_MS_111"
_VERIFIER = "pkce-verifier-sentinel-ms-222-xxxxxxxxxxxxxxxxxxxx"
_REFRESH = "REFRESH_TOKEN_SENTINEL_MS_333"
_ID_TOKEN = "ID_TOKEN_SENTINEL_MS_444"
_ACCESS = "ACCESS_TOKEN_SENTINEL_MS_555"
_OID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_EXTERNAL = f"{MSA_TENANT_ID}:{_OID}"


def _claims(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "oid": _OID,
        "tid": MSA_TENANT_ID,
        "sub": "pairwise-sub-must-not-be-used",
        "iss": f"https://login.microsoftonline.com/{MSA_TENANT_ID}/v2.0",
        "aud": _CLIENT_ID,
        "preferred_username": "mailbox@outlook.com",
        "email": "mailbox@outlook.com",
        "upn": "mailbox@outlook.com",
    }
    payload.update(overrides)
    return payload


def _client(
    *,
    tenant: str = _TENANT,
    token_response: dict | None = None,
    token_error: Exception | None = None,
    claims: dict | None = None,
    verify_error: Exception | None = None,
    captured: dict | None = None,
) -> MicrosoftMailboxOAuthClient:
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
        return claims if claims is not None else _claims()

    return MicrosoftMailboxOAuthClient(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        redirect_uri=_REDIRECT,
        tenant=tenant,
        token_fetcher=fetch,
        id_token_verifier=verify,
    )


def _success_response(**overrides: object) -> dict:
    payload: dict[str, object] = {
        "refresh_token": _REFRESH,
        "id_token": _ID_TOKEN,
        "access_token": _ACCESS,
        "scope": f"openid profile offline_access {GRAPH_MAIL_READ_SCOPE} {GRAPH_MAIL_SEND_SCOPE}",
        "expires_in": 3600,
    }
    payload.update(overrides)
    return payload


def test_exchange_uses_consumed_verifier_and_tid_oid() -> None:
    captured: dict[str, str] = {}
    client = _client(token_response=_success_response(), captured=captured)
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert captured["code"] == _CODE
    assert captured["verifier"] == _VERIFIER
    assert captured["id_token"] == _ID_TOKEN
    assert result.external_account_id == _EXTERNAL
    assert result.granted_capabilities == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )
    stored = deserialize_microsoft_mailbox_secret(result.secret_material)
    assert stored.refresh_token == _REFRESH
    assert stored.tenant_id == MSA_TENANT_ID
    assert stored.object_id == _OID
    assert stored.external_account_id == _EXTERNAL
    assert GRAPH_MAIL_READ_SCOPE in stored.scopes
    assert GRAPH_MAIL_SEND_SCOPE in stored.scopes
    assert _ACCESS.encode() not in result.secret_material
    assert _ID_TOKEN.encode() not in result.secret_material
    assert _CODE.encode() not in result.secret_material
    assert _CLIENT_SECRET.encode() not in result.secret_material
    assert b"mailbox@outlook.com" not in result.secret_material
    assert b"pairwise-sub" not in result.secret_material
    assert result.display_identity == "mailbox@outlook.com"
    assert result.external_account_id != result.display_identity


def test_email_and_sub_are_not_used_as_identity() -> None:
    client = _client(token_response=_success_response())
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.external_account_id == _EXTERNAL
    assert result.external_account_id != "mailbox@outlook.com"
    assert result.external_account_id != "pairwise-sub-must-not-be-used"
    assert result.display_identity == "mailbox@outlook.com"


def test_preferred_username_missing_keeps_display_identity_null() -> None:
    client = _client(
        token_response=_success_response(),
        claims=_claims(
            preferred_username="  ",
            email="mailbox@outlook.com",
            upn="mailbox@outlook.com",
        ),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.external_account_id == _EXTERNAL
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


def test_consumers_tenant_rejects_work_account_tid() -> None:
    work_tid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    client = _client(
        token_response=_success_response(),
        claims=_claims(
            tid=work_tid,
            iss=f"https://login.microsoftonline.com/{work_tid}/v2.0",
        ),
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_organizations_tenant_rejects_msa_tid() -> None:
    client = _client(
        tenant="organizations",
        token_response=_success_response(),
        claims=_claims(),
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_specific_tenant_requires_matching_tid() -> None:
    tenant = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    oid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    client = _client(
        tenant=tenant,
        token_response=_success_response(),
        claims=_claims(
            tid=tenant,
            oid=oid,
            iss=f"https://login.microsoftonline.com/{tenant}/v2.0",
            sub="other-sub",
            preferred_username="user@contoso.com",
            email="user@contoso.com",
            upn="user@contoso.com",
        ),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.external_account_id == f"{tenant}:{oid}"


def test_missing_refresh_token_is_rejected() -> None:
    client = _client(token_response=_success_response(refresh_token=""))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_missing_id_token_is_rejected() -> None:
    client = _client(token_response=_success_response(id_token=None))
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_short_graph_scope_names_map_capabilities() -> None:
    client = _client(
        token_response=_success_response(scope="openid Mail.Read Mail.Send offline_access"),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.granted_capabilities == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )


def test_scope_mapping_is_case_insensitive() -> None:
    client = _client(
        token_response=_success_response(scope="openid MAIL.READ mail.send"),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.granted_capabilities == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )


def test_partial_grant_maps_read_only_capabilities() -> None:
    client = _client(
        token_response=_success_response(scope=f"openid {GRAPH_MAIL_READ_SCOPE}"),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.granted_capabilities == (CommunicationCapability.MAIL_READ,)
    assert CommunicationCapability.MAIL_SEND not in result.granted_capabilities


def test_send_without_read_does_not_invent_read_capability() -> None:
    client = _client(
        token_response=_success_response(scope=f"openid {GRAPH_MAIL_SEND_SCOPE}"),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.granted_capabilities == (CommunicationCapability.MAIL_SEND,)


def test_unrelated_graph_scopes_do_not_grant_mail_capabilities() -> None:
    client = _client(
        token_response=_success_response(scope="openid profile User.Read Mail.ReadWrite"),
    )
    result = client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    assert result.granted_capabilities == ()


def test_transport_failure_during_exchange_is_unavailable() -> None:
    client = _client(
        token_response=_success_response(),
        token_error=TimeoutError("network down"),
    )
    with pytest.raises(ServiceUnavailableError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


class _StatusClient:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self._status = status
        self._payload = payload

    def __enter__(self) -> _StatusClient:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def post(self, url: str, data: dict[str, str]) -> httpx.Response:
        return httpx.Response(self._status, json=self._payload)


def test_token_endpoint_failure_does_not_complete_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StatusClient(500, {"error": "server_error", "error_description": _REFRESH})
    monkeypatch.setattr(
        "app.infrastructure.oauth.microsoft.httpx.Client",
        lambda **_kwargs: stub,
    )
    client = MicrosoftMailboxOAuthClient(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        redirect_uri=_REDIRECT,
        tenant=_TENANT,
    )
    with pytest.raises(ServiceUnavailableError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)


def test_invalid_grant_on_code_exchange_is_authorization_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StatusClient(400, {"error": "invalid_grant", "error_description": _CODE})
    monkeypatch.setattr(
        "app.infrastructure.oauth.microsoft.httpx.Client",
        lambda **_kwargs: stub,
    )
    client = MicrosoftMailboxOAuthClient(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        redirect_uri=_REDIRECT,
        tenant=_TENANT,
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
