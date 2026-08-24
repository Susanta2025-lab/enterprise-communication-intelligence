"""Unit tests for Microsoft Graph HTTP error mapping."""

import httpx
import pytest

from app.core.exceptions import (
    ConnectorAuthenticationError,
    ConnectorError,
    ConnectorInvalidCursorError,
    ConnectorMessageContentError,
    ConnectorMessageNotFoundError,
    ConnectorPermissionError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
)
from app.domain.interfaces import ConnectorMessageQuery
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from app.infrastructure.connectors.microsoft_graph.pagination import (
    opaque_cursor_from_next_link,
)
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GRAPH_TOKEN,
    GraphHttpStub,
)

_SAFE_NEXT_LINK = (
    "https://graph.microsoft.com/v1.0/me/messages?$select=id&$top=10&$skiptoken=stale"
)
_SAFE_CURSOR = opaque_cursor_from_next_link(_SAFE_NEXT_LINK)


def _assert_generic(exc: ConnectorError) -> None:
    text = exc.message.lower()
    assert "graph" not in text
    assert "microsoft" not in text
    assert "outlook" not in text
    assert "httpx" not in text
    assert "invalidauthenticationtoken" not in text
    assert exc.__cause__ is None


def test_fetch_401_is_authentication_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["msg-1"] = 401
    stub.error_json = {
        "error": {
            "code": "InvalidAuthenticationToken",
            "message": "Access token has expired.",
            "innerError": {"request-id": "rid-secret", "date": "2026-08-20"},
        }
    }

    with pytest.raises(ConnectorAuthenticationError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "Access token has expired." not in exc_info.value.message
    assert "rid-secret" not in exc_info.value.message


def test_fetch_403_is_permission_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["msg-1"] = 403
    stub.error_json = {
        "error": {
            "code": "ErrorAccessDenied",
            "message": "Access is denied. Check credentials and try again.",
        }
    }

    with pytest.raises(ConnectorPermissionError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "Access is denied" not in exc_info.value.message


def test_fetch_404_is_not_found(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["msg-1"] = 404

    with pytest.raises(ConnectorMessageNotFoundError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)


def test_fetch_429_is_rate_limit_error_without_retry(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["msg-1"] = 429
    stub.error_json = {"error": {"code": "TooManyRequests", "message": "Retry-After: 30"}}

    with pytest.raises(ConnectorRateLimitError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "Retry-After" not in exc_info.value.message
    assert len(stub.requests) == 1


def test_fetch_500_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["msg-1"] = 500
    stub.error_json = {"error": {"code": "ServiceError", "message": "backend error from Graph"}}

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "backend error" not in exc_info.value.message
    assert len(stub.requests) == 1


def test_fetch_503_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["msg-1"] = 503

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)


def test_timeout_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.transport_error = httpx.TimeoutException("timed out")

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "timed out" not in exc_info.value.message
    assert len(stub.requests) == 1


def test_transport_error_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.transport_error = httpx.ConnectError("dns failed")

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "dns failed" not in exc_info.value.message


def test_list_400_with_cursor_is_invalid_cursor(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_status = 400
    stub.error_json = {"error": {"code": "InvalidRequest", "message": "Invalid skiptoken"}}

    with pytest.raises(ConnectorInvalidCursorError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10, cursor=_SAFE_CURSOR))

    _assert_generic(exc_info.value)
    assert "skiptoken" not in exc_info.value.message
    assert _SAFE_NEXT_LINK not in exc_info.value.message


def test_list_400_without_cursor_is_not_invalid_cursor(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_status = 400
    stub.error_json = {"error": {"code": "InvalidRequest", "message": "Invalid $top"}}

    with pytest.raises(ConnectorError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10))

    assert not isinstance(exc_info.value, ConnectorInvalidCursorError)
    _assert_generic(exc_info.value)


def test_fetch_400_is_generic_connector_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["msg-1"] = 400

    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch_message("msg-1")

    assert exc_info.value.__class__ is ConnectorError
    _assert_generic(exc_info.value)


def test_non_json_success_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_text["msg-1"] = "<html>not json</html>"

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "<html>not json</html>" not in exc_info.value.message


def test_redirect_is_not_followed(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["msg-1"] = 302

    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch_message("msg-1")

    assert len(stub.requests) == 1
    assert stub.requests[0].url.host == "graph.microsoft.com"
    assert all(request.url.host != "evil.example" for request in stub.requests)
    _assert_generic(exc_info.value)
    assert not isinstance(exc_info.value, ConnectorMessageNotFoundError)


def test_redirect_is_not_followed_when_client_would_follow(graph_stub: GraphHttpStub) -> None:
    graph_stub.fetch_status["msg-1"] = 302
    client = httpx.Client(
        transport=httpx.MockTransport(graph_stub),
        follow_redirects=True,
    )
    connector = MicrosoftGraphCommunicationConnector(
        http_client=client,
        access_token_provider=lambda: GRAPH_TOKEN,
    )
    try:
        with pytest.raises(ConnectorError) as exc_info:
            connector.fetch_message("msg-1")
        assert len(graph_stub.requests) == 1
        assert graph_stub.requests[0].url.host == "graph.microsoft.com"
        assert all(request.url.host != "evil.example" for request in graph_stub.requests)
        _assert_generic(exc_info.value)
    finally:
        client.close()


def test_list_404_is_not_message_not_found(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_status = 404

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10))

    assert not isinstance(exc_info.value, ConnectorMessageNotFoundError)
    _assert_generic(exc_info.value)


def test_continuation_404_is_not_message_not_found(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.list_status = 404

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10, cursor=_SAFE_CURSOR))

    assert not isinstance(exc_info.value, ConnectorMessageNotFoundError)
    assert not isinstance(exc_info.value, ConnectorInvalidCursorError)
    _assert_generic(exc_info.value)


def test_unexpected_fetch_status_is_generic_connector_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    for status in (405, 409, 412):
        stub.requests.clear()
        stub.fetch_status["msg-1"] = status
        with pytest.raises(ConnectorError) as exc_info:
            connector.fetch_message("msg-1")
        assert exc_info.value.__class__ is ConnectorError
        _assert_generic(exc_info.value)
        assert len(stub.requests) == 1


def test_empty_success_body_is_unavailable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_text["msg-1"] = ""

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)


def test_malformed_fetch_object_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_json["msg-1"] = ["not", "an", "object"]

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
