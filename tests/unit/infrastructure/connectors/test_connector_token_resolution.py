"""Access-token resolution semantics for read connectors."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ConnectorAuthenticationError,
    ConnectorUnavailableError,
)
from app.infrastructure.connectors.gmail import GmailCommunicationConnector
from app.infrastructure.connectors.microsoft_graph import (
    MicrosoftGraphCommunicationConnector,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from tests.unit.infrastructure.connectors.gmail.conftest import GmailHttpStub, gmail_resource
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GraphHttpStub,
    graph_resource,
)
from tests.unit.infrastructure.credentials.conftest import (
    CountingStore,
    FakeRefreshAdapter,
    build_resolver,
    seed_credential,
)

_LOCATOR = "oauth-readtoken0000001"


def _gmail_connector(
    token_provider: Callable[[], str],
    stub: GmailHttpStub,
) -> tuple[GmailCommunicationConnector, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(stub))
    connector = GmailCommunicationConnector(
        http_client=client,
        access_token_provider=token_provider,
    )
    return connector, client


def _graph_connector(
    token_provider: Callable[[], str],
    stub: GraphHttpStub,
) -> tuple[MicrosoftGraphCommunicationConnector, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(stub))
    connector = MicrosoftGraphCommunicationConnector(
        http_client=client,
        access_token_provider=token_provider,
    )
    return connector, client


@pytest.mark.parametrize("provider", ["gmail", "microsoft_graph"])
def test_permanent_refresh_failure_is_reauth_and_skips_mailbox_http(
    provider: str,
) -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR, provider=provider)
    adapter = FakeRefreshAdapter()
    adapter.error = CommunicationCredentialReauthorizationRequiredError()
    resolver = build_resolver(store, {provider: adapter})
    token_provider = resolver.resolve(credential_ref=_LOCATOR, provider=provider)
    if provider == "gmail":
        stub: GmailHttpStub | GraphHttpStub = GmailHttpStub()
        connector, client = _gmail_connector(token_provider, stub)
    else:
        stub = GraphHttpStub()
        connector, client = _graph_connector(token_provider, stub)
    try:
        with pytest.raises(CommunicationCredentialReauthorizationRequiredError):
            connector.fetch_message("msg-1")
    finally:
        client.close()

    assert stub.requests == []
    assert adapter.calls
    found = store.inner.get(_LOCATOR) if hasattr(store, "inner") else store.get(_LOCATOR)
    assert found is not None


@pytest.mark.parametrize("provider", ["gmail", "microsoft_graph"])
def test_transient_store_failure_is_unavailable_not_reauth(provider: str) -> None:
    class _FailingStore(CountingStore):
        def get(self, credential_ref: str):
            self.gets += 1
            raise CommunicationCredentialUnavailableError()

    store = _FailingStore(InMemoryCommunicationCredentialStore())
    adapter = FakeRefreshAdapter()
    resolver = build_resolver(store, {provider: adapter})
    token_provider = resolver.resolve(credential_ref=_LOCATOR, provider=provider)
    if provider == "gmail":
        stub: GmailHttpStub | GraphHttpStub = GmailHttpStub()
        connector, client = _gmail_connector(token_provider, stub)
    else:
        stub = GraphHttpStub()
        connector, client = _graph_connector(token_provider, stub)
    try:
        with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
            connector.fetch_message("msg-1")
    finally:
        client.close()

    assert not isinstance(
        exc_info.value,
        CommunicationCredentialReauthorizationRequiredError,
    )
    assert stub.requests == []
    assert adapter.calls == []


@pytest.mark.parametrize("provider", ["gmail", "microsoft_graph"])
def test_transient_refresh_failure_is_unavailable_not_reauth(provider: str) -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR, provider=provider)
    adapter = FakeRefreshAdapter()
    adapter.error = CommunicationCredentialUnavailableError()
    resolver = build_resolver(store, {provider: adapter})
    token_provider = resolver.resolve(credential_ref=_LOCATOR, provider=provider)
    if provider == "gmail":
        stub: GmailHttpStub | GraphHttpStub = GmailHttpStub()
        connector, client = _gmail_connector(token_provider, stub)
    else:
        stub = GraphHttpStub()
        connector, client = _graph_connector(token_provider, stub)
    try:
        with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
            connector.fetch_message("msg-1")
    finally:
        client.close()

    assert not isinstance(
        exc_info.value,
        CommunicationCredentialReauthorizationRequiredError,
    )
    assert stub.requests == []
    assert adapter.calls


@pytest.mark.parametrize("provider", ["gmail", "microsoft_graph"])
def test_successful_refresh_supplies_token_to_mailbox_http(provider: str) -> None:
    store = CountingStore()
    seed_credential(store, locator=_LOCATOR, provider=provider)
    adapter = FakeRefreshAdapter(token="refreshed-access-token")
    resolver = build_resolver(store, {provider: adapter})
    token_provider = resolver.resolve(credential_ref=_LOCATOR, provider=provider)
    if provider == "gmail":
        stub = GmailHttpStub()
        stub.messages["msg-1"] = gmail_resource("msg-1")
        connector, client = _gmail_connector(token_provider, stub)
    else:
        stub = GraphHttpStub()
        stub.messages["msg-1"] = graph_resource("msg-1")
        connector, client = _graph_connector(token_provider, stub)
    try:
        message = connector.fetch_message("msg-1")
    finally:
        client.close()

    assert message.message_id == "msg-1"
    assert stub.requests
    assert stub.requests[0].headers.get("authorization") == "Bearer refreshed-access-token"
    assert adapter.calls


def test_mailbox_http_401_is_connector_auth_not_reauth() -> None:
    stub = GmailHttpStub()
    stub.fetch_status["msg-1"] = 401
    connector, client = _gmail_connector(lambda: "valid-token", stub)
    try:
        with pytest.raises(ConnectorAuthenticationError) as exc_info:
            connector.fetch_message("msg-1")
    finally:
        client.close()

    assert not isinstance(
        exc_info.value,
        CommunicationCredentialReauthorizationRequiredError,
    )
    assert len(stub.requests) == 1


def test_unknown_token_callable_failure_is_unavailable_not_auth() -> None:
    stub = GmailHttpStub()

    def boom() -> str:
        raise RuntimeError("key vault exploded")

    connector, client = _gmail_connector(boom, stub)
    try:
        with pytest.raises(ConnectorUnavailableError) as exc_info:
            connector.fetch_message("msg-1")
    finally:
        client.close()

    assert not isinstance(exc_info.value, ConnectorAuthenticationError)
    assert not isinstance(
        exc_info.value,
        CommunicationCredentialReauthorizationRequiredError,
    )
    assert stub.requests == []
    assert "key vault" not in exc_info.value.message.lower()
