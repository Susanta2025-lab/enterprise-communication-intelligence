"""Normalize Microsoft Graph message JSON into domain CommunicationMessage values."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import (
    ConnectorAttachmentMetadataError,
    ConnectorMessageContentError,
    ConnectorUnavailableError,
    ConnectorUnsupportedAttachmentError,
)
from app.domain.enums import AttachmentDisposition, SourceType
from app.domain.models import (
    AttachmentMetadata,
    CommunicationMessage,
    MessageMetadata,
)
from app.infrastructure.connectors.common.html_text import html_to_plain_text

_FILE_ATTACHMENT = "microsoft.graph.fileattachment"
_ITEM_ATTACHMENT = "microsoft.graph.itemattachment"
_REFERENCE_ATTACHMENT = "microsoft.graph.referenceattachment"

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


def parse_attachment_page(payload: object) -> tuple[list[object], str | None]:
    """Return raw Graph attachment resources and the raw ``@odata.nextLink``."""
    if not isinstance(payload, dict):
        raise ConnectorUnavailableError()
    if "value" not in payload:
        raise ConnectorUnavailableError()
    value = payload["value"]
    if not isinstance(value, list):
        raise ConnectorUnavailableError()
    return value, _next_cursor(payload.get(_NEXT_LINK_KEY))


def normalize_graph_attachment(item: object) -> AttachmentMetadata | None:
    """Normalize one Graph attachment resource. Fail closed for unsupported classes.

    Returns ``None`` when a file attachment is missing identifiers required for
    later retrieve. Presence of ``contentBytes`` is treated as invalid metadata.
    """
    if not isinstance(item, dict):
        raise ConnectorAttachmentMetadataError()
    if "contentBytes" in item:
        raise ConnectorAttachmentMetadataError()
    attachment_class = _graph_attachment_class(item.get("@odata.type"))
    if attachment_class == _FILE_ATTACHMENT:
        return _file_attachment_metadata(item)
    if attachment_class in {_ITEM_ATTACHMENT, _REFERENCE_ATTACHMENT}:
        raise ConnectorUnsupportedAttachmentError()
    raise ConnectorUnsupportedAttachmentError()


def _file_attachment_metadata(item: dict[str, Any]) -> AttachmentMetadata | None:
    attachment_id = _required_text(item.get("id"))
    if attachment_id is None:
        return None
    media_type = _optional_text(item.get("contentType"))
    if media_type is None:
        return None
    reported_size = _reported_size(item.get("size"))
    if reported_size is None:
        return None
    is_inline = item.get("isInline") is True
    disposition = (
        AttachmentDisposition.INLINE if is_inline else AttachmentDisposition.ATTACHMENT
    )
    filename = item.get("name")
    if filename is None:
        filename = ""
    elif not isinstance(filename, str):
        return None
    try:
        return AttachmentMetadata(
            provider_attachment_id=attachment_id,
            filename=filename,
            media_type=media_type,
            reported_size=reported_size,
            disposition=disposition,
            is_inline=is_inline,
            content_id=_optional_text(item.get("contentId")),
        )
    except ValidationError:
        return None


def _graph_attachment_class(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return value.strip().lstrip("#").lower()


def _reported_size(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


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
