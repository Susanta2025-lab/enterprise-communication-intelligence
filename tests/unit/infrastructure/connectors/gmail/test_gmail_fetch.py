"""Unit tests for Gmail fetch_message HTTP behavior and identity mapping."""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import ConnectorMessageNotFoundError
from app.domain.enums import SourceType
from app.domain.interfaces import CommunicationConnector
from app.domain.models import CommunicationMessage
from tests.unit.infrastructure.connectors.gmail.conftest import (
    GMAIL_API_PREFIX,
    GMAIL_TOKEN,
    gmail_resource,
)


def test_gmail_connector_implements_communication_connector(
    gmail_connector: tuple,
) -> None:
    connector, _stub, _client = gmail_connector

    assert isinstance(connector, CommunicationConnector)
    assert connector.provider == "gmail"


def test_fetch_requests_message_endpoint_with_format_full(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")

    connector.fetch_message("msg-1")

    request = stub.requests[0]
    assert request.method == "GET"
    assert request.url.path == f"{GMAIL_API_PREFIX}/msg-1"
    assert request.url.params.get("format") == "full"
    assert request.headers.get("authorization") == f"Bearer {GMAIL_TOKEN}"
    assert request.headers.get("accept") == "application/json"


def test_fetch_returns_normalized_email_message(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        thread_id="thread-99",
        sender="Finance Bot <finance.bot@example.com>",
        to="ops.lead@example.com, sre.oncall@example.com",
        cc="manager@example.com",
        subject="Q3 budget review",
        body="Please review the Q3 budget proposal before Friday.",
        date="Wed, 20 Aug 2026 09:00:00 +0000",
        internal_date="1776704400000",
        label_ids=["INBOX", "IMPORTANT"],
    )

    message = connector.fetch_message("msg-1")

    assert isinstance(message, CommunicationMessage)
    assert message.metadata.source_type is SourceType.EMAIL
    assert message.message_id == "msg-1"
    assert message.metadata.source_id == "msg-1"
    assert message.metadata.thread_id == "thread-99"
    assert message.metadata.sender == "finance.bot@example.com"
    assert message.metadata.recipients == [
        "ops.lead@example.com",
        "sre.oncall@example.com",
        "manager@example.com",
    ]
    assert message.metadata.subject == "Q3 budget review"
    assert message.body == "Please review the Q3 budget proposal before Friday."
    assert message.metadata.sent_at == datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    assert message.metadata.received_at == datetime.fromtimestamp(
        1776704400000 / 1000, tz=UTC
    )
    assert message.metadata.labels == ["INBOX", "IMPORTANT"]
    assert "<html" not in message.body.lower()


def test_fetch_unknown_message_raises_not_found(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["missing"] = 404

    with pytest.raises(ConnectorMessageNotFoundError) as exc_info:
        connector.fetch_message("missing")

    assert exc_info.value.message == "Connector message not found."
    assert exc_info.value.__cause__ is None
    assert "missing" not in exc_info.value.message


def test_blank_provider_message_id_raises_not_found(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector

    with pytest.raises(ConnectorMessageNotFoundError):
        connector.fetch_message("   ")

    assert stub.requests == []


def test_malicious_message_id_cannot_change_host(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    malicious_id = "https://evil.example/steal"
    stub.messages[malicious_id] = gmail_resource(malicious_id)

    message = connector.fetch_message(malicious_id)

    request = stub.requests[0]
    raw_path = request.url.raw_path.decode("ascii")
    assert request.url.scheme == "https"
    assert request.url.host == "gmail.googleapis.com"
    assert raw_path.startswith("/gmail/v1/users/me/messages/")
    assert "%2F" in raw_path.upper() or "%2f" in raw_path
    assert message.message_id == malicious_id


def test_path_traversal_message_id_stays_on_gmail_host(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    malicious_id = "../../other-host?q=1"
    stub.messages[malicious_id] = gmail_resource(malicious_id)

    connector.fetch_message(malicious_id)

    request = stub.requests[0]
    raw_path = request.url.raw_path.decode("ascii")
    assert request.url.host == "gmail.googleapis.com"
    assert request.url.scheme == "https"
    assert request.url.params.get("format") == "full"
    assert request.url.params.get("q") is None
    assert raw_path.startswith("/gmail/v1/users/me/messages/")
    assert "%2F" in raw_path.upper()
    assert "%3F" in raw_path.upper()


def test_hash_in_message_id_cannot_change_target(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    malicious_id = "msg-1#https://evil.example"
    stub.messages[malicious_id] = gmail_resource(malicious_id)

    connector.fetch_message(malicious_id)

    request = stub.requests[0]
    raw_path = request.url.raw_path.decode("ascii")
    assert request.url.host == "gmail.googleapis.com"
    assert request.url.scheme == "https"
    assert request.url.fragment == ""
    assert raw_path.startswith("/gmail/v1/users/me/messages/")
    assert "%23" in raw_path.upper()


def test_connector_does_not_close_injected_client(gmail_connector: tuple) -> None:
    connector, stub, client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")

    connector.fetch_message("msg-1")

    assert len(stub.requests) == 1
    assert not client.is_closed
