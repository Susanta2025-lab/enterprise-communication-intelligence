"""Bounded text extraction for already-validated PDF attachments."""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from app.domain.attachment_policy import MAX_EXTRACTED_TEXT_CHARS, MAX_PDF_PAGES
from app.domain.enums import AttachmentKind
from app.domain.exceptions import (
    AttachmentEncryptedError,
    AttachmentExceedsLimitError,
    AttachmentNoExtractableTextError,
    AttachmentParseError,
)
from app.domain.models.attachment import AttachmentContent, ParsedAttachment

_PDF_WARNING_MARKERS: tuple[tuple[bytes, str], ...] = (
    (b"/JS", "pdf_javascript_ignored"),
    (b"/JavaScript", "pdf_javascript_ignored"),
    (b"/Launch", "pdf_launch_ignored"),
    (b"/EmbeddedFile", "pdf_embedded_file_ignored"),
    (b"/GoToR", "pdf_external_link_ignored"),
    (b"/URI", "pdf_external_link_ignored"),
)


def parse_pdf_attachment(content: AttachmentContent) -> ParsedAttachment:
    """Extract text from a text-based PDF. OCR is not performed."""
    payload = content.content
    try:
        reader = PdfReader(io.BytesIO(payload), strict=False)
    except (PdfReadError, PdfStreamError, ValueError, OSError) as exc:
        raise AttachmentParseError() from exc

    if getattr(reader, "is_encrypted", False):
        raise AttachmentEncryptedError()

    try:
        page_count = len(reader.pages)
    except (PdfReadError, PdfStreamError, ValueError) as exc:
        raise AttachmentParseError() from exc

    if page_count > MAX_PDF_PAGES:
        raise AttachmentExceedsLimitError()

    collected: list[str] = []
    used = 0
    truncated = False
    try:
        for page in reader.pages:
            piece = page.extract_text() or ""
            if not piece:
                continue
            remaining = MAX_EXTRACTED_TEXT_CHARS - used
            if remaining <= 0:
                truncated = True
                break
            if len(piece) > remaining:
                collected.append(piece[:remaining])
                used += remaining
                truncated = True
                break
            collected.append(piece)
            used += len(piece)
    except (PdfReadError, PdfStreamError, ValueError) as exc:
        raise AttachmentParseError() from exc

    text = _normalize_extracted_text("\n".join(collected))
    if not text:
        raise AttachmentNoExtractableTextError()

    return ParsedAttachment(
        kind=AttachmentKind.PDF,
        media_type="application/pdf",
        extracted_text=text,
        page_count=page_count,
        character_count=len(text),
        truncated=truncated,
        warnings=_pdf_structure_warnings(payload),
    )


def _normalize_extracted_text(text: str) -> str:
    normalized = text.replace("\x00", "")
    lines = [line.rstrip() for line in normalized.splitlines()]
    return "\n".join(lines).strip()


def _pdf_structure_warnings(payload: bytes) -> tuple[str, ...]:
    warnings: list[str] = []
    seen: set[str] = set()
    for marker, warning in _PDF_WARNING_MARKERS:
        if marker in payload and warning not in seen:
            seen.add(warning)
            warnings.append(warning)
    return tuple(warnings)
