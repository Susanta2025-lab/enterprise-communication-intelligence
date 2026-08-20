"""Unit tests for Microsoft Graph fetch_message HTTP behavior and identity mapping."""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import ConnectorMessageNotFoundError
from app.domain.enums import SourceType
from app.domain.interfaces import CommunicationConnector
from app.domain.models import CommunicationMessage
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    FETCH_SELECT_FIELDS,
    GRAPH_API_PREFIX,
    GRAPH_TOKEN,
    graph_resource,
)


def test_graph_connector_implements_communication_connector(
    graph_connector: tuple,
) -> None:
    connector, _stub, _client = graph_connector

    assert isinstance(connector, CommunicationConnector)
    assert connector.provider == "microsoft_graph"


def test_fetch_requests_message_endpoint_with_select_and_prefer(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.fetch_message("msg-1")

    request = stub.requests[0]
    assert request.method == "GET"
    assert request.url.host == "graph.microsoft.com"
    assert request.url.path == f"{GRAPH_API_PREFIX}/msg-1"
    fields = {part.strip() for part in request.url.params.get("$select", "").split(",") if part}
    assert fields == FETCH_SELECT_FIELDS
    assert "attachments" not in fields
    assert "bodyPreview" not in fields
    assert "uniqueBody" not in fields
    assert "internetMessageHeaders" not in fields
    assert request.headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"
    assert request.headers.get("accept") == "application/json"
    assert request.headers.get("prefer") == 'outlook.body-content-type="text"'


def test_fetch_returns_normalized_email_message(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        conversation_id="conv-99",
        from_address="finance.bot@example.com",
        from_name="Finance Bot",
        to=[("ops.lead@example.com", "Ops"), ("sre.oncall@example.com", None)],
        cc=[("manager@example.com", "Manager")],
        subject="Q3 budget review",
        body="Please review the Q3 budget proposal before Friday.",
        sent_at="2026-08-20T09:00:00Z",
        received_at="2026-08-20T09:01:00Z",
        categories=["INBOX", "IMPORTANT"],
        internet_message_id="<not-the-provider-id@example.com>",
    )

    message = connector.fetch_message("msg-1")

    assert isinstance(message, CommunicationMessage)
    assert message.metadata.source_type is SourceType.EMAIL
    assert message.message_id == "msg-1"
    assert message.metadata.source_id == "msg-1"
    assert message.metadata.thread_id == "conv-99"
    assert message.metadata.sender == "finance.bot@example.com"
    assert message.metadata.recipients == [
        "ops.lead@example.com",
        "sre.oncall@example.com",
        "manager@example.com",
    ]
    assert message.metadata.subject == "Q3 budget review"
    assert message.body == "Please review the Q3 budget proposal before Friday."
    assert message.metadata.sent_at == datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    assert message.metadata.received_at == datetime(2026, 8, 20, 9, 1, tzinfo=UTC)
    assert message.metadata.labels == ["INBOX", "IMPORTANT"]
    assert "<html" not in message.body.lower()


def test_fetch_unknown_message_raises_not_found(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.fetch_status["missing"] = 404

    with pytest.raises(ConnectorMessageNotFoundError) as exc_info:
        connector.fetch_message("missing")

    assert exc_info.value.message == "Connector message not found."
    assert exc_info.value.__cause__ is None
    assert "missing" not in exc_info.value.message


def test_blank_provider_message_id_raises_not_found(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector

    with pytest.raises(ConnectorMessageNotFoundError):
        connector.fetch_message("   ")

    assert stub.requests == []


def test_malicious_message_id_cannot_change_host(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    malicious_id = "https://evil.example/steal"
    stub.messages[malicious_id] = graph_resource(malicious_id)

    message = connector.fetch_message(malicious_id)

    request = stub.requests[0]
    raw_path = request.url.raw_path.decode("ascii")
    assert request.url.scheme == "https"
    assert request.url.host == "graph.microsoft.com"
    assert raw_path.startswith("/v1.0/me/messages/")
    assert "%2F" in raw_path.upper() or "%2f" in raw_path
    assert message.message_id == malicious_id


def test_path_traversal_message_id_stays_on_graph_host(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    malicious_id = "../../other-host?q=1"
    stub.messages[malicious_id] = graph_resource(malicious_id)

    connector.fetch_message(malicious_id)

    request = stub.requests[0]
    raw_path = request.url.raw_path.decode("ascii")
    assert request.url.host == "graph.microsoft.com"
    assert request.url.scheme == "https"
    assert request.url.params.get("q") is None
    assert raw_path.startswith("/v1.0/me/messages/")
    assert "%2F" in raw_path.upper()
    assert "%3F" in raw_path.upper()


def test_hash_and_query_characters_in_message_id_cannot_change_target(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    malicious_id = "msg-1#https://evil.example?x=1&y=2"
    stub.messages[malicious_id] = graph_resource(malicious_id)

    connector.fetch_message(malicious_id)

    request = stub.requests[0]
    raw_path = request.url.raw_path.decode("ascii")
    assert request.url.host == "graph.microsoft.com"
    assert request.url.scheme == "https"
    assert request.url.fragment == ""
    assert raw_path.startswith("/v1.0/me/messages/")
    assert "%23" in raw_path.upper()
    assert "%26" in raw_path.upper()
    assert "%3D" in raw_path.upper()


def test_direct_fetch_makes_one_request(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.fetch_message("msg-1")

    assert len(stub.requests) == 1
    assert "$value" not in str(stub.requests[0].url)
    assert "/attachments" not in str(stub.requests[0].url)


def test_connector_does_not_close_injected_client(graph_connector: tuple) -> None:
    connector, stub, client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    connector.fetch_message("msg-1")

    assert len(stub.requests) == 1
    assert not client.is_closed
