"""Privacy tests for Gmail reply executor logs and exceptions."""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import (
    CommunicationActionExecutionError,
    CommunicationCredentialUnavailableError,
    ServiceUnavailableError,
)
from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor
from tests.unit.infrastructure.executors.gmail.conftest import (
    CountingTokenProvider,
    execution_command,
    metadata_resource,
)

_SECRET_TOKEN = "SUPER_SECRET_GMAIL_TOKEN_123"
_SECRET_BODY = "SECRET_APPROVED_GMAIL_REPLY_BODY_123"
_SECRET_MESSAGE_ID = "SECRET_PROVIDER_MESSAGE_ID_123"
_SECRET_RECIPIENT = "distinctive-gmail-recipient-privacy@example.test"
_SECRET_MAILBOX = "secret-mailbox-owner@example.test"
_SECRET_SUBJECT = "SECRET_GMAIL_SUBJECT_123"
_SECRET_RFC_ID = "<SECRET_GMAIL_RFC_MESSAGE_ID_123@example.test>"
_SECRET_THREAD = "SECRET_GMAIL_THREAD_ID_123"
_GMAIL_ERROR_BODY = "SUPER_SECRET_GMAIL_ERROR_BODY_123"


def _serialized(events: list[dict]) -> str:
    return repr(events)


def _assert_secrets_absent(blob: str) -> None:
    lowered = blob.lower()
    assert _SECRET_TOKEN not in blob
    assert _SECRET_BODY not in blob
    assert _SECRET_MESSAGE_ID not in blob
    assert _SECRET_RECIPIENT not in blob
    assert _SECRET_MAILBOX not in blob
    assert _SECRET_SUBJECT not in blob
    assert _SECRET_RFC_ID not in blob
    assert _SECRET_THREAD not in blob
    assert _GMAIL_ERROR_BODY not in blob
    assert "authorization" not in lowered
    assert "bearer " not in lowered
    assert "credential_ref" not in lowered


def test_successful_reply_logs_omit_token_body_and_headers(
    gmail_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    _executor, stub, client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        provider_message_id=_SECRET_MESSAGE_ID,
        thread_id=_SECRET_THREAD,
        sender=_SECRET_RECIPIENT,
        subject=_SECRET_SUBJECT,
        rfc_message_id=_SECRET_RFC_ID,
    )
    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(_SECRET_TOKEN),
        mailbox_address=_SECRET_MAILBOX,
    )
    command = execution_command(
        approved_reply_body=_SECRET_BODY,
        provider_message_id=_SECRET_MESSAGE_ID,
    )

    result = executor.execute(command)

    assert result is None
    assert stub.metadata_requests()[0].headers.get("authorization") == f"Bearer {_SECRET_TOKEN}"
    _assert_secrets_absent(_serialized(log_events))


def test_error_logs_omit_token_body_recipient_and_gmail_payload(
    gmail_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    _executor, stub, client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        provider_message_id=_SECRET_MESSAGE_ID,
        thread_id=_SECRET_THREAD,
        sender=_SECRET_RECIPIENT,
        subject=_SECRET_SUBJECT,
        rfc_message_id=_SECRET_RFC_ID,
    )
    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(_SECRET_TOKEN),
        mailbox_address=_SECRET_MAILBOX,
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
        stub.send_status = status
        stub.send_json = {
            "error": {
                "code": 403,
                "message": _GMAIL_ERROR_BODY,
            }
        }
        with pytest.raises(error_type) as exc_info:
            executor.execute(command)
        _assert_secrets_absent(_serialized(log_events))
        _assert_secrets_absent(exc_info.value.message)
        assert stub.send_requests()[0].headers.get("authorization") == f"Bearer {_SECRET_TOKEN}"
        assert len(stub.send_requests()) == 1


def test_timeout_logs_omit_token_and_body(
    gmail_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    _executor, stub, client, _tokens = gmail_reply_executor
    stub.send_transport_error = httpx.TimeoutException("timed out")
    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(_SECRET_TOKEN),
        mailbox_address=_SECRET_MAILBOX,
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
    assert _SECRET_TOKEN not in repr(exc_info.value)


def test_provider_mismatch_logs_omit_body(
    gmail_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    executor, stub, _client, tokens = gmail_reply_executor
    command = execution_command(
        provider="microsoft_graph",
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
    gmail_reply_executor: tuple,
    log_events: list[dict],
) -> None:
    _executor, stub, client, _tokens = gmail_reply_executor

    def missing_token() -> str:
        raise CommunicationCredentialUnavailableError()

    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=missing_token,
        mailbox_address=_SECRET_MAILBOX,
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
