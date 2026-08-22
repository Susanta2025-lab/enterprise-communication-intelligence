"""Unit tests for Gmail reply failure mapping."""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import CommunicationActionExecutionError, ServiceUnavailableError
from tests.unit.infrastructure.executors.gmail.conftest import execution_command

_UNAVAILABLE = "Communication action execution is currently unavailable."
_FAILED = "Communication action execution failed."
_GMAIL_ERROR = {
    "error": {
        "code": 403,
        "message": "Gmail exploded: Access is denied for mailbox alice@example.com",
        "errors": [{"message": "SUPER_SECRET_GMAIL_ERROR_BODY_123", "reason": "forbidden"}],
    }
}


def _assert_generic_execution_error(exc: Exception) -> None:
    text = str(exc).lower()
    message = getattr(exc, "message", str(exc))
    blob = f"{message}{exc}{exc!r}".lower()
    assert "gmail" not in blob
    assert "google" not in blob
    assert "httpx" not in text
    assert "alice@example.com" not in blob
    assert "gmail exploded" not in blob
    assert "super_secret_gmail_error_body_123" not in blob
    assert exc.__cause__ is None


def _assert_metadata_only(stub: object) -> None:
    assert len(stub.metadata_requests()) == 1  # type: ignore[attr-defined]
    assert stub.send_requests() == []  # type: ignore[attr-defined]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_metadata_4xx_is_definite_execution_error_without_send(
    gmail_reply_executor: tuple,
    status: int,
) -> None:
    executor, stub, _client, tokens = gmail_reply_executor
    stub.metadata_status = status
    stub.metadata_json = _GMAIL_ERROR

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    assert exc_info.value.message == _FAILED
    _assert_generic_execution_error(exc_info.value)
    _assert_metadata_only(stub)
    assert tokens.calls == 1


def test_metadata_429_does_not_retry(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_status = 429
    stub.metadata_json = {"error": {"message": "Retry-After: 30"}}

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_generic_execution_error(exc_info.value)
    assert "Retry-After" not in exc_info.value.message
    _assert_metadata_only(stub)


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504, 599])
def test_metadata_unavailable_statuses_prevent_send(
    gmail_reply_executor: tuple,
    status: int,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_status = status
    stub.metadata_json = _GMAIL_ERROR

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert exc_info.value.message == _UNAVAILABLE
    _assert_generic_execution_error(exc_info.value)
    _assert_metadata_only(stub)


@pytest.mark.parametrize("status", [201, 202, 204])
def test_metadata_unexpected_2xx_prevents_send(
    gmail_reply_executor: tuple,
    status: int,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_status = status

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    _assert_generic_execution_error(exc_info.value)
    _assert_metadata_only(stub)


def test_metadata_timeout_is_unavailable_without_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_transport_error = httpx.TimeoutException("timed out contacting Gmail")

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "timed out" not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)
    _assert_metadata_only(stub)


def test_metadata_transport_error_is_unavailable_without_send(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_transport_error = httpx.ConnectError("dns failed for gmail.googleapis.com")

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "dns failed" not in exc_info.value.message
    assert "gmail.googleapis.com" not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)
    _assert_metadata_only(stub)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_send_4xx_is_definite_execution_error(
    gmail_reply_executor: tuple,
    status: int,
) -> None:
    executor, stub, _client, tokens = gmail_reply_executor
    stub.send_status = status
    stub.send_json = _GMAIL_ERROR

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    assert exc_info.value.message == _FAILED
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.metadata_requests()) == 1
    assert len(stub.send_requests()) == 1
    assert tokens.calls == 1


def test_send_429_does_not_retry(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_status = 429
    stub.send_json = {"error": {"message": "Retry-After: 30"}}

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_generic_execution_error(exc_info.value)
    assert "Retry-After" not in exc_info.value.message
    assert len(stub.send_requests()) == 1


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504, 599])
def test_send_unavailable_statuses_are_not_definite_failure(
    gmail_reply_executor: tuple,
    status: int,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_status = status
    stub.send_json = _GMAIL_ERROR

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert exc_info.value.message == _UNAVAILABLE
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.send_requests()) == 1


@pytest.mark.parametrize("status", [201, 202, 204])
def test_send_unexpected_2xx_is_unavailable(gmail_reply_executor: tuple, status: int) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_status = status

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.send_requests()) == 1


def test_send_timeout_is_unavailable_without_retry(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_transport_error = httpx.TimeoutException("timed out contacting Gmail")

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "timed out" not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.send_requests()) == 1


def test_send_transport_error_is_unavailable_without_retry(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_transport_error = httpx.ConnectError("dns failed for gmail.googleapis.com")

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "dns failed" not in exc_info.value.message
    assert "gmail.googleapis.com" not in exc_info.value.message
    _assert_generic_execution_error(exc_info.value)
    assert len(stub.send_requests()) == 1


def test_send_redirect_is_not_followed(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_status = 302

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    assert len(stub.send_requests()) == 1
    assert stub.send_requests()[0].url.host == "gmail.googleapis.com"
    assert all(request.url.host != "evil.example" for request in stub.requests)
    _assert_generic_execution_error(exc_info.value)
