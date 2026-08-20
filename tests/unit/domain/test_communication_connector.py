"""Unit tests for the CommunicationConnector contract and page/query types."""

from typing import get_args, get_origin, get_type_hints

import pytest
from pydantic import ValidationError

from app.domain.enums import SourceType
from app.domain.interfaces import CommunicationConnector, ConnectorMessageQuery, MessagePage
from app.domain.models import CommunicationMessage, MessageMetadata


def _message(**overrides: object) -> CommunicationMessage:
    payload: dict[str, object] = {
        "body": "Please review the attached quarterly report.",
        "message_id": "fake-msg-001",
        "metadata": MessageMetadata(
            source_type=SourceType.EMAIL,
            sender="alice@example.com",
            recipients=["bob@example.com"],
            subject="Quarterly report",
        ),
    }
    payload.update(overrides)
    return CommunicationMessage.model_validate(payload)


def test_connector_contract_uses_domain_and_python_types() -> None:
    """The connector port must expose only domain and Python types."""
    fetch_hints = get_type_hints(CommunicationConnector.fetch_message)
    assert fetch_hints["provider_message_id"] is str
    assert fetch_hints["return"] is CommunicationMessage

    list_hints = get_type_hints(CommunicationConnector.list_messages)
    assert list_hints["query"] is ConnectorMessageQuery
    assert list_hints["return"] is MessagePage

    provider_getter = CommunicationConnector.provider.fget
    assert provider_getter is not None
    provider_hints = get_type_hints(provider_getter)
    assert provider_hints["return"] is str


def test_query_and_page_fields_keep_cursors_opaque() -> None:
    """Application-facing pagination is only str | None."""
    assert set(ConnectorMessageQuery.model_fields) == {"limit", "cursor"}
    assert set(MessagePage.model_fields) == {"items", "next_cursor"}
    assert "pageToken" not in ConnectorMessageQuery.model_fields
    assert "nextLink" not in MessagePage.model_fields
    assert "skipToken" not in MessagePage.model_fields

    cursor_annotation = ConnectorMessageQuery.model_fields["cursor"].annotation
    next_cursor_annotation = MessagePage.model_fields["next_cursor"].annotation
    assert get_origin(cursor_annotation) is type(str | None)
    assert str in get_args(cursor_annotation) or cursor_annotation is str | None
    assert next_cursor_annotation is str | None or str in get_args(next_cursor_annotation)


def test_message_page_accepts_communication_messages() -> None:
    """A page must carry domain CommunicationMessage items."""
    message = _message()
    page = MessagePage(items=[message], next_cursor="n:1")

    assert page.items == [message]
    assert isinstance(page.items[0], CommunicationMessage)
    assert page.items[0].metadata.source_type is SourceType.EMAIL
    assert page.next_cursor == "n:1"


def test_message_page_allows_terminal_cursor() -> None:
    """A missing next_cursor means the caller has reached the last page."""
    page = MessagePage(items=[_message()], next_cursor=None)

    assert page.next_cursor is None
    assert len(page.items) == 1


def test_query_default_limit_is_bounded() -> None:
    """Queries default to a small page size within 1-100."""
    query = ConnectorMessageQuery()

    assert query.limit == 10
    assert query.cursor is None


def test_query_rejects_out_of_range_limits() -> None:
    """Limit must stay within the documented bounds."""
    with pytest.raises(ValidationError):
        ConnectorMessageQuery(limit=0)
    with pytest.raises(ValidationError):
        ConnectorMessageQuery(limit=101)


def test_query_rejects_blank_cursor() -> None:
    """Blank continuation tokens are invalid before an adapter sees them."""
    with pytest.raises(ValidationError):
        ConnectorMessageQuery(cursor="   ")


def test_query_forbids_vendor_pagination_fields() -> None:
    """Unknown pagination fields must not be accepted on the query model."""
    with pytest.raises(ValidationError):
        ConnectorMessageQuery.model_validate({"limit": 10, "pageToken": "abc"})


def test_message_page_rejects_blank_next_cursor() -> None:
    """A blank continuation token is invalid; omit next_cursor to end the page."""
    with pytest.raises(ValidationError):
        MessagePage(items=[_message()], next_cursor="   ")


def test_message_page_forbids_vendor_pagination_fields() -> None:
    """Unknown pagination fields must not be accepted on the page model."""
    with pytest.raises(ValidationError):
        MessagePage.model_validate(
            {"items": [_message().model_dump()], "nextLink": "https://example"}
        )


def test_source_type_has_no_vendor_email_members() -> None:
    """Email remains the medium; vendor identity does not belong on SourceType."""
    values = {member.value for member in SourceType}
    assert SourceType.EMAIL == "email"
    assert "gmail" not in values
    assert "outlook" not in values
    assert "microsoft_graph" not in values
    assert not hasattr(SourceType, "GMAIL")
    assert not hasattr(SourceType, "OUTLOOK")
    assert not hasattr(SourceType, "MICROSOFT_GRAPH")


def test_connector_contract_is_read_only() -> None:
    """CommunicationConnector must not grow send, reply, or modify operations."""
    assert not hasattr(CommunicationConnector, "send")
    assert not hasattr(CommunicationConnector, "reply")
    assert not hasattr(CommunicationConnector, "modify")
    assert not hasattr(CommunicationConnector, "delete")
    assert not hasattr(CommunicationConnector, "execute")
    assert hasattr(CommunicationConnector, "list_messages")
    assert hasattr(CommunicationConnector, "fetch_message")
