"""Unit tests for Microsoft Graph pagination and nextLink security."""

import httpx
import pytest

from app.core.exceptions import ConnectorInvalidCursorError
from app.domain.interfaces import ConnectorMessageQuery
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GRAPH_API_PREFIX,
    GRAPH_TOKEN,
    GraphHttpStub,
    graph_resource,
)

_SAFE_NEXT_LINK = (
    "https://graph.microsoft.com/v1.0/me/messages"
    "?$select=id&$top=10&$skiptoken=OPAQUE-TOKEN-ZX91"
)


def test_next_link_copied_unchanged_to_next_cursor(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")
    stub.next_link = _SAFE_NEXT_LINK

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert page.next_cursor == _SAFE_NEXT_LINK


def test_blank_next_link_is_terminal_page(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = {"value": []}
    stub.list_json["@odata.nextLink"] = "   "

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert page.items == []
    assert page.next_cursor is None


def test_continuation_uses_entire_next_link(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-2"] = graph_resource("msg-2")
    stub.list_ids = ["msg-2"]

    page = connector.list_messages(ConnectorMessageQuery(limit=99, cursor=_SAFE_NEXT_LINK))

    list_request = stub.requests[0]
    assert list_request.method == "GET"
    assert str(list_request.url) == _SAFE_NEXT_LINK
    assert list_request.url.host == "graph.microsoft.com"
    assert list_request.url.path == GRAPH_API_PREFIX
    assert list_request.url.params.get("$skiptoken") == "OPAQUE-TOKEN-ZX91"
    assert list_request.url.params.get("$top") == "10"
    assert list_request.url.params.get("$select") == "id"
    assert [item.message_id for item in page.items] == ["msg-2"]


def test_continuation_does_not_rewrite_top_or_select(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-2"] = graph_resource("msg-2")
    stub.list_ids = ["msg-2"]

    connector.list_messages(ConnectorMessageQuery(limit=1, cursor=_SAFE_NEXT_LINK))

    params = stub.requests[0].url.params
    assert params.get("$top") == "10"
    assert params.get("$select") == "id"
    assert params.get("$skiptoken") == "OPAQUE-TOKEN-ZX91"


def test_changed_query_limit_does_not_alter_continuation_url(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-2"] = graph_resource("msg-2")
    stub.list_ids = ["msg-2"]

    connector.list_messages(ConnectorMessageQuery(limit=50, cursor=_SAFE_NEXT_LINK))

    assert str(stub.requests[0].url) == _SAFE_NEXT_LINK
    assert stub.requests[0].url.params.get("$top") != "50"


def test_continuation_requests_one_page_then_n_fetches(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages = {
        "msg-a": graph_resource("msg-a"),
        "msg-b": graph_resource("msg-b"),
    }
    stub.list_ids = ["msg-a", "msg-b"]
    stub.next_link = (
        "https://graph.microsoft.com/v1.0/me/messages?$select=id&$top=2&$skiptoken=page-3"
    )

    page = connector.list_messages(ConnectorMessageQuery(limit=10, cursor=_SAFE_NEXT_LINK))

    list_calls = [
        request for request in stub.requests if request.url.path.rstrip("/") == GRAPH_API_PREFIX
    ]
    assert len(list_calls) == 1
    assert str(list_calls[0].url) == _SAFE_NEXT_LINK
    assert len(stub.requests) == 3
    assert page.next_cursor == stub.next_link


def test_continuation_does_not_parse_skip_values(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")
    cursor = (
        "https://graph.microsoft.com/v1.0/me/messages?$select=id&$skip=250&$skiptoken=keep-me"
    )

    connector.list_messages(ConnectorMessageQuery(limit=5, cursor=cursor))

    assert str(stub.requests[0].url) == cursor
    assert stub.requests[0].url.params.get("$skip") == "250"
    assert stub.requests[0].url.params.get("$skiptoken") == "keep-me"


@pytest.mark.parametrize(
    "cursor",
    [
        "http://graph.microsoft.com/v1.0/me/messages",
        "https://evil.example/v1.0/me/messages",
        "https://graph.microsoft.com.evil.test/v1.0/me/messages",
        "https://user@graph.microsoft.com/v1.0/me/messages",
        "https://user:pass@graph.microsoft.com/v1.0/me/messages",
        "https://graph.microsoft.com:444/v1.0/me/messages",
        "https://graph.microsoft.com/v1.0/me/messages#fragment",
        "/v1.0/me/messages",
        "//graph.microsoft.com/v1.0/me/messages",
        "https://graph.microsoft.com/v1.0/users/someone/messages",
        "https://graph.microsoft.com/v1.0/me/drive/root",
        "https://graph.microsoft.com/beta/me/messages",
        "https://graph.microsoft.com/v1.0/me/messages/$delta",
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
        "https://graph.microsoft.com./v1.0/me/messages",
        "https://graph.microsoft.com%2eevil.test/v1.0/me/messages",
        "https://graph.microsoft.com/v1.0/me/messages/../drive",
        "https://graph.microsoft.com/v1.0/me/messages%2F../drive",
        "https://graph.microsoft.com/v1.0/me/messages/anything",
    ],
)
def test_malicious_cursor_is_rejected_before_http(
    graph_connector: tuple,
    cursor: str,
) -> None:
    connector, stub, _client = graph_connector

    with pytest.raises(ConnectorInvalidCursorError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10, cursor=cursor))

    assert stub.requests == []
    assert exc_info.value.message == "Connector cursor is invalid."
    assert exc_info.value.__cause__ is None
    assert GRAPH_TOKEN not in exc_info.value.message
    assert "authorization" not in exc_info.value.message.lower()
    assert cursor not in exc_info.value.message
    assert "evil" not in exc_info.value.message.lower()


class _CountingToken:
    def __init__(self, token: str) -> None:
        self.token = token
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.token


def test_malicious_cursor_does_not_resolve_token(graph_stub: GraphHttpStub) -> None:
    token = _CountingToken(GRAPH_TOKEN)
    client = httpx.Client(transport=httpx.MockTransport(graph_stub))
    connector = MicrosoftGraphCommunicationConnector(
        http_client=client,
        access_token_provider=token,
    )
    try:
        with pytest.raises(ConnectorInvalidCursorError):
            connector.list_messages(
                ConnectorMessageQuery(
                    limit=10,
                    cursor="https://evil.example/v1.0/me/messages",
                )
            )
    finally:
        client.close()

    assert graph_stub.requests == []
    assert token.calls == 0


def test_uppercase_graph_host_continuation_is_accepted(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    cursor = (
        "https://GRAPH.MICROSOFT.COM/v1.0/me/messages?$skiptoken=OPAQUE-TOKEN-ZX91"
    )

    page = connector.list_messages(ConnectorMessageQuery(limit=10, cursor=cursor))

    assert page.items == []
    assert len(stub.requests) == 1
    assert stub.requests[0].url.scheme == "https"
    assert stub.requests[0].url.host == "graph.microsoft.com"
    assert stub.requests[0].url.path == GRAPH_API_PREFIX
    assert stub.requests[0].url.params.get("$skiptoken") == "OPAQUE-TOKEN-ZX91"
    assert stub.requests[0].headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"


def test_explicit_https_port_443_continuation_is_accepted(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    cursor = (
        "https://graph.microsoft.com:443/v1.0/me/messages"
        "?$select=id&$top=5&$skiptoken=port-443"
    )

    connector.list_messages(ConnectorMessageQuery(limit=99, cursor=cursor))

    request = stub.requests[0]
    assert len(stub.requests) == 1
    assert request.url.scheme == "https"
    assert request.url.host == "graph.microsoft.com"
    assert request.url.port in {None, 443}
    assert request.url.path == GRAPH_API_PREFIX
    assert request.url.params.get("$skiptoken") == "port-443"
    assert request.url.params.get("$top") == "5"
    assert request.url.params.get("$select") == "id"
    assert request.headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"


def test_trailing_slash_continuation_is_accepted(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    cursor = "https://graph.microsoft.com/v1.0/me/messages/?$skiptoken=slash"

    connector.list_messages(ConnectorMessageQuery(limit=10, cursor=cursor))

    assert len(stub.requests) == 1
    assert str(stub.requests[0].url) == cursor
    assert stub.requests[0].url.path == f"{GRAPH_API_PREFIX}/"
    assert stub.requests[0].url.params.get("$skiptoken") == "slash"


def test_encoded_continuation_query_is_preserved(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    cursor = (
        "https://graph.microsoft.com/v1.0/me/messages?%24skiptoken=abc%2Fdef%3D"
    )

    connector.list_messages(ConnectorMessageQuery(limit=10, cursor=cursor))

    assert len(stub.requests) == 1
    assert str(stub.requests[0].url) == cursor


def test_skip_top_select_continuation_query_is_preserved(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    cursor = (
        "https://graph.microsoft.com/v1.0/me/messages?$skip=10&$top=5&$select=id"
    )

    connector.list_messages(ConnectorMessageQuery(limit=99, cursor=cursor))

    request = stub.requests[0]
    assert str(request.url) == cursor
    assert request.url.params.get("$skip") == "10"
    assert request.url.params.get("$top") == "5"
    assert request.url.params.get("$select") == "id"


def test_query_containing_external_url_stays_on_graph(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    cursor = (
        "https://graph.microsoft.com/v1.0/me/messages"
        "?redirect=https://evil.example"
    )

    connector.list_messages(ConnectorMessageQuery(limit=10, cursor=cursor))

    assert len(stub.requests) == 1
    assert str(stub.requests[0].url) == cursor
    assert stub.requests[0].url.host == "graph.microsoft.com"
    assert all(request.url.host != "evil.example" for request in stub.requests)
