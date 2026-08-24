"""Unit tests for Microsoft Graph pagination and nextLink security."""

import httpx
import pytest

from app.core.exceptions import ConnectorInvalidCursorError, ConnectorUnavailableError
from app.domain.interfaces import ConnectorMessageQuery
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from app.infrastructure.connectors.microsoft_graph.pagination import (
    opaque_cursor_from_next_link,
    pagination_params_from_cursor,
)
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
_SAFE_CURSOR = opaque_cursor_from_next_link(_SAFE_NEXT_LINK)


def test_next_link_is_normalized_to_opaque_cursor(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")
    stub.next_link = _SAFE_NEXT_LINK

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert page.next_cursor == _SAFE_CURSOR
    assert page.next_cursor is not None
    assert "graph.microsoft.com" not in page.next_cursor
    assert "https://" not in page.next_cursor
    assert "@odata.nextLink" not in page.next_cursor
    assert "$select" not in page.next_cursor
    assert _SAFE_NEXT_LINK != page.next_cursor


def test_blank_next_link_is_terminal_page(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = {"value": []}
    stub.list_json["@odata.nextLink"] = "   "

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert page.items == []
    assert page.next_cursor is None


def test_continuation_reconstructs_fixed_query(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-2"] = graph_resource("msg-2")
    stub.list_ids = ["msg-2"]

    page = connector.list_messages(ConnectorMessageQuery(limit=99, cursor=_SAFE_CURSOR))

    list_request = stub.requests[0]
    assert list_request.method == "GET"
    assert list_request.url.host == "graph.microsoft.com"
    assert list_request.url.path.rstrip("/") == GRAPH_API_PREFIX
    assert list_request.url.params.get("$skiptoken") == "OPAQUE-TOKEN-ZX91"
    assert list_request.url.params.get("$top") == "99"
    assert list_request.url.params.get("$select") == "id"
    assert [item.message_id for item in page.items] == ["msg-2"]


def test_continuation_uses_current_query_limit(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-2"] = graph_resource("msg-2")
    stub.list_ids = ["msg-2"]

    connector.list_messages(ConnectorMessageQuery(limit=1, cursor=_SAFE_CURSOR))

    params = stub.requests[0].url.params
    assert params.get("$top") == "1"
    assert params.get("$select") == "id"
    assert params.get("$skiptoken") == "OPAQUE-TOKEN-ZX91"


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

    page = connector.list_messages(ConnectorMessageQuery(limit=10, cursor=_SAFE_CURSOR))

    list_calls = [
        request for request in stub.requests if request.url.path.rstrip("/") == GRAPH_API_PREFIX
    ]
    assert len(list_calls) == 1
    assert list_calls[0].url.params.get("$skiptoken") == "OPAQUE-TOKEN-ZX91"
    assert len(stub.requests) == 3
    assert page.next_cursor == opaque_cursor_from_next_link(stub.next_link)
    assert "graph.microsoft.com" not in (page.next_cursor or "")


def test_skip_only_next_link_continues_with_skip(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    next_link = "https://graph.microsoft.com/v1.0/me/messages?$skip=10&$top=5&$select=id"
    stub.next_link = next_link

    page = connector.list_messages(ConnectorMessageQuery(limit=5))
    cursor = page.next_cursor
    assert cursor == opaque_cursor_from_next_link(next_link)
    assert cursor is not None
    assert "graph.microsoft.com" not in cursor

    stub.requests.clear()
    connector.list_messages(ConnectorMessageQuery(limit=7, cursor=cursor))
    params = stub.requests[0].url.params
    assert params.get("$skip") == "10"
    assert params.get("$top") == "7"
    assert params.get("$select") == "id"
    assert params.get("$skiptoken") is None


def test_skiptoken_is_preferred_over_skip() -> None:
    next_link = (
        "https://graph.microsoft.com/v1.0/me/messages"
        "?$select=id&$skip=250&$skiptoken=keep-me"
    )
    cursor = opaque_cursor_from_next_link(next_link)
    assert pagination_params_from_cursor(cursor) == {"$skiptoken": "keep-me"}


def test_encoded_next_link_skiptoken_round_trips(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    next_link = (
        "https://graph.microsoft.com/v1.0/me/messages?%24skiptoken=abc%2Fdef%3D"
    )
    stub.next_link = next_link

    page = connector.list_messages(ConnectorMessageQuery(limit=10))
    cursor = page.next_cursor
    assert cursor == opaque_cursor_from_next_link(next_link)

    stub.requests.clear()
    connector.list_messages(ConnectorMessageQuery(limit=10, cursor=cursor))
    assert stub.requests[0].url.params.get("$skiptoken") == "abc/def="


def test_provider_next_link_to_other_host_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    stub.next_link = "https://evil.example/v1.0/me/messages?$skiptoken=steal"

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


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
        _SAFE_NEXT_LINK,
        "gmail-page-token",
        "st.",
        "sk.",
    ],
)
def test_malicious_or_raw_url_cursor_is_rejected_before_http(
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


def test_uppercase_graph_host_next_link_is_normalized(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    stub.next_link = (
        "https://GRAPH.MICROSOFT.COM/v1.0/me/messages?$skiptoken=OPAQUE-TOKEN-ZX91"
    )

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert page.next_cursor == _SAFE_CURSOR
    assert "GRAPH.MICROSOFT.COM" not in (page.next_cursor or "")


def test_port_443_and_trailing_slash_next_links_are_normalized(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    stub.next_link = (
        "https://graph.microsoft.com:443/v1.0/me/messages/"
        "?$select=id&$top=5&$skiptoken=port-443"
    )

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert page.next_cursor == opaque_cursor_from_next_link(stub.next_link)
    assert "graph.microsoft.com" not in (page.next_cursor or "")

    stub.requests.clear()
    connector.list_messages(ConnectorMessageQuery(limit=10, cursor=page.next_cursor))
    request = stub.requests[0]
    assert request.url.host == "graph.microsoft.com"
    assert request.url.params.get("$skiptoken") == "port-443"
    assert request.url.params.get("$top") == "10"


def test_query_containing_external_url_does_not_leave_graph(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []
    stub.next_link = (
        "https://graph.microsoft.com/v1.0/me/messages"
        "?redirect=https://evil.example&$skiptoken=stay"
    )

    page = connector.list_messages(ConnectorMessageQuery(limit=10))
    cursor = page.next_cursor
    assert cursor is not None
    assert "evil.example" not in cursor

    stub.requests.clear()
    connector.list_messages(ConnectorMessageQuery(limit=10, cursor=cursor))
    assert stub.requests[0].url.host == "graph.microsoft.com"
    assert all(request.url.host != "evil.example" for request in stub.requests)
