"""Normalize Gmail API JSON into domain CommunicationMessage values."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import ConnectorMessageContentError, ConnectorUnavailableError
from app.domain.enums import SourceType
from app.domain.models import CommunicationMessage, MessageMetadata
from app.infrastructure.connectors.common.html_text import html_to_plain_text

_RATE_LIMIT_REASONS = frozenset(
    {
        "quotaExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
    }
)


def normalize_gmail_message(payload: object) -> CommunicationMessage:
    """Convert one Gmail ``format=full`` resource into a CommunicationMessage."""
    if not isinstance(payload, dict):
        raise ConnectorMessageContentError()
    message_id = _required_text(payload.get("id"))
    if message_id is None:
        raise ConnectorMessageContentError()
    mime_payload = payload.get("payload")
    if not isinstance(mime_payload, dict):
        raise ConnectorMessageContentError()

    headers = _header_values(mime_payload)
    sender = _sender(headers)
    body = _plain_text_body(mime_payload)
    sent_at, received_at = _timestamps(headers, payload.get("internalDate"))
    thread_id = _optional_text(payload.get("threadId"))
    subject = _subject(headers)

    try:
        return CommunicationMessage(
            body=body,
            message_id=message_id,
            metadata=MessageMetadata(
                source_type=SourceType.EMAIL,
                sender=sender,
                recipients=_recipients(headers),
                subject=subject,
                source_id=message_id,
                thread_id=thread_id,
                sent_at=sent_at,
                received_at=received_at,
                labels=_labels(payload.get("labelIds")),
            ),
        )
    except ValidationError:
        raise ConnectorMessageContentError() from None


def parse_list_page(payload: object) -> tuple[list[str], str | None]:
    """Return listed Gmail ids and the opaque next-page token, if any."""
    if not isinstance(payload, dict):
        raise ConnectorUnavailableError()
    if "messages" not in payload:
        ids: list[str] = []
    else:
        messages = payload["messages"]
        if not isinstance(messages, list):
            raise ConnectorUnavailableError()
        ids = []
        for item in messages:
            if not isinstance(item, dict):
                raise ConnectorUnavailableError()
            message_id = _required_text(item.get("id"))
            if message_id is None:
                raise ConnectorUnavailableError()
            ids.append(message_id)
    next_cursor = payload.get("nextPageToken")
    if next_cursor is None:
        return ids, None
    if not isinstance(next_cursor, str):
        raise ConnectorUnavailableError()
    if not next_cursor.strip():
        return ids, None
    return ids, next_cursor


def gmail_rate_limit_reason(payload: object) -> bool:
    """Return True when a Gmail error object uses a known rate-limit reason."""
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    errors = error.get("errors")
    if not isinstance(errors, list):
        return False
    for item in errors:
        if not isinstance(item, dict):
            continue
        reason = item.get("reason")
        if isinstance(reason, str) and reason in _RATE_LIMIT_REASONS:
            return True
    return False


def _plain_text_body(part: dict[str, Any]) -> str:
    candidates = list(_iter_text_parts(part))
    for kind, text in candidates:
        if kind == "plain":
            return text
    for kind, text in candidates:
        if kind == "html":
            converted = html_to_plain_text(text)
            if converted:
                return converted
    raise ConnectorMessageContentError()


def _iter_text_parts(part: object) -> list[tuple[str, str]]:
    if not isinstance(part, dict) or _is_attachment(part):
        return []
    found: list[tuple[str, str]] = []
    media = _media_type(part)
    if media in {"text/plain", "text/html"}:
        text = _decode_part_text(part)
        if text.strip():
            found.append(("plain" if media == "text/plain" else "html", text))
    nested = part.get("parts")
    if isinstance(nested, list):
        for child in nested:
            found.extend(_iter_text_parts(child))
    return found


def _is_attachment(part: dict[str, Any]) -> bool:
    filename = part.get("filename")
    if isinstance(filename, str) and filename.strip():
        return True
    if _has_attachment_disposition(part):
        return True
    body = part.get("body")
    if not isinstance(body, dict):
        return False
    attachment_id = body.get("attachmentId")
    data = body.get("data")
    has_inline = isinstance(data, str) and data.strip()
    return isinstance(attachment_id, str) and bool(attachment_id.strip()) and not has_inline


def _has_attachment_disposition(part: dict[str, Any]) -> bool:
    for value in _header_values(part).get("content-disposition", []):
        disposition = value.split(";", 1)[0].strip().lower()
        if disposition == "attachment":
            return True
    return False


def _decode_part_text(part: dict[str, Any]) -> str:
    body = part.get("body")
    if not isinstance(body, dict):
        return ""
    data = body.get("data")
    if not isinstance(data, str) or not data.strip():
        return ""
    raw = _decode_base64url(data)
    return _decode_charset(raw, _declared_charset(part))


def _decode_base64url(data: str) -> bytes:
    padded = data + "=" * ((4 - len(data) % 4) % 4)
    try:
        translated = padded.encode("ascii").translate(bytes.maketrans(b"-_", b"+/"))
        return base64.b64decode(translated, validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError):
        raise ConnectorMessageContentError() from None


def _decode_charset(raw: bytes, charset: str | None) -> str:
    encoding = charset.strip() if isinstance(charset, str) and charset.strip() else "utf-8"
    try:
        return raw.decode(encoding)
    except LookupError:
        return raw.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _declared_charset(part: dict[str, Any]) -> str | None:
    for value in _header_values(part).get("content-type", []):
        charset = _charset_from_content_type(value)
        if charset:
            return charset
    mime_type = part.get("mimeType")
    if isinstance(mime_type, str):
        return _charset_from_content_type(mime_type)
    return None


def _charset_from_content_type(value: str) -> str | None:
    message = Message()
    try:
        message["Content-Type"] = value
        charset = message.get_content_charset()
    except (TypeError, ValueError, LookupError):
        return None
    if isinstance(charset, str) and charset.strip():
        return charset.strip()
    return None


def _media_type(part: dict[str, Any]) -> str:
    raw = part.get("mimeType")
    if not isinstance(raw, str):
        return ""
    return raw.split(";", 1)[0].strip().lower()


def _header_values(payload: dict[str, Any]) -> dict[str, list[str]]:
    collected: dict[str, list[str]] = {}
    headers = payload.get("headers")
    if not isinstance(headers, list):
        return collected
    for item in headers:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        collected.setdefault(name.lower(), []).append(value)
    return collected


def _first_header(headers: dict[str, list[str]], name: str) -> str | None:
    values = headers.get(name.lower())
    if not values:
        return None
    return values[0]


def _decode_rfc2047(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeDecodeError, ValueError, TypeError):
        return value
    except Exception:
        return value


def _sender(headers: dict[str, list[str]]) -> str:
    raw = _first_header(headers, "from")
    if raw is None or not raw.strip():
        raise ConnectorMessageContentError()
    _display, address = parseaddr(_decode_rfc2047(raw))
    sender = address.strip()
    if not sender:
        raise ConnectorMessageContentError()
    return sender


def _recipients(headers: dict[str, list[str]]) -> list[str]:
    chunks: list[str] = []
    for name in ("to", "cc", "bcc"):
        chunks.extend(headers.get(name, []))
    if not chunks:
        return []
    joined = ", ".join(_decode_rfc2047(chunk) for chunk in chunks)
    addresses: list[str] = []
    seen: set[str] = set()
    for _display, address in getaddresses([joined]):
        normalized = address.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        addresses.append(normalized)
    return addresses


def _subject(headers: dict[str, list[str]]) -> str | None:
    raw = _first_header(headers, "subject")
    if raw is None or not raw.strip():
        return None
    decoded = _decode_rfc2047(raw).strip()
    return decoded or None


def _timestamps(
    headers: dict[str, list[str]],
    internal_date: object,
) -> tuple[datetime | None, datetime | None]:
    received_at = _parse_internal_date(internal_date)
    sent_at = _parse_date_header(_first_header(headers, "date")) or received_at
    return sent_at, received_at


def _parse_date_header(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return _as_utc(parsed)


def _parse_internal_date(value: object) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        millis = value
    elif isinstance(value, str) and value.strip().isdigit():
        millis = int(value.strip())
    else:
        return None
    try:
        return datetime.fromtimestamp(millis / 1000, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            labels.append(item.strip())
    return labels


def _required_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
