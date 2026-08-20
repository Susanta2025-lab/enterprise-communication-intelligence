"""Unit tests for Gmail HTTP error mapping."""

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
from tests.unit.infrastructure.connectors.gmail.conftest import gmail_resource


def _assert_generic(exc: ConnectorError) -> None:
    text = exc.message.lower()
    assert "gmail" not in text
    assert "google" not in text
    assert "httpx" not in text
    assert "invalid authentication" not in text
    assert exc.__cause__ is None


def test_fetch_401_is_authentication_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["msg-1"] = 401
    stub.error_json = {
        "error": {"message": "Request had invalid authentication credentials."}
    }

    with pytest.raises(ConnectorAuthenticationError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "invalid authentication" not in exc_info.value.message


def test_fetch_403_is_permission_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["msg-1"] = 403
    stub.error_json = {"error": {"message": "Gmail API has not been used"}}

    with pytest.raises(ConnectorPermissionError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)


def test_fetch_403_rate_limit_reason_is_rate_limit_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["msg-1"] = 403
    stub.error_json = {
        "error": {
            "errors": [{"reason": "rateLimitExceeded"}],
            "message": "User-rate limit exceeded",
        }
    }

    with pytest.raises(ConnectorRateLimitError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "User-rate limit exceeded" not in exc_info.value.message


def test_fetch_404_is_not_found(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["msg-1"] = 404

    with pytest.raises(ConnectorMessageNotFoundError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)


def test_fetch_429_is_rate_limit_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["msg-1"] = 429

    with pytest.raises(ConnectorRateLimitError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert len(stub.requests) == 1


def test_fetch_500_is_unavailable(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["msg-1"] = 500
    stub.error_json = {"error": {"message": "backend error from Gmail"}}

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "backend error" not in exc_info.value.message
    assert len(stub.requests) == 1


def test_fetch_503_is_unavailable(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["msg-1"] = 503

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)


def test_timeout_is_unavailable(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.transport_error = httpx.TimeoutException("timed out")

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "timed out" not in exc_info.value.message
    assert len(stub.requests) == 1


def test_transport_error_is_unavailable(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.transport_error = httpx.ConnectError("dns failed")

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "dns failed" not in exc_info.value.message


def test_list_400_with_cursor_is_invalid_cursor(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.list_status = 400
    stub.error_json = {"error": {"message": "Invalid pageToken value"}}

    with pytest.raises(ConnectorInvalidCursorError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10, cursor="bad-token"))

    _assert_generic(exc_info.value)
    assert "pageToken" not in exc_info.value.message
    assert "bad-token" not in exc_info.value.message


def test_list_400_without_cursor_is_not_invalid_cursor(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.list_status = 400
    stub.error_json = {"error": {"message": "Invalid maxResults"}}

    with pytest.raises(ConnectorError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10))

    assert not isinstance(exc_info.value, ConnectorInvalidCursorError)
    _assert_generic(exc_info.value)


def test_non_json_success_is_unavailable(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_text["msg-1"] = "<html>not json</html>"

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
    assert "<html>not json</html>" not in exc_info.value.message


def test_redirect_is_not_followed(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["msg-1"] = 302

    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch_message("msg-1")

    assert len(stub.requests) == 1
    assert stub.requests[0].url.host == "gmail.googleapis.com"
    _assert_generic(exc_info.value)
    assert not isinstance(exc_info.value, ConnectorMessageNotFoundError)


def test_list_404_is_not_message_not_found(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.list_status = 404

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(limit=10))

    assert not isinstance(exc_info.value, ConnectorMessageNotFoundError)
    _assert_generic(exc_info.value)


def test_unexpected_fetch_status_is_generic_connector_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    for status in (400, 405, 409, 412):
        stub.requests.clear()
        stub.fetch_status["msg-1"] = status
        with pytest.raises(ConnectorError) as exc_info:
            connector.fetch_message("msg-1")
        assert exc_info.value.__class__ is ConnectorError
        _assert_generic(exc_info.value)
        assert len(stub.requests) == 1


def test_empty_success_body_is_unavailable(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_text["msg-1"] = ""

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)


def test_missing_from_header_is_content_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    resource = gmail_resource("msg-1")
    resource["payload"]["headers"] = [
        header for header in resource["payload"]["headers"] if header["name"] != "From"
    ]
    stub.messages["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        connector.fetch_message("msg-1")

    _assert_generic(exc_info.value)
