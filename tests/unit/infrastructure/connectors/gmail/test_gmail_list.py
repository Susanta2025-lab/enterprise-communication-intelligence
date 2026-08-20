"""Unit tests for Gmail list_messages HTTP behavior."""

import pytest

from app.core.exceptions import ConnectorUnavailableError
from app.domain.interfaces import ConnectorMessageQuery, MessagePage
from tests.unit.infrastructure.connectors.gmail.conftest import (
    GMAIL_API_PREFIX,
    GMAIL_LIST_URL,
    GMAIL_TOKEN,
    gmail_resource,
)


def test_list_requests_users_me_messages(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=7))

    list_request = stub.requests[0]
    assert list_request.method == "GET"
    assert str(list_request.url).startswith(GMAIL_LIST_URL)
    assert list_request.url.path.rstrip("/") == GMAIL_API_PREFIX
    assert list_request.headers.get("authorization") == f"Bearer {GMAIL_TOKEN}"
    assert list_request.headers.get("accept") == "application/json"


def test_list_maps_limit_to_max_results(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=7))

    assert stub.requests[0].url.params.get("maxResults") == "7"


def test_list_omits_page_token_when_cursor_is_none(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=1))

    assert "pageToken" not in stub.requests[0].url.params


def test_list_passes_page_token_unchanged(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")
    cursor = "opaque-gmail-page-token"

    connector.list_messages(ConnectorMessageQuery(limit=1, cursor=cursor))

    assert stub.requests[0].url.params.get("pageToken") == cursor


def test_list_returns_next_page_token_unchanged(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")
    stub.next_page_token = "opaque-next-page"

    page = connector.list_messages(ConnectorMessageQuery(limit=1))

    assert page.next_cursor == "opaque-next-page"


def test_empty_gmail_list_returns_empty_page(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.list_ids = []

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert isinstance(page, MessagePage)
    assert page.items == []
    assert page.next_cursor is None
    assert len(stub.requests) == 1


def test_list_fetches_each_returned_message_id(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages = {
        "msg-a": gmail_resource("msg-a"),
        "msg-b": gmail_resource("msg-b"),
        "msg-c": gmail_resource("msg-c"),
    }
    stub.list_ids = ["msg-a", "msg-b", "msg-c"]

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    fetch_paths = [request.url.path for request in stub.requests[1:]]
    assert fetch_paths == [
        f"{GMAIL_API_PREFIX}/msg-a",
        f"{GMAIL_API_PREFIX}/msg-b",
        f"{GMAIL_API_PREFIX}/msg-c",
    ]
    assert [item.message_id for item in page.items] == ["msg-a", "msg-b", "msg-c"]
    assert len(stub.requests) == 4


def test_list_preserves_gmail_result_ordering(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages = {
        "msg-z": gmail_resource("msg-z", subject="Z"),
        "msg-a": gmail_resource("msg-a", subject="A"),
        "msg-m": gmail_resource("msg-m", subject="M"),
    }
    stub.list_ids = ["msg-z", "msg-a", "msg-m"]

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert [item.message_id for item in page.items] == ["msg-z", "msg-a", "msg-m"]


def test_list_fetch_failure_fails_the_list(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages = {
        "msg-1": gmail_resource("msg-1"),
        "msg-2": gmail_resource("msg-2"),
        "msg-3": gmail_resource("msg-3"),
    }
    stub.list_ids = ["msg-1", "msg-2", "msg-3"]
    stub.fetch_status["msg-2"] = 500

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))

    assert len(stub.requests) == 3
    assert stub.requests[2].url.path.endswith("/msg-2")


def test_list_does_not_follow_next_page_token(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages = {
        "msg-1": gmail_resource("msg-1"),
        "msg-2": gmail_resource("msg-2"),
    }
    stub.list_ids = ["msg-1"]
    stub.next_page_token = "another-page"

    page = connector.list_messages(ConnectorMessageQuery(limit=1))

    list_calls = [
        request
        for request in stub.requests
        if request.url.path.rstrip("/") == GMAIL_API_PREFIX
    ]
    assert len(list_calls) == 1
    assert [item.message_id for item in page.items] == ["msg-1"]
    assert page.next_cursor == "another-page"


def test_list_does_not_retry_failed_list_request(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.list_status = 500

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=1))

    assert len(stub.requests) == 1


def test_list_does_not_send_speculative_gmail_search_params(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")

    connector.list_messages(ConnectorMessageQuery(limit=3))

    params = stub.requests[0].url.params
    assert "q" not in params
    assert "labelIds" not in params
    assert "includeSpamTrash" not in params


def test_empty_object_list_is_terminal_page(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.list_json = {}

    page = connector.list_messages(ConnectorMessageQuery(limit=10))

    assert page.items == []
    assert page.next_cursor is None
    assert len(stub.requests) == 1


def test_null_messages_list_is_unavailable(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.list_json = {"messages": None}

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))


def test_non_list_messages_is_unavailable(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.list_json = {"messages": {"id": "msg-1"}}

    with pytest.raises(ConnectorUnavailableError):
        connector.list_messages(ConnectorMessageQuery(limit=10))
