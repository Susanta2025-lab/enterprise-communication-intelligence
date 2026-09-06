"""TXT extraction tests for accepted encodings and fail-closed binaries."""

import pytest

from app.domain.attachment_policy import MAX_EXTRACTED_TEXT_CHARS
from app.domain.enums import AttachmentKind
from app.domain.exceptions import AttachmentParseError
from app.infrastructure.attachments.txt import parse_txt_attachment
from tests.unit.infrastructure.attachments.fixtures import attachment_content


def _txt(payload: bytes):
    return attachment_content(payload, filename="notes.txt", media_type="text/plain")


def test_txt_utf8() -> None:
    parsed = parse_txt_attachment(_txt(b"Plain status update"))

    assert parsed.kind is AttachmentKind.TXT
    assert parsed.extracted_text == "Plain status update"
    assert parsed.truncated is False


def test_txt_utf8_bom() -> None:
    parsed = parse_txt_attachment(_txt("\ufeffBOM note".encode("utf-8-sig")))

    assert parsed.extracted_text == "BOM note"
    assert parsed.extracted_text is not None
    assert not parsed.extracted_text.startswith("\ufeff")


def test_txt_utf16_bom() -> None:
    parsed = parse_txt_attachment(_txt("UTF16 note".encode("utf-16")))

    assert "UTF16 note" in (parsed.extracted_text or "")
    assert parsed.extracted_text is not None
    assert not parsed.extracted_text.startswith("\ufeff")


def test_txt_rejects_binary() -> None:
    with pytest.raises(AttachmentParseError):
        parse_txt_attachment(_txt(b"\x00\x01\x02\xff\xfe binary"))


def test_txt_truncates_at_output_bound() -> None:
    payload = ("C" * (MAX_EXTRACTED_TEXT_CHARS + 25)).encode()
    parsed = parse_txt_attachment(_txt(payload))

    assert parsed.truncated is True
    assert parsed.character_count == MAX_EXTRACTED_TEXT_CHARS
    assert parsed.extracted_text == "C" * MAX_EXTRACTED_TEXT_CHARS
