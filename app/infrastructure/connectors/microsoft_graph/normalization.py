"""Normalize Microsoft Graph message JSON into domain CommunicationMessage values."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import ConnectorMessageContentError, ConnectorUnavailableError
from app.domain.enums import SourceType
from app.domain.models import CommunicationMessage, MessageMetadata
from app.infrastructure.connectors.common.html_text import html_to_plain_text

_NEXT_LINK_KEY = "@odata.nextLink"


def normalize_graph_message(payload: object) -> CommunicationMessage:
    """Convert one Graph message resource into a CommunicationMessage.

    Sender prefers Graph ``from.emailAddress.address`` (the mailbox the message
    was sent from). When ``from`` is missing or unusable, ``sender`` is used as
    a narrow fallback for delegate/send-as scenarios. Display names are ignored.
    Graph ``bodyPreview`` is never used as a body fallback.
    """
    if not isinstance(payload, dict):
        raise ConnectorMessageContentError()
    message_id = _required_text(payload.get("id"))
    if message_id is None:
        raise ConnectorMessageContentError()

    try:
        return CommunicationMessage(
            body=_plain_text_body(payload),
            message_id=message_id,
            metadata=MessageMetadata(
                source_type=SourceType.EMAIL,
                sender=_sender(payload),
                recipients=_recipients(payload),
                subject=_subject(payload.get("subject")),
                source_id=message_id,
                thread_id=_optional_text(payload.get("conversationId")),
                sent_at=_parse_graph_datetime(payload.get("sentDateTime")),
                received_at=_parse_graph_datetime(payload.get("receivedDateTime")),
                labels=_labels(payload.get("categories")),
            ),
        )
    except ValidationError:
        raise ConnectorMessageContentError() from None


def parse_list_page(payload: object) -> tuple[list[str], str | None]:
    """Return listed Graph ids and the raw ``@odata.nextLink``, if any."""
    if not isinstance(payload, dict):
        raise ConnectorUnavailableError()
    if "value" not in payload:
        raise ConnectorUnavailableError()
    value = payload["value"]
    if not isinstance(value, list):
        raise ConnectorUnavailableError()
    ids: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            raise ConnectorUnavailableError()
        message_id = _required_text(item.get("id"))
        if message_id is None:
            raise ConnectorUnavailableError()
        ids.append(message_id)
    return ids, _next_cursor(payload.get(_NEXT_LINK_KEY))


def _plain_text_body(payload: dict[str, Any]) -> str:
    body = payload.get("body")
    if not isinstance(body, dict):
        raise ConnectorMessageContentError()
    content_type = body.get("contentType")
    content = body.get("content")
    if not isinstance(content_type, str) or not content_type.strip():
        raise ConnectorMessageContentError()
    if not isinstance(content, str):
        raise ConnectorMessageContentError()
    kind = content_type.strip().lower()
    if kind == "text":
        if not content.strip():
            raise ConnectorMessageContentError()
        return content
    if kind == "html":
        converted = html_to_plain_text(content)
        if not converted:
            raise ConnectorMessageContentError()
        return converted
    raise ConnectorMessageContentError()


def _sender(payload: dict[str, Any]) -> str:
    address = _email_address(payload.get("from"))
    if address is None:
        address = _email_address(payload.get("sender"))
    if address is None:
        raise ConnectorMessageContentError()
    return address


def _recipients(payload: dict[str, Any]) -> list[str]:
    addresses: list[str] = []
    seen: set[str] = set()
    for key in ("toRecipients", "ccRecipients", "bccRecipients"):
        entries = payload.get(key)
        if not isinstance(entries, list):
            continue
        for item in entries:
            address = _email_address(item)
            if address is None or address in seen:
                continue
            seen.add(address)
            addresses.append(address)
    return addresses


def _email_address(recipient: object) -> str | None:
    if not isinstance(recipient, dict):
        return None
    email = recipient.get("emailAddress")
    if not isinstance(email, dict):
        return None
    return _required_text(email.get("address"))


def _subject(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _optional_text(value)


def _labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            labels.append(item.strip())
    return labels


def _parse_graph_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    text = _cap_fractional_seconds(text)
    try:
        parsed = datetime.fromisoformat(text)
    except (ValueError, OverflowError, OSError):
        return None
    return _as_utc(parsed)


def _cap_fractional_seconds(text: str) -> str:
    """Keep at most six fractional digits so datetime.fromisoformat can parse Graph values."""
    if "." not in text:
        return text
    head, rest = text.split(".", 1)
    digits: list[str] = []
    index = 0
    while index < len(rest) and rest[index].isdigit():
        digits.append(rest[index])
        index += 1
    if not digits:
        return text
    return f"{head}.{''.join(digits)[:6]}{rest[index:]}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _next_cursor(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConnectorUnavailableError()
    if not value.strip():
        return None
    return value


def _required_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
