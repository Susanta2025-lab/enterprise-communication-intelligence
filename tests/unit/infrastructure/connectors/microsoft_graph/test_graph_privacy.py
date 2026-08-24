"""Privacy tests for Microsoft Graph adapter logs, exceptions, and token handling."""

import httpx
import pytest

from app.core.exceptions import (
    ConnectorAuthenticationError,
    ConnectorInvalidCursorError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
)
from app.domain.interfaces import ConnectorMessageQuery
from app.infrastructure.connectors.common.auth import AccessTokenProvider
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from app.infrastructure.connectors.microsoft_graph.pagination import (
    opaque_cursor_from_next_link,
)
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GRAPH_TOKEN,
    graph_resource,
)

_SUBJECT = "UniqueSubjectZX91"
_SENDER = "unique.sender@example.test"
_RECIPIENT = "unique.recipient@example.test"
_BODY = "UniqueBodyContentZX91"
_MESSAGE_ID = "uniqueMsgIdZX91"
_CONVERSATION_ID = "uniqueConvIdZX91"
_NEXT_LINK = (
    "https://graph.microsoft.com/v1.0/me/messages"
    "?$select=id&$top=1&$skiptoken=uniqueSkipTokenZX91"
)


def _serialized(events: list[dict]) -> str:
    return repr(events)


def _assert_secrets_absent(blob: str) -> None:
    lowered = blob.lower()
    assert GRAPH_TOKEN not in blob
    assert "authorization" not in lowered
    assert "bearer " not in lowered
    assert _SUBJECT not in blob
    assert _SENDER not in blob
    assert _RECIPIENT not in blob
    assert _BODY not in blob
    assert _MESSAGE_ID not in blob
    assert _CONVERSATION_ID not in blob
    assert _NEXT_LINK not in blob
    assert "uniqueSkipTokenZX91" not in blob


def test_successful_fetch_logs_omit_token_and_content(
    graph_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = graph_connector
    stub.messages[_MESSAGE_ID] = graph_resource(
        _MESSAGE_ID,
        conversation_id=_CONVERSATION_ID,
        from_address=_SENDER,
        to=[(_RECIPIENT, None)],
        subject=_SUBJECT,
        body=_BODY,
    )

    message = connector.fetch_message(_MESSAGE_ID)

    assert stub.requests[0].headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"
    assert message.body == _BODY
    _assert_secrets_absent(_serialized(log_events))


def test_error_logs_omit_token_and_vendor_bodies(
    graph_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = graph_connector
    cases = (
        (401, ConnectorAuthenticationError),
        (429, ConnectorRateLimitError),
        (500, ConnectorUnavailableError),
    )
    for status, error_type in cases:
        stub.requests.clear()
        stub.fetch_status[_MESSAGE_ID] = status
        stub.error_json = {
            "error": {
                "code": "ErrorAccessDenied",
                "message": f"Graph exploded for {_BODY}",
                "innerError": {"request-id": "rid-secret", "client-request-id": "cid-secret"},
            }
        }
        with pytest.raises(error_type) as exc_info:
            connector.fetch_message(_MESSAGE_ID)
        _assert_secrets_absent(_serialized(log_events))
        _assert_secrets_absent(exc_info.value.message)
        assert "rid-secret" not in exc_info.value.message
        assert "Graph exploded" not in exc_info.value.message
        assert stub.requests[0].headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"
        assert len(stub.requests) == 1


def test_timeout_logs_omit_token(
    graph_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = graph_connector
    stub.transport_error = httpx.TimeoutException("timed out")

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message(_MESSAGE_ID)

    _assert_secrets_absent(_serialized(log_events))
    _assert_secrets_absent(exc_info.value.message)
    assert GRAPH_TOKEN not in str(exc_info.value)


def test_list_next_link_is_not_logged(
    graph_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = graph_connector
    stub.messages[_MESSAGE_ID] = graph_resource(
        _MESSAGE_ID,
        conversation_id=_CONVERSATION_ID,
        from_address=_SENDER,
        to=[(_RECIPIENT, None)],
        subject=_SUBJECT,
        body=_BODY,
    )
    stub.next_link = _NEXT_LINK

    page = connector.list_messages(
        ConnectorMessageQuery(limit=1, cursor=opaque_cursor_from_next_link(_NEXT_LINK))
    )

    assert page.next_cursor == opaque_cursor_from_next_link(_NEXT_LINK)
    assert page.next_cursor != _NEXT_LINK
    assert stub.requests[0].url.host == "graph.microsoft.com"
    assert stub.requests[0].url.params.get("$skiptoken") == "uniqueSkipTokenZX91"
    _assert_secrets_absent(_serialized(log_events))


def test_rejected_cursor_does_not_expose_token_or_url(
    graph_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = graph_connector
    cursor = "https://evil.example/v1.0/me/messages?token=steal"

    with pytest.raises(ConnectorInvalidCursorError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10, cursor=cursor))

    assert stub.requests == []
    _assert_secrets_absent(_serialized(log_events))
    _assert_secrets_absent(exc_info.value.message)
    assert GRAPH_TOKEN not in str(exc_info.value)
    assert "evil.example" not in exc_info.value.message


def test_invalid_token_does_not_make_http_call(graph_connector: tuple) -> None:
    _connector, stub, client = graph_connector
    for token in (None, "", "   "):
        connector = MicrosoftGraphCommunicationConnector(
            http_client=client,
            access_token_provider=_constant_token(token),
        )

        with pytest.raises(ConnectorAuthenticationError) as exc_info:
            connector.fetch_message("msg-1")

        assert stub.requests == []
        assert GRAPH_TOKEN not in exc_info.value.message
        assert exc_info.value.message == "Connector authentication failed."


def test_token_provider_exception_is_unavailable_error(graph_connector: tuple) -> None:
    _connector, stub, client = graph_connector

    def boom() -> str:
        raise RuntimeError("token store exploded")

    connector = MicrosoftGraphCommunicationConnector(
        http_client=client,
        access_token_provider=boom,
    )

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    assert stub.requests == []
    assert GRAPH_TOKEN not in exc_info.value.message
    assert "token store exploded" not in exc_info.value.message
    assert exc_info.value.__cause__ is None
    assert exc_info.value.message == "Connector is currently unavailable."


def _constant_token(token: object) -> AccessTokenProvider:
    def provide() -> str:
        return token  # type: ignore[return-value]

    return provide
