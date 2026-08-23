"""Microsoft refresh adapter success and failure taxonomy."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.infrastructure.credentials.locators import create_communication_credential
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.oauth import OAuthCommunicationCredentialResolver
from app.infrastructure.oauth.microsoft import (
    GRAPH_MAIL_READ_SCOPE,
    MSA_TENANT_ID,
    MicrosoftRefreshableCredentialAdapter,
    deserialize_microsoft_mailbox_secret,
    serialize_microsoft_mailbox_secret,
)

_CLIENT_ID = "11111111-1111-1111-1111-111111111111"
_CLIENT_SECRET = "test-microsoft-client-secret-sentinel"
_TENANT = "consumers"
_REFRESH = "REFRESH_TOKEN_SENTINEL_MS_REFRESH_001"
_ACCESS = "ACCESS_TOKEN_SENTINEL_MS_REFRESH_002"
_OID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _material(*, refresh: str = _REFRESH) -> bytes:
    return serialize_microsoft_mailbox_secret(
        refresh_token=refresh,
        scopes=(GRAPH_MAIL_READ_SCOPE,),
        tenant_id=MSA_TENANT_ID,
        object_id=_OID,
    )


def _adapter(transport):
    return MicrosoftRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        tenant=_TENANT,
        refresh_transport=transport,
        clock=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )


def test_refresh_success_returns_access_token_without_persisting_it() -> None:
    captured: dict[str, object] = {}

    def transport(form: dict[str, str]) -> dict[str, object]:
        captured["form"] = dict(form)
        return {
            "access_token": _ACCESS,
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    adapter = _adapter(transport)
    result = adapter.acquire_access_token(
        provider="microsoft_graph",
        secret_material=_material(),
    )
    assert result.access_token == _ACCESS
    assert result.expires_at == datetime(2026, 8, 23, 13, 0, tzinfo=UTC)
    assert result.replacement_secret_material is None
    form = captured["form"]
    assert isinstance(form, dict)
    assert form["grant_type"] == "refresh_token"
    assert form["refresh_token"] == _REFRESH
    assert form["client_id"] == _CLIENT_ID
    assert "scope" not in form
    blob = f"{result!r}{adapter!r}"
    assert _ACCESS not in blob
    assert _REFRESH not in blob
    assert _CLIENT_SECRET not in blob


def test_rotated_refresh_token_returns_replacement_material() -> None:
    rotated = "ROTATED_REFRESH_TOKEN_SENTINEL_MS_003"

    def transport(_form: dict[str, str]) -> dict[str, object]:
        return {
            "access_token": _ACCESS,
            "expires_in": 3600,
            "refresh_token": rotated,
        }

    result = _adapter(transport).acquire_access_token(
        provider="microsoft_graph",
        secret_material=_material(),
    )
    assert result.replacement_secret_material is not None
    stored = deserialize_microsoft_mailbox_secret(result.replacement_secret_material)
    assert stored.refresh_token == rotated
    assert stored.tenant_id == MSA_TENANT_ID
    assert stored.object_id == _OID
    assert _ACCESS.encode() not in result.replacement_secret_material


def test_temporary_refresh_failure_is_unavailable() -> None:
    def transport(_form: dict[str, str]) -> dict[str, object]:
        raise TimeoutError("temporarily unreachable")

    with pytest.raises(CommunicationCredentialUnavailableError):
        _adapter(transport).acquire_access_token(
            provider="microsoft_graph",
            secret_material=_material(),
        )


def test_confirmed_invalid_grant_requires_reauthorization() -> None:
    def transport(_form: dict[str, str]) -> dict[str, object]:
        raise CommunicationCredentialReauthorizationRequiredError()

    with pytest.raises(CommunicationCredentialReauthorizationRequiredError):
        _adapter(transport).acquire_access_token(
            provider="microsoft_graph",
            secret_material=_material(),
        )


def test_ambiguous_refresh_error_is_not_permanent() -> None:
    def transport(_form: dict[str, str]) -> dict[str, object]:
        raise RuntimeError("something went wrong")

    with pytest.raises(CommunicationCredentialUnavailableError):
        _adapter(transport).acquire_access_token(
            provider="microsoft_graph",
            secret_material=_material(),
        )


def test_expires_in_string_is_accepted() -> None:
    def transport(_form: dict[str, str]) -> dict[str, object]:
        return {"access_token": _ACCESS, "expires_in": "1800"}

    result = _adapter(transport).acquire_access_token(
        provider="microsoft_graph",
        secret_material=_material(),
    )
    assert result.expires_at == datetime(2026, 8, 23, 12, 30, tzinfo=UTC)


def test_missing_expires_in_is_unavailable() -> None:
    def transport(_form: dict[str, str]) -> dict[str, object]:
        return {"access_token": _ACCESS}

    with pytest.raises(CommunicationCredentialUnavailableError):
        _adapter(transport).acquire_access_token(
            provider="microsoft_graph",
            secret_material=_material(),
        )


def test_unsupported_provider_is_rejected() -> None:
    def transport(_form: dict[str, str]) -> dict[str, object]:
        return {"access_token": _ACCESS, "expires_in": 3600}

    with pytest.raises(UnsupportedCommunicationCredentialProviderError):
        _adapter(transport).acquire_access_token(
            provider="gmail",
            secret_material=_material(),
        )


class _StatusClient:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self._status = status
        self._payload = payload
        self.requests: list[httpx.Request] = []

    def __enter__(self) -> _StatusClient:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def post(self, url: str, data: dict[str, str]) -> httpx.Response:
        self.requests.append(httpx.Request("POST", url, data=data))
        return httpx.Response(self._status, json=self._payload)


def test_http_invalid_grant_requires_reauthorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StatusClient(400, {"error": "invalid_grant", "error_description": _REFRESH})
    monkeypatch.setattr(
        "app.infrastructure.oauth.microsoft.httpx.Client",
        lambda **_kwargs: stub,
    )
    adapter = MicrosoftRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        tenant=_TENANT,
        clock=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(CommunicationCredentialReauthorizationRequiredError):
        adapter.acquire_access_token(provider="microsoft_graph", secret_material=_material())
    assert stub.requests[0].url.host == "login.microsoftonline.com"


def test_http_temporary_failure_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StatusClient(503, {"error": "temporarily_unavailable"})
    monkeypatch.setattr(
        "app.infrastructure.oauth.microsoft.httpx.Client",
        lambda **_kwargs: stub,
    )
    adapter = MicrosoftRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        tenant=_TENANT,
        clock=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(CommunicationCredentialUnavailableError):
        adapter.acquire_access_token(provider="microsoft_graph", secret_material=_material())


def test_shared_resolver_caches_until_refresh_skew() -> None:
    store = InMemoryCommunicationCredentialStore()
    record = create_communication_credential(
        store,
        provider="microsoft_graph",
        secret_material=_material(),
    )
    calls: list[dict[str, str]] = []

    def transport(form: dict[str, str]) -> dict[str, object]:
        calls.append(dict(form))
        return {"access_token": f"{_ACCESS}-{len(calls)}", "expires_in": 3600}

    clock_now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

    def clock() -> datetime:
        return clock_now

    adapter = MicrosoftRefreshableCredentialAdapter(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        tenant=_TENANT,
        refresh_transport=transport,
        clock=clock,
    )
    resolver = OAuthCommunicationCredentialResolver(
        store,
        {"microsoft_graph": adapter},
        clock=clock,
    )
    provider = resolver.resolve(
        credential_ref=record.credential_ref,
        provider="microsoft_graph",
    )
    assert provider() == f"{_ACCESS}-1"
    assert provider() == f"{_ACCESS}-1"
    assert len(calls) == 1
    clock_now = datetime(2026, 8, 23, 12, 56, tzinfo=UTC)
    assert provider() == f"{_ACCESS}-2"
    assert len(calls) == 2


def test_secret_material_does_not_contain_access_token() -> None:
    material = _material()
    assert _ACCESS.encode() not in material
    stored = deserialize_microsoft_mailbox_secret(material)
    assert stored.refresh_token == _REFRESH
    blob = repr(stored)
    assert _REFRESH not in blob
