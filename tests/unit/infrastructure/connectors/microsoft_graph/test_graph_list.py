"""Unit tests for Microsoft Graph list_messages HTTP behavior."""

import pytest

from app.core.exceptions import ConnectorUnavailableError
from app.domain.enums import SourceType
from app.domain.interfaces import ConnectorMessageQuery, MessagePage
from app.infrastructure.connectors.microsoft_graph.pagination import (
    opaque_cursor_from_next_link,
)
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GRAPH_API_PREFIX,
    GRAPH_LIST_URL,
    GRAPH_TOKEN,
    graph_resource,
)


def test_provider_is_microsoft_graph(graph_connector: tuple) -> None:
    connector, _stub, _client = graph_connector

    assert connector.provider == "microsoft_graph"


def test_list_requests_me_messages(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=7))

    list_request = stub.requests[0]
    assert list_request.method == "GET"
    assert str(list_request.url).startswith(GRAPH_LIST_URL)
    assert list_request.url.host == "graph.microsoft.com"
    assert list_request.url.path.rstrip("/") == GRAPH_API_PREFIX
    assert list_request.headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"
    assert list_request.headers.get("accept") == "application/json"


def test_list_maps_limit_to_top(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=7))

    assert stub.requests[0].url.params.get("$top") == "7"
    assert stub.requests[0].url.params.get("$select") == "id"


def test_list_selects_only_id(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=3))

    params = stub.requests[0].url.params
    assert params.get("$select") == "id"
    assert "$filter" not in params
    assert "$orderby" not in params
    assert "$search" not in params
    assert "$skip" not in params
    assert "skiptoken" not in str(params).lower()


def test_empty_graph_list_returns_empty_page(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_ids = []

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert isinstance(page, MessagePage)
    assert page.items == []
    assert page.next_cursor is None
    assert len(stub.requests) == 1


def test_list_one_id_fetches_that_message(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")
    stub.list_ids = ["msg-1"]

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert [item.message_id for item in page.items] == ["msg-1"]
    assert page.items[0].metadata.source_type is SourceType.EMAIL
    assert len(stub.requests) == 2


def test_list_fetches_each_returned_message_id(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages = {
        "msg-a": graph_resource("msg-a"),
        "msg-b": graph_resource("msg-b"),
        "msg-c": graph_resource("msg-c"),
    }
    stub.list_ids = ["msg-a", "msg-b", "msg-c"]

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    fetch_paths = [request.url.path for request in stub.requests[1:]]
    assert fetch_paths == [
        f"{GRAPH_API_PREFIX}/msg-a",
        f"{GRAPH_API_PREFIX}/msg-b",
        f"{GRAPH_API_PREFIX}/msg-c",
    ]
    assert [item.message_id for item in page.items] == ["msg-a", "msg-b", "msg-c"]
    assert len(stub.requests) == 4


def test_list_preserves_graph_result_ordering(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages = {
        "msg-z": graph_resource("msg-z", subject="Z"),
        "msg-a": graph_resource("msg-a", subject="A"),
        "msg-m": graph_resource("msg-m", subject="M"),
    }
    stub.list_ids = ["msg-z", "msg-a", "msg-m"]

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert [item.message_id for item in page.items] == ["msg-z", "msg-a", "msg-m"]


def test_list_fetch_failure_fails_the_list(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages = {
        "msg-1": graph_resource("msg-1"),
        "msg-2": graph_resource("msg-2"),
        "msg-3": graph_resource("msg-3"),
    }
    stub.list_ids = ["msg-1", "msg-2", "msg-3"]
    stub.fetch_status["msg-2"] = 500

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))

    assert len(stub.requests) == 3
    assert stub.requests[2].url.path.endswith("/msg-2")


def test_list_does_not_follow_next_link(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages = {
        "msg-1": graph_resource("msg-1"),
        "msg-2": graph_resource("msg-2"),
    }
    stub.list_ids = ["msg-1"]
    stub.next_link = (
        "https://graph.microsoft.com/v1.0/me/messages?$select=id&$top=1&$skiptoken=page-2"
    )

    page = connector.list_messages(ConnectorMessageQuery(limit=1))

    list_calls = [
        request for request in stub.requests if request.url.path.rstrip("/") == GRAPH_API_PREFIX
    ]
    assert len(list_calls) == 1
    assert [item.message_id for item in page.items] == ["msg-1"]
    assert page.next_cursor == opaque_cursor_from_next_link(stub.next_link)
    assert "graph.microsoft.com" not in (page.next_cursor or "")


def test_list_does_not_retry_failed_list_request(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_status = 500

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=1))

    assert len(stub.requests) == 1


def test_list_ignores_unknown_collection_fields(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")
    stub.list_json = {
        "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#messages",
        "value": [{"id": "msg-1", "subject": "ignored-on-list", "@odata.etag": "W/\"abc\""}],
        "extra": "ignored",
    }

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert [item.message_id for item in page.items] == ["msg-1"]
    assert page.items[0].metadata.subject == "Status update"


def test_malformed_top_level_list_json_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = [{"id": "msg-1"}]

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


def test_missing_value_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = {"@odata.context": "https://graph.microsoft.com/v1.0/$metadata#messages"}

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


def test_null_value_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = {"value": None}

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


def test_non_list_value_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = {"value": {"id": "msg-1"}}

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


def test_list_item_non_object_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = {"value": ["msg-1"]}

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


def test_list_item_missing_id_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = {"value": [{"subject": "no-id"}]}

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


def test_list_item_blank_id_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_json = {"value": [{"id": "   "}]}

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


def test_list_does_not_call_profile_or_attachments(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=1))

    assert all(request.url.host == "graph.microsoft.com" for request in stub.requests)
    assert all(request.url.path.startswith(GRAPH_API_PREFIX) for request in stub.requests)
    assert all("/attachments" not in request.url.path for request in stub.requests)
    assert all("$value" not in str(request.url) for request in stub.requests)
    assert all("/oauth" not in str(request.url).lower() for request in stub.requests)
