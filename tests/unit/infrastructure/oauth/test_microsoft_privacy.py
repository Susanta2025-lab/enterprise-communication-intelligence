"""Secret-marker privacy tests for Microsoft OAuth objects."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.exceptions import MailboxOAuthAuthorizationFailedError
from app.domain.enums import CommunicationCapability
from app.domain.interfaces.mailbox_oauth_client import MailboxOAuthAuthorizationResult
from app.infrastructure.oauth.microsoft import (
    GRAPH_MAIL_READ_SCOPE,
    MSA_TENANT_ID,
    MicrosoftMailboxOAuthClient,
    MicrosoftRefreshableCredentialAdapter,
    deserialize_microsoft_mailbox_secret,
    serialize_microsoft_mailbox_secret,
)

_CLIENT_SECRET = "PRIV_MS_CLIENT_SECRET_SENTINEL_AAA"
_CODE = "PRIV_MS_AUTH_CODE_SENTINEL_BBB"
_VERIFIER = "PRIV_MS_PKCE_VERIFIER_SENTINEL_CCC_xxxxxxxx"
_STATE = "PRIV_MS_OAUTH_STATE_SENTINEL_DDD"
_REFRESH = "PRIV_MS_REFRESH_TOKEN_SENTINEL_EEE"
_ACCESS = "PRIV_MS_ACCESS_TOKEN_SENTINEL_FFF"
_ID_TOKEN = "PRIV_MS_ID_TOKEN_SENTINEL_GGG"
_OID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
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


def test_microsoft_oauth_objects_omit_secrets_from_repr() -> None:
    material = serialize_microsoft_mailbox_secret(
        refresh_token=_REFRESH,
        scopes=(GRAPH_MAIL_READ_SCOPE,),
        tenant_id=MSA_TENANT_ID,
        object_id=_OID,
    )
    stored = deserialize_microsoft_mailbox_secret(material)
    result = MailboxOAuthAuthorizationResult(
        external_account_id=f"{MSA_TENANT_ID}:{_OID}",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
        secret_material=material,
    )
    client = MicrosoftMailboxOAuthClient(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        redirect_uri="https://eci.example.invalid/callback",
        tenant="consumers",
    )
    adapter = MicrosoftRefreshableCredentialAdapter(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        tenant="consumers",
    )
    blob = f"{client!r}{adapter!r}{result!r}{stored!r}"
    _assert_opaque(blob)
    assert "MicrosoftMailboxOAuthClient()" in repr(client)
    assert "MicrosoftRefreshableCredentialAdapter()" in repr(adapter)


def test_exchange_failures_omit_secrets(
    log_events: list[dict],
) -> None:
    def fetch(code: str, verifier: str) -> dict:
        raise RuntimeError(f"provider {_CODE} {_VERIFIER} {_CLIENT_SECRET}")

    client = MicrosoftMailboxOAuthClient(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        redirect_uri="https://eci.example.invalid/callback",
        tenant="consumers",
        token_fetcher=fetch,
        id_token_verifier=lambda _token: {},
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError) as exc_info:
        client.exchange_authorization_code(code=_CODE, code_verifier=_VERIFIER)
    blob = f"{exc_info.value}{exc_info.value!r}{exc_info.value.message}{log_events!r}"
    _assert_opaque(blob)


def test_refresh_failures_omit_secrets(log_events: list[dict]) -> None:
    def transport(_form: dict[str, str]) -> dict:
        raise RuntimeError(f"invalid_grant {_REFRESH} {_ACCESS} {_CLIENT_SECRET}")

    adapter = MicrosoftRefreshableCredentialAdapter(
        client_id="client-id",
        client_secret=_CLIENT_SECRET,
        tenant="consumers",
        refresh_transport=transport,
        clock=lambda: datetime.now(UTC),
    )
    material = serialize_microsoft_mailbox_secret(
        refresh_token=_REFRESH,
        scopes=(GRAPH_MAIL_READ_SCOPE,),
        tenant_id=MSA_TENANT_ID,
        object_id=_OID,
    )
    with pytest.raises(Exception) as exc_info:
        adapter.acquire_access_token(provider="microsoft_graph", secret_material=material)
    blob = f"{exc_info.value}{exc_info.value!r}{log_events!r}"
    _assert_opaque(blob)
    assert "error_description" not in blob
