"""Unit tests for Microsoft Graph reply failure mapping."""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import CommunicationActionExecutionError, ServiceUnavailableError
from app.infrastructure.executors.microsoft_graph import MicrosoftGraphCommunicationActionExecutor
from tests.unit.infrastructure.executors.microsoft_graph.conftest import (
    CountingTokenProvider,
    GraphReplyHttpStub,
    execution_command,
)

_UNAVAILABLE = "Communication action execution is currently unavailable."
_FAILED = "Communication action execution failed."
_GRAPH_ERROR = {
    "error": {
        "code": "ErrorAccessDenied",
        "message": "Graph exploded: Access is denied for mailbox alice@example.com",
        "innerError": {"request-id": "rid-secret", "client-request-id": "cid-secret"},
    }
}


def _assert_generic_execution_error(exc: Exception) -> None:
    text = str(exc).lower()
    message = getattr(exc, "message", str(exc))
    blob = f"{message}{exc}{exc!r}".lower()
    assert "graph" not in blob
    assert "microsoft" not in blob
    assert "outlook" not in blob
    assert "httpx" not in text
    assert "alice@example.com" not in blob
    assert "rid-secret" not in blob
    assert "cid-secret" not in blob
    assert "graph exploded" not in blob
    assert exc.__cause__ is None


def test_graph_400_is_definite_execution_error(graph_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = graph_reply_executor
    stub.status = 400
    stub.error_json = _GRAPH_ERROR

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    assert exc_info.value.message == _FAILED
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.requests) == 1
    assert tokens.calls == 1


def test_graph_401_is_definite_execution_error(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 401
    stub.error_json = {
        "error": {
            "code": "InvalidAuthenticationToken",
            "message": "Access token has expired.",
        }
    }

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    assert "Access token has expired." not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)


def test_graph_403_is_definite_execution_error(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 403
    stub.error_json = {
        "error": {
            "code": "ErrorAccessDenied",
            "message": "Missing Mail.Send permission for this mailbox.",
        }
    }

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    assert "Mail.Send" not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)


def test_graph_404_is_definite_execution_error(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 404

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_generic_execution_error(exc_info.value)


def test_graph_409_is_definite_execution_error(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 409

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_generic_execution_error(exc_info.value)


def test_graph_422_is_definite_execution_error(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 422

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_generic_execution_error(exc_info.value)


def test_graph_429_is_definite_without_retry(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 429
    stub.error_json = {"error": {"code": "TooManyRequests", "message": "Retry-After: 30"}}

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_generic_execution_error(exc_info.value)
    assert "Retry-After" not in exc_info.value.message
    assert len(stub.requests) == 1


def test_graph_408_is_unavailable_not_definite_failure(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 408

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert exc_info.value.message == _UNAVAILABLE
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.requests) == 1


def test_graph_500_is_unavailable_not_definite_failure(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 500
    stub.error_json = {"error": {"code": "ServiceError", "message": "backend error from Graph"}}

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "backend error" not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.requests) == 1


def test_graph_503_is_unavailable_not_definite_failure(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 503

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    _assert_generic_execution_error(exc_info.value)


@pytest.mark.parametrize("status", [502, 504, 599])
def test_other_5xx_are_unavailable_not_definite_failure(
    graph_reply_executor: tuple,
    status: int,
) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = status

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.requests) == 1


def test_timeout_is_unavailable_without_retry(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.transport_error = httpx.TimeoutException("timed out contacting Graph")

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert exc_info.value.message == _UNAVAILABLE
    assert "timed out" not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.requests) == 1


def test_transport_error_is_unavailable_without_retry(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.transport_error = httpx.ConnectError("dns failed for graph.microsoft.com")

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "dns failed" not in exc_info.value.message
    assert "graph.microsoft.com" not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.requests) == 1


def test_unexpected_200_is_not_silently_accepted(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 200
    stub.body_json = {"id": "unexpected-success-body"}

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.requests) == 1


def test_unexpected_204_is_not_silently_accepted(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 204

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    _assert_generic_execution_error(exc_info.value)


def test_unexpected_201_is_not_silently_accepted(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 201

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    _assert_generic_execution_error(exc_info.value)


def test_informational_1xx_is_not_success(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 100

    with pytest.raises((CommunicationActionExecutionError, ServiceUnavailableError)) as exc_info:
        executor.execute(execution_command())

    _assert_generic_execution_error(exc_info.value)
    assert len(stub.requests) == 1


def test_redirect_is_not_followed(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.status = 302

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    assert len(stub.requests) == 1
    assert stub.requests[0].url.host == "graph.microsoft.com"
    assert all(request.url.host != "evil.example" for request in stub.requests)
    _assert_generic_execution_error(exc_info.value)


def test_redirect_is_not_followed_when_client_would_follow(
    graph_reply_stub: GraphReplyHttpStub,
) -> None:
    graph_reply_stub.status = 302
    token_provider = CountingTokenProvider()
    client = httpx.Client(
        transport=httpx.MockTransport(graph_reply_stub),
        follow_redirects=True,
    )
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=token_provider,
    )
    try:
        with pytest.raises(CommunicationActionExecutionError) as exc_info:
            executor.execute(execution_command())
        assert len(graph_reply_stub.requests) == 1
        assert graph_reply_stub.requests[0].url.host == "graph.microsoft.com"
        assert all(request.url.host != "evil.example" for request in graph_reply_stub.requests)
        authorization = graph_reply_stub.requests[0].headers.get("authorization")
        assert authorization is not None
        assert "evil.example" not in authorization
        _assert_generic_execution_error(exc_info.value)
    finally:
        client.close()
