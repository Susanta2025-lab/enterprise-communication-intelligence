"""Unit tests for Microsoft Graph request headers and token resolution."""

import httpx

from app.domain.interfaces import ConnectorMessageQuery
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GRAPH_TOKEN,
    GraphHttpStub,
    graph_resource,
)


class _CountingToken:
    def __init__(self, token: str) -> None:
        self.token = token
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.token


def test_list_sends_authorization_and_accept_without_prefer(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=1))

    list_request = stub.requests[0]
    assert list_request.headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"
    assert list_request.headers.get("accept") == "application/json"
    assert list_request.headers.get("prefer") is None


def test_fetch_sends_prefer_text_body(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.fetch_message("msg-1")

    assert stub.requests[0].headers.get("prefer") == 'outlook.body-content-type="text"'
    assert stub.requests[0].headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"
    assert stub.requests[0].headers.get("accept") == "application/json"


def test_token_provider_is_called_once_per_http_request(graph_stub: GraphHttpStub) -> None:
    stub = graph_stub
    stub.messages = {
        "msg-a": graph_resource("msg-a"),
        "msg-b": graph_resource("msg-b"),
        "msg-c": graph_resource("msg-c"),
    }
    stub.list_ids = ["msg-a", "msg-b", "msg-c"]
    token = _CountingToken(GRAPH_TOKEN)
    client = httpx.Client(transport=httpx.MockTransport(stub))
    connector = MicrosoftGraphCommunicationConnector(
        http_client=client,
        access_token_provider=token,
    )

    try:
        connector.list_messages(ConnectorMessageQuery(limit=10))
    finally:
        client.close()

    assert len(stub.requests) == 4
    assert token.calls == 4


def test_token_is_not_cached_across_requests(graph_stub: GraphHttpStub) -> None:
    stub = graph_stub
    stub.messages["msg-1"] = graph_resource("msg-1")
    tokens = iter(["unit-test-graph-token-one", "unit-test-graph-token-two"])

    def provide() -> str:
        return next(tokens)

    client = httpx.Client(transport=httpx.MockTransport(stub))
    connector = MicrosoftGraphCommunicationConnector(
        http_client=client,
        access_token_provider=provide,
    )
    try:
        connector.fetch_message("msg-1")
        connector.fetch_message("msg-1")
    finally:
        client.close()

    assert stub.requests[0].headers.get("authorization") == "Bearer unit-test-graph-token-one"
    assert stub.requests[1].headers.get("authorization") == "Bearer unit-test-graph-token-two"
