"""Unit tests for the offline fake communication connector."""

from pathlib import Path

import pytest

from app.core.exceptions import (
    ConnectorAttachmentNotFoundError,
    ConnectorInvalidCursorError,
    ConnectorMessageNotFoundError,
    ConnectorUnsupportedAttachmentError,
)
from app.domain.enums import AttachmentDisposition, SourceType
from app.domain.interfaces import (
    AttachmentMetadataPage,
    CommunicationConnector,
    ConnectorMessageQuery,
    MessagePage,
)
from app.domain.models import AttachmentContent, AttachmentMetadata, CommunicationMessage
from app.infrastructure.connectors.fake import FakeCommunicationConnector

_FAKE_ROOT = Path(__file__).resolve().parents[4] / "app" / "infrastructure" / "connectors" / "fake"
_NETWORK_MARKERS = (
    "httpx",
    "requests",
    "urllib",
    "google",
    "graph.microsoft.com",
    "gmail.googleapis.com",
    "azure",
    "boto3",
)


def test_fake_connector_implements_communication_connector() -> None:
    """The fake adapter is a CommunicationConnector."""
    connector = FakeCommunicationConnector()

    assert isinstance(connector, CommunicationConnector)
    assert connector.provider == "fake"


def test_list_messages_returns_bounded_email_items() -> None:
    """list_messages honors limit and returns normalized email messages."""
    connector = FakeCommunicationConnector()

    page = connector.list_messages(ConnectorMessageQuery(limit=2))

    assert isinstance(page, MessagePage)
    assert len(page.items) == 2
    assert page.next_cursor is not None
    for message in page.items:
        _assert_normalized_email(message)


def test_list_messages_paginates_with_opaque_cursor() -> None:
    """A next_cursor continues the catalog without exposing vendor pagination."""
    connector = FakeCommunicationConnector()
    first = connector.list_messages(ConnectorMessageQuery(limit=2))
    second = connector.list_messages(ConnectorMessageQuery(limit=2, cursor=first.next_cursor))
    third = connector.list_messages(ConnectorMessageQuery(limit=2, cursor=second.next_cursor))

    first_ids = [item.message_id for item in first.items]
    second_ids = [item.message_id for item in second.items]
    third_ids = [item.message_id for item in third.items]

    assert first.next_cursor is not None
    assert "pageToken" not in first.next_cursor
    assert "nextLink" not in first.next_cursor
    assert set(first_ids).isdisjoint(second_ids)
    assert set(second_ids).isdisjoint(third_ids)
    assert third.next_cursor is None
    assert len(first.items) + len(second.items) + len(third.items) == 5


def test_malformed_cursor_raises_connector_error() -> None:
    """Malformed fake tokens must become ConnectorInvalidCursorError, not ValueError."""
    connector = FakeCommunicationConnector()
    invalid = ("gmail-page-token", "n:", "n:-1", "n:1.5", "n:²")

    for cursor in invalid:
        with pytest.raises(ConnectorInvalidCursorError) as exc_info:
            connector.list_messages(ConnectorMessageQuery(cursor=cursor))
        assert exc_info.value.message == "Connector cursor is invalid."
        assert not isinstance(exc_info.value.__cause__, ValueError)


def test_invalid_cursor_raises_connector_error() -> None:
    """Vendor-looking tokens must not be interpreted; they fail as invalid cursors."""
    connector = FakeCommunicationConnector()

    with pytest.raises(ConnectorInvalidCursorError) as exc_info:
        connector.list_messages(ConnectorMessageQuery(cursor="gmail-page-token"))

    assert exc_info.value.message == "Connector cursor is invalid."
    assert "gmail" not in exc_info.value.message.lower()


def test_fetch_known_message_succeeds() -> None:
    """fetch_message returns the same normalized message listed in the catalog."""
    connector = FakeCommunicationConnector()
    listed = connector.list_messages(ConnectorMessageQuery(limit=1)).items[0]
    assert listed.message_id is not None

    fetched = connector.fetch_message(listed.message_id)

    assert fetched == listed
    _assert_normalized_email(fetched)


def test_cursor_past_catalog_returns_empty_page() -> None:
    """A well-formed cursor past the catalog is an empty terminal page."""
    connector = FakeCommunicationConnector()

    page = connector.list_messages(ConnectorMessageQuery(cursor="n:99"))

    assert page.items == []
    assert page.next_cursor is None


def test_returned_messages_do_not_mutate_catalog() -> None:
    """Callers must not be able to corrupt later fetches by mutating a result."""
    connector = FakeCommunicationConnector()
    first = connector.fetch_message("fake-msg-001")
    listed = connector.list_messages(ConnectorMessageQuery(limit=1)).items[0]
    first.body = "mutated-body"
    listed.body = "mutated-list-body"

    fetched = connector.fetch_message("fake-msg-001")

    assert fetched.body != "mutated-body"
    assert fetched.body != "mutated-list-body"
    assert fetched.body.startswith("Please review the Q3 budget")


def test_fetch_unknown_message_raises_not_found() -> None:
    """Unknown provider ids raise a connector-neutral not-found error."""
    connector = FakeCommunicationConnector()

    with pytest.raises(ConnectorMessageNotFoundError) as exc_info:
        connector.fetch_message("missing-message")

    assert exc_info.value.message == "Connector message not found."


def _attachment(
    attachment_id: str,
    *,
    filename: str = "report.pdf",
    is_inline: bool = False,
) -> AttachmentMetadata:
    return AttachmentMetadata(
        provider_attachment_id=attachment_id,
        filename=filename,
        media_type="application/pdf",
        reported_size=128,
        disposition=(
            AttachmentDisposition.INLINE if is_inline else AttachmentDisposition.ATTACHMENT
        ),
        is_inline=is_inline,
    )


def test_default_catalog_has_no_attachments() -> None:
    connector = FakeCommunicationConnector()

    page = connector.list_attachments("fake-msg-001")

    assert isinstance(page, AttachmentMetadataPage)
    assert page.items == []
    assert page.truncated is False


def test_fake_lists_one_and_multiple_attachment_metadata() -> None:
    connector = FakeCommunicationConnector(
        attachments={
            "fake-msg-001": (_attachment("att-1"),),
            "fake-msg-002": (_attachment("att-2"), _attachment("att-3", filename="notes.pdf")),
        }
    )

    one = connector.list_attachments("fake-msg-001")
    many = connector.list_attachments("fake-msg-002")
    none = connector.list_attachments("fake-msg-003")

    assert [item.provider_attachment_id for item in one.items] == ["att-1"]
    assert [item.provider_attachment_id for item in many.items] == ["att-2", "att-3"]
    assert none.items == []
    listed = connector.list_messages(ConnectorMessageQuery(limit=1)).items[0]
    assert listed.message_id == "fake-msg-001"
    assert "attachments" not in CommunicationMessage.model_fields


def test_fake_inline_attachment_metadata() -> None:
    connector = FakeCommunicationConnector(
        attachments={
            "fake-msg-001": (
                _attachment("att-inline", filename="logo.png", is_inline=True),
            )
        }
    )

    page = connector.list_attachments("fake-msg-001")

    assert page.items[0].is_inline is True
    assert page.items[0].disposition is AttachmentDisposition.INLINE


def test_fake_unsupported_attachment_type_fails_closed() -> None:
    connector = FakeCommunicationConnector(
        unsupported_attachment_message_ids=frozenset({"fake-msg-004"}),
        attachments={"fake-msg-004": (_attachment("att-x"),)},
    )

    with pytest.raises(ConnectorUnsupportedAttachmentError):
        connector.list_attachments("fake-msg-004")
    with pytest.raises(ConnectorUnsupportedAttachmentError):
        connector.fetch_attachment_content("fake-msg-004", "att-x")


def test_fake_missing_attachment_is_not_found() -> None:
    connector = FakeCommunicationConnector(
        attachments={"fake-msg-001": (_attachment("att-1"),)},
        attachment_contents={("fake-msg-001", "att-1"): b"%PDF-test"},
    )

    with pytest.raises(ConnectorAttachmentNotFoundError):
        connector.fetch_attachment_content("fake-msg-001", "missing")
    with pytest.raises(ConnectorMessageNotFoundError):
        connector.list_attachments("missing-message")


def test_fake_fetch_attachment_content_uses_stable_ids() -> None:
    connector = FakeCommunicationConnector(
        attachments={"fake-msg-001": (_attachment("att-stable"),)},
        attachment_contents={("fake-msg-001", "att-stable"): b"%PDF-stable"},
    )

    first = connector.list_attachments("fake-msg-001").items[0]
    content = connector.fetch_attachment_content("fake-msg-001", first.provider_attachment_id)

    assert isinstance(content, AttachmentContent)
    assert content.source_message_id == "fake-msg-001"
    assert content.source_attachment_id == "att-stable"
    assert content.content == b"%PDF-stable"
    assert content.metadata.provider_attachment_id == "att-stable"


def test_fake_attachment_metadata_does_not_mutate_catalog() -> None:
    connector = FakeCommunicationConnector(
        attachments={"fake-msg-001": (_attachment("att-1"),)}
    )
    listed = connector.list_attachments("fake-msg-001").items[0]
    listed.filename = "mutated.pdf"

    again = connector.list_attachments("fake-msg-001").items[0]
    assert again.filename == "report.pdf"


def test_fake_connector_source_is_offline() -> None:
    """Phase 10A fake adapter code must not call vendor or HTTP clients."""
    for path in _FAKE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for marker in _NETWORK_MARKERS:
            assert marker not in source, f"{path} must remain offline ({marker})"


def _assert_normalized_email(message: CommunicationMessage) -> None:
    assert isinstance(message, CommunicationMessage)
    assert message.metadata.source_type is SourceType.EMAIL
    assert message.message_id is not None
    assert message.message_id.startswith("fake-")
    assert message.body
    assert "<html" not in message.body.lower()
    assert "<p>" not in message.body.lower()
    assert message.metadata.sender
    assert message.metadata.recipients
    assert message.metadata.subject
    assert message.metadata.sent_at is not None
    assert message.metadata.received_at is not None
