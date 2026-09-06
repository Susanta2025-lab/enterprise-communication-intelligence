"""Bounded plain-text extraction for already-validated TXT attachments."""

from app.domain.attachment_policy import MAX_EXTRACTED_TEXT_CHARS, decode_txt_attachment
from app.domain.enums import AttachmentKind
from app.domain.exceptions import (
    AttachmentContentInvalidError,
    AttachmentNoExtractableTextError,
    AttachmentParseError,
)
from app.domain.models.attachment import AttachmentContent, ParsedAttachment


def parse_txt_attachment(content: AttachmentContent) -> ParsedAttachment:
    """Decode accepted encodings and bound the extracted character count."""
    try:
        decoded = decode_txt_attachment(content.content)
    except AttachmentContentInvalidError as exc:
        raise AttachmentParseError() from exc

    truncated = False
    text = decoded.replace("\x00", "")
    if len(text) > MAX_EXTRACTED_TEXT_CHARS:
        text = text[:MAX_EXTRACTED_TEXT_CHARS]
        truncated = True
    if not text.strip():
        raise AttachmentNoExtractableTextError()

    return ParsedAttachment(
        kind=AttachmentKind.TXT,
        media_type="text/plain",
        extracted_text=text,
        page_count=None,
        character_count=len(text),
        truncated=truncated,
        warnings=(),
    )
