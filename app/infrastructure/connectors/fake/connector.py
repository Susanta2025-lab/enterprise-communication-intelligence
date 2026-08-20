"""Deterministic offline CommunicationConnector for architecture and tests."""

from datetime import UTC, datetime, timedelta

from app.core.exceptions import ConnectorInvalidCursorError, ConnectorMessageNotFoundError
from app.domain.enums import SourceType
from app.domain.interfaces import CommunicationConnector, ConnectorMessageQuery, MessagePage
from app.domain.models import CommunicationMessage, MessageMetadata

_CURSOR_PREFIX = "n:"


def _synthetic_messages() -> tuple[CommunicationMessage, ...]:
    """Return a stable catalog of already-normalized synthetic email messages."""
    return (
        _email(
            message_id="fake-msg-001",
            sender="finance.bot@example.com",
            recipients=["ops.lead@example.com"],
            subject="Q3 budget review",
            body="Please review the Q3 budget proposal before Friday.",
            thread_id="fake-thread-001",
            sent_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        ),
        _email(
            message_id="fake-msg-002",
            sender="alerts.bot@example.com",
            recipients=["sre.oncall@example.com", "ops.lead@example.com"],
            subject="Incident follow-up",
            body="The overnight batch completed. Please confirm the reconciliation totals.",
            thread_id="fake-thread-002",
            sent_at=datetime(2026, 8, 1, 10, 15, tzinfo=UTC),
        ),
        _email(
            message_id="fake-msg-003",
            sender="hr.ops@example.com",
            recipients=["manager@example.com"],
            subject="Weekly staffing update",
            body="Sharing the notes from this week's staffing standup for visibility.",
            thread_id="fake-thread-003",
            sent_at=datetime(2026, 8, 2, 8, 30, tzinfo=UTC),
        ),
        _email(
            message_id="fake-msg-004",
            sender="procurement@example.com",
            recipients=["finance.bot@example.com"],
            subject="Purchase order approval",
            body="Please approve the purchase order for the replacement laptops.",
            thread_id="fake-thread-004",
            sent_at=datetime(2026, 8, 2, 14, 0, tzinfo=UTC),
        ),
        _email(
            message_id="fake-msg-005",
            sender="scheduler@example.com",
            recipients=["ops.lead@example.com"],
            subject="Schedule a follow-up",
            body="Can we schedule a follow-up meeting to close the open action items?",
            thread_id="fake-thread-005",
            sent_at=datetime(2026, 8, 3, 11, 45, tzinfo=UTC),
        ),
    )


def _email(
    *,
    message_id: str,
    sender: str,
    recipients: list[str],
    subject: str,
    body: str,
    thread_id: str,
    sent_at: datetime,
) -> CommunicationMessage:
    received_at = sent_at + timedelta(minutes=1)
    return CommunicationMessage(
        body=body,
        message_id=message_id,
        metadata=MessageMetadata(
            source_type=SourceType.EMAIL,
            sender=sender,
            recipients=recipients,
            subject=subject,
            source_id=message_id,
            thread_id=thread_id,
            sent_at=sent_at,
            received_at=received_at,
        ),
    )


class FakeCommunicationConnector(CommunicationConnector):
    """In-memory connector that returns synthetic, already-normalized messages."""

    def __init__(self, messages: tuple[CommunicationMessage, ...] | None = None) -> None:
        catalog = messages if messages is not None else _synthetic_messages()
        self._messages = tuple(message.model_copy(deep=True) for message in catalog)
        self._by_id = {
            message.message_id: message
            for message in self._messages
            if message.message_id is not None
        }

    @property
    def provider(self) -> str:
        return "fake"

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        start = self._decode_cursor(query.cursor)
        end = start + query.limit
        items = [message.model_copy(deep=True) for message in self._messages[start:end]]
        next_cursor = self._encode_cursor(end) if end < len(self._messages) else None
        return MessagePage(items=items, next_cursor=next_cursor)

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        message = self._by_id.get(provider_message_id)
        if message is None:
            raise ConnectorMessageNotFoundError()
        return message.model_copy(deep=True)

    def _decode_cursor(self, cursor: str | None) -> int:
        if cursor is None:
            return 0
        if not cursor.startswith(_CURSOR_PREFIX):
            raise ConnectorInvalidCursorError()
        rest = cursor.removeprefix(_CURSOR_PREFIX)
        if not rest.isascii() or not rest.isdigit():
            raise ConnectorInvalidCursorError()
        try:
            return int(rest)
        except ValueError:
            raise ConnectorInvalidCursorError() from None

    def _encode_cursor(self, index: int) -> str:
        return f"{_CURSOR_PREFIX}{index}"
