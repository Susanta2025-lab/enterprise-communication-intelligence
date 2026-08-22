"""Unit tests for Gmail reply metadata safety and fail-closed recipient rules."""

from __future__ import annotations

import pytest

from app.core.exceptions import CommunicationActionExecutionError, ServiceUnavailableError
from tests.unit.infrastructure.executors.gmail.conftest import (
    FROM_ADDRESS,
    RFC_MESSAGE_ID,
    SUBJECT,
    THREAD_ID,
    execution_command,
    header,
    metadata_resource,
)

_FAILED = "Communication action execution failed."


def _assert_failed_before_send(stub: object, exc: CommunicationActionExecutionError) -> None:
    assert exc.message == _FAILED
    assert stub.send_requests() == []  # type: ignore[attr-defined]
    assert len(stub.metadata_requests()) == 1  # type: ignore[attr-defined]
    assert exc.__cause__ is None
    blob = f"{exc.message}{exc}{exc!r}".lower()
    assert "gmail" not in blob
    assert FROM_ADDRESS not in blob
    assert RFC_MESSAGE_ID.lower() not in blob


def test_multiple_reply_to_mailboxes_fail_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        reply_to="replies@example.test, other@example.test",
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)
    assert "replies@example.test" not in exc_info.value.message


def test_multiple_from_mailboxes_fail_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        sender="Alice <alice@example.test>, Bob <bob@example.test>",
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_malformed_reply_to_fails_closed_without_from_fallback(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(reply_to="not-a-mailbox")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_blank_reply_to_fails_closed_without_from_fallback(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(reply_to="   ")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_malformed_from_fails_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(sender="not-a-mailbox")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [
        metadata_resource() | {"threadId": None},
        {k: v for k, v in metadata_resource().items() if k != "threadId"},
        metadata_resource(thread_id="   "),
        metadata_resource(
            headers=[header("Subject", SUBJECT), header("Message-ID", RFC_MESSAGE_ID)],
        ),
        metadata_resource(
            headers=[header("From", FROM_ADDRESS), header("Message-ID", RFC_MESSAGE_ID)],
        ),
        metadata_resource(headers=[header("From", FROM_ADDRESS), header("Subject", SUBJECT)]),
        metadata_resource(subject="   "),
        metadata_resource(rfc_message_id="   "),
        metadata_resource(rfc_message_id="not-a-message-id"),
        metadata_resource(sender="   "),
    ],
)
def test_missing_required_metadata_fails_before_send(
    gmail_reply_executor: tuple,
    payload: dict,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = payload

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_missing_payload_fails_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = {"id": "gmail-msg-abc123", "threadId": THREAD_ID}

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_duplicate_from_fails_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        headers=[
            header("From", FROM_ADDRESS),
            header("From", "other@example.test"),
            header("Subject", SUBJECT),
            header("Message-ID", RFC_MESSAGE_ID),
        ]
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_duplicate_reply_to_fails_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        headers=[
            header("From", FROM_ADDRESS),
            header("Reply-To", "replies@example.test"),
            header("Reply-To", "other@example.test"),
            header("Subject", SUBJECT),
            header("Message-ID", RFC_MESSAGE_ID),
        ]
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_duplicate_subject_fails_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        headers=[
            header("From", FROM_ADDRESS),
            header("Subject", SUBJECT),
            header("Subject", "Other subject"),
            header("Message-ID", RFC_MESSAGE_ID),
        ]
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_duplicate_message_id_fails_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        headers=[
            header("From", FROM_ADDRESS),
            header("Subject", SUBJECT),
            header("Message-ID", RFC_MESSAGE_ID),
            header("Message-ID", "<other@example.test>"),
        ]
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_duplicate_references_fails_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        headers=[
            header("From", FROM_ADDRESS),
            header("Subject", SUBJECT),
            header("Message-ID", RFC_MESSAGE_ID),
            header("References", "<a@example.test>"),
            header("References", "<b@example.test>"),
        ]
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("From", "sender@example.test\r\nBcc: victim@example.test"),
        ("Reply-To", "replies@example.test\nCc: victim@example.test"),
        ("Subject", "Hello\r\nBcc: victim@example.test"),
        ("Message-ID", "<id@example.test>\nBcc: victim@example.test"),
        ("References", "<root@example.test>\r\nBcc: victim@example.test"),
    ],
)
def test_header_injection_fails_before_send(
    gmail_reply_executor: tuple,
    name: str,
    value: str,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    headers = [
        header("From", FROM_ADDRESS),
        header("Subject", SUBJECT),
        header("Message-ID", RFC_MESSAGE_ID),
    ]
    replaced = False
    updated: list[dict[str, str]] = []
    for item in headers:
        if item["name"] == name:
            updated.append(header(name, value))
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(header(name, value))
    stub.metadata_json = metadata_resource(headers=updated)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)
    assert "victim@example.test" not in exc_info.value.message


def test_malformed_metadata_json_is_unavailable_before_send(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_text = "{not-json"

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert stub.send_requests() == []
    assert len(stub.metadata_requests()) == 1
    assert "not-json" not in exc_info.value.message


def test_non_object_metadata_json_is_unavailable_before_send(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = ["not", "an", "object"]

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert stub.send_requests() == []


def test_non_object_payload_is_unavailable_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = {"id": "gmail-msg-abc123", "threadId": THREAD_ID, "payload": "oops"}

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert stub.send_requests() == []


def test_case_insensitive_duplicate_subject_fails_before_send(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        headers=[
            header("From", FROM_ADDRESS),
            header("Subject", SUBJECT),
            header("subject", "other subject"),
            header("SUBJECT", "third subject"),
            header("Message-ID", RFC_MESSAGE_ID),
        ]
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_case_insensitive_duplicate_from_fails_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        headers=[
            header("From", FROM_ADDRESS),
            header("FROM", "other@example.test"),
            header("Subject", SUBJECT),
            header("Message-ID", RFC_MESSAGE_ID),
        ]
    )

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


@pytest.mark.parametrize(
    "sender",
    [
        "undisclosed-recipients:;",
        "Friends: alice@example.test;",
        "Friends: alice@example.test, bob@example.test;",
        "alice@example.test, bob@example.test",
        "Alice <alice@example.test>, Bob <bob@example.test>",
    ],
)
def test_group_and_multiple_from_headers_fail_before_send(
    gmail_reply_executor: tuple,
    sender: str,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(sender=sender)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


def test_malformed_reply_to_group_does_not_fall_back_to_from(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(reply_to="Replies: replies@example.test;")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


@pytest.mark.parametrize(
    "rfc_message_id",
    [
        "abc@example.test",
        "<>",
        "<a b@example.test>",
        "<a@example.test>\r\nBcc: x@example.test",
        "<a@example.test> <b@example.test>",
        "<@example.test>",
        "<abc@>",
    ],
)
def test_malformed_message_id_fails_before_send(
    gmail_reply_executor: tuple,
    rfc_message_id: str,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(rfc_message_id=rfc_message_id)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


@pytest.mark.parametrize(
    "references",
    [
        "please see previous conversation",
        "<a@example.test> not-an-id <b@example.test>",
        "abc@example.test",
        "<a@example.test>\r\nBcc: victim@example.test",
        "<a b@example.test>",
    ],
)
def test_malformed_references_fail_before_send(
    gmail_reply_executor: tuple,
    references: str,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(references=references)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)
    assert stub.send_requests() == []


def test_thread_id_control_characters_fail_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(thread_id="thread\x00id")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    _assert_failed_before_send(stub, exc_info.value)


@pytest.mark.parametrize(
    "thread_id",
    [
        ["thread-list"],
        {"id": "thread-object"},
        12345,
    ],
)
def test_non_string_thread_id_is_unavailable_before_send(
    gmail_reply_executor: tuple,
    thread_id: object,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource() | {"threadId": thread_id}

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert stub.send_requests() == []
    assert len(stub.metadata_requests()) == 1


def test_list_payload_is_unavailable_before_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = {"id": "gmail-msg-abc123", "threadId": THREAD_ID, "payload": ["oops"]}

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert stub.send_requests() == []


@pytest.mark.parametrize("headers", [{"From": FROM_ADDRESS}, "From: x", 12])
def test_non_list_headers_are_unavailable_before_send(
    gmail_reply_executor: tuple,
    headers: object,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = {
        "id": "gmail-msg-abc123",
        "threadId": THREAD_ID,
        "payload": {"headers": headers},
    }

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert stub.send_requests() == []


@pytest.mark.parametrize(
    "headers",
    [
        [header("From", FROM_ADDRESS), "not-an-object", header("Subject", SUBJECT)],
        [
            header("From", FROM_ADDRESS),
            {"name": "Subject", "value": SUBJECT},
            {"name": 1, "value": RFC_MESSAGE_ID},
        ],
        [
            header("From", FROM_ADDRESS),
            {"name": "Subject", "value": 12},
            header("Message-ID", RFC_MESSAGE_ID),
        ],
    ],
)
def test_malformed_header_item_types_are_unavailable_before_send(
    gmail_reply_executor: tuple,
    headers: list[object],
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = {
        "id": "gmail-msg-abc123",
        "threadId": THREAD_ID,
        "payload": {"headers": headers},
    }

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert stub.send_requests() == []
    assert "gmail" not in exc_info.value.message.lower()
