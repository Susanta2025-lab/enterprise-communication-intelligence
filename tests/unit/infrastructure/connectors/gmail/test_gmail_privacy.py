"""Privacy tests for Gmail adapter logs, exceptions, and token handling."""

import httpx
import pytest

from app.core.exceptions import (
    ConnectorAuthenticationError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
)
from app.domain.interfaces import ConnectorMessageQuery
from app.infrastructure.connectors.common.auth import AccessTokenProvider
from app.infrastructure.connectors.gmail import GmailCommunicationConnector
from tests.unit.infrastructure.connectors.gmail.conftest import GMAIL_TOKEN, gmail_resource

_SUBJECT = "UniqueSubjectZX91"
_SENDER = "unique.sender@example.test"
_RECIPIENT = "unique.recipient@example.test"
_BODY = "UniqueBodyContentZX91"
_MESSAGE_ID = "uniqueMsgIdZX91"
_PAGE_TOKEN = "uniquePageTokenZX91"


def _serialized(events: list[dict]) -> str:
    return repr(events)


def _assert_secrets_absent(blob: str) -> None:
    lowered = blob.lower()
    assert GMAIL_TOKEN not in blob
    assert "authorization" not in lowered
    assert "bearer " not in lowered
    assert _SUBJECT not in blob
    assert _SENDER not in blob
    assert _RECIPIENT not in blob
    assert _BODY not in blob
    assert _MESSAGE_ID not in blob
    assert _PAGE_TOKEN not in blob


def test_successful_fetch_logs_omit_token_and_content(
    gmail_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages[_MESSAGE_ID] = gmail_resource(
        _MESSAGE_ID,
        sender=_SENDER,
        to=_RECIPIENT,
        subject=_SUBJECT,
        body=_BODY,
    )

    message = connector.fetch_message(_MESSAGE_ID)

    assert stub.requests[0].headers.get("authorization") == f"Bearer {GMAIL_TOKEN}"
    assert message.body == _BODY
    _assert_secrets_absent(_serialized(log_events))


def test_error_logs_omit_token_and_vendor_bodies(
    gmail_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = gmail_connector
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
                "message": f"Gmail exploded for {_BODY}",
                "status": "PERMISSION_DENIED",
            }
        }
        with pytest.raises(error_type) as exc_info:
            connector.fetch_message(_MESSAGE_ID)
        _assert_secrets_absent(_serialized(log_events))
        _assert_secrets_absent(exc_info.value.message)
        assert stub.requests[0].headers.get("authorization") == f"Bearer {GMAIL_TOKEN}"
        assert len(stub.requests) == 1


def test_timeout_logs_omit_token(
    gmail_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = gmail_connector
    stub.transport_error = httpx.TimeoutException("timed out")

    with pytest.raises(ConnectorUnavailableError) as exc_info:
        connector.fetch_message(_MESSAGE_ID)

    _assert_secrets_absent(_serialized(log_events))
    _assert_secrets_absent(exc_info.value.message)
    assert GMAIL_TOKEN not in str(exc_info.value)


def test_list_cursor_is_not_logged(
    gmail_connector: tuple,
    log_events: list[dict],
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages[_MESSAGE_ID] = gmail_resource(
        _MESSAGE_ID,
        sender=_SENDER,
        to=_RECIPIENT,
        subject=_SUBJECT,
        body=_BODY,
    )
    stub.next_page_token = _PAGE_TOKEN

    page = connector.list_messages(ConnectorMessageQuery(limit=1, cursor=_PAGE_TOKEN))

    assert page.next_cursor == _PAGE_TOKEN
    assert stub.requests[0].url.params.get("pageToken") == _PAGE_TOKEN
    _assert_secrets_absent(_serialized(log_events))


def test_invalid_token_does_not_make_http_call(gmail_connector: tuple) -> None:
    _connector, stub, client = gmail_connector
    for token in (None, "", "   "):
        connector = GmailCommunicationConnector(
            http_client=client,
            access_token_provider=_constant_token(token),
        )

        with pytest.raises(ConnectorAuthenticationError) as exc_info:
            connector.fetch_message("msg-1")

        assert stub.requests == []
        assert GMAIL_TOKEN not in exc_info.value.message
        assert exc_info.value.message == "Connector authentication failed."


def _constant_token(token: object) -> AccessTokenProvider:
    def provide() -> str:
        return token  # type: ignore[return-value]

    return provide
