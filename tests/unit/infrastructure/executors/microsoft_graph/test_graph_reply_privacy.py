"""Privacy tests for Microsoft Graph reply executor logs and exceptions."""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import (
    CommunicationActionExecutionError,
    CommunicationCredentialUnavailableError,
    ServiceUnavailableError,
)
from app.infrastructure.executors.microsoft_graph import MicrosoftGraphCommunicationActionExecutor
from tests.unit.infrastructure.executors.microsoft_graph.conftest import (
    CountingTokenProvider,
    execution_command,
)

_SECRET_TOKEN = "SUPER_SECRET_GRAPH_TOKEN_123"
_SECRET_BODY = "SECRET_APPROVED_REPLY_BODY_123"
_SECRET_MESSAGE_ID = "SECRET_PROVIDER_MESSAGE_ID_123"
_GRAPH_ERROR_BODY = "SUPER_SECRET_GRAPH_ERROR_BODY_123"


def _serialized(events: list[dict]) -> str:
    return repr(events)


def _assert_secrets_absent(blob: str) -> None:
    lowered = blob.lower()
    assert _SECRET_TOKEN not in blob
    assert _SECRET_BODY not in blob
    assert _SECRET_MESSAGE_ID not in blob
    assert _GRAPH_ERROR_BODY not in blob
    assert "authorization" not in lowered
    assert "bearer " not in lowered
    assert "credential_ref" not in lowered


def test_successful_reply_logs_omit_token_and_body(
    graph_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    _executor, stub, client, _tokens = graph_reply_executor
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(_SECRET_TOKEN),
    )
    command = execution_command(
        approved_reply_body=_SECRET_BODY,
        provider_message_id=_SECRET_MESSAGE_ID,
    )

    result = executor.execute(command)

    assert result is None
    assert stub.requests[0].headers.get("authorization") == f"Bearer {_SECRET_TOKEN}"
    _assert_secrets_absent(_serialized(log_events))


def test_error_logs_omit_token_body_and_graph_payload(
    graph_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    _executor, stub, client, _tokens = graph_reply_executor
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(_SECRET_TOKEN),
    )
    command = execution_command(
        approved_reply_body=_SECRET_BODY,
        provider_message_id=_SECRET_MESSAGE_ID,
    )
    cases = (
        (400, CommunicationActionExecutionError),
        (401, CommunicationActionExecutionError),
        (403, CommunicationActionExecutionError),
        (404, CommunicationActionExecutionError),
        (429, CommunicationActionExecutionError),
        (408, ServiceUnavailableError),
        (500, ServiceUnavailableError),
        (503, ServiceUnavailableError),
    )
    for status, error_type in cases:
        stub.requests.clear()
        stub.status = status
        stub.error_json = {
            "error": {
                "code": "ErrorAccessDenied",
                "message": _GRAPH_ERROR_BODY,
                "innerError": {"request-id": "rid-secret"},
            }
        }
        with pytest.raises(error_type) as exc_info:
            executor.execute(command)
        _assert_secrets_absent(_serialized(log_events))
        _assert_secrets_absent(exc_info.value.message)
        assert "rid-secret" not in exc_info.value.message
        assert stub.requests[0].headers.get("authorization") == f"Bearer {_SECRET_TOKEN}"
        assert len(stub.requests) == 1


def test_timeout_logs_omit_token_and_body(
    graph_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    _executor, stub, client, _tokens = graph_reply_executor
    stub.transport_error = httpx.TimeoutException("timed out")
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(_SECRET_TOKEN),
    )
    command = execution_command(
        approved_reply_body=_SECRET_BODY,
        provider_message_id=_SECRET_MESSAGE_ID,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(command)

    _assert_secrets_absent(_serialized(log_events))
    _assert_secrets_absent(exc_info.value.message)
    assert _SECRET_TOKEN not in str(exc_info.value)


def test_provider_mismatch_logs_omit_body(
    graph_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    executor, stub, _client, tokens = graph_reply_executor
    command = execution_command(
        provider="gmail",
        approved_reply_body=_SECRET_BODY,
        provider_message_id=_SECRET_MESSAGE_ID,
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []
    _assert_secrets_absent(_serialized(log_events))
    _assert_secrets_absent(exc_info.value.message)


def test_credential_unavailable_logs_omit_token_and_body(
    graph_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    _executor, stub, client, _tokens = graph_reply_executor

    def missing_token() -> str:
        raise CommunicationCredentialUnavailableError()

    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=missing_token,
    )
    command = execution_command(
        approved_reply_body=_SECRET_BODY,
        provider_message_id=_SECRET_MESSAGE_ID,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(command)

    assert stub.requests == []
    _assert_secrets_absent(_serialized(log_events))
    _assert_secrets_absent(exc_info.value.message)
    _assert_secrets_absent(str(exc_info.value))


def test_phase12f_markers_are_absent_from_graph_logs_and_exceptions(
    graph_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    token = "SUPER_SECRET_PHASE12_TOKEN"
    body = "SUPER_SECRET_PHASE12_REPLY_BODY"
    provider_error = "SUPER_SECRET_PHASE12_PROVIDER_ERROR"
    _executor, stub, client, _tokens = graph_reply_executor
    stub.status = 403
    stub.error_json = {"error": {"message": provider_error}}
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(token),
    )
    command = execution_command(approved_reply_body=body)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    blob = f"{_serialized(log_events)}{exc_info.value.message}{exc_info.value!r}"
    assert token not in blob
    assert body not in blob
    assert provider_error not in blob
    assert "SUPER_SECRET_PHASE12_CREDENTIAL_REF" not in blob
    assert "authorization" not in blob.lower()
    assert stub.requests[0].headers.get("authorization") == f"Bearer {token}"
