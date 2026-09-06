"""DOCX text extraction tests. Macros and embeddings are not executed."""

import zipfile

import pytest

from app.domain.attachment_policy import MAX_EXTRACTED_TEXT_CHARS
from app.domain.enums import AttachmentKind
from app.domain.exceptions import AttachmentParseError
from app.infrastructure.attachments.docx import parse_docx_attachment
from tests.unit.infrastructure.attachments.fixtures import (
    attachment_content,
    docx_with_external_relationship,
    docx_with_text,
    docx_with_zip_member,
)

_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx(payload: bytes):
    return attachment_content(payload, filename="note.docx", media_type=_DOCX_TYPE)


def test_docx_extracts_paragraphs() -> None:
    parsed = parse_docx_attachment(_docx(docx_with_text("First paragraph", "Second paragraph")))

    assert parsed.kind is AttachmentKind.DOCX
    assert parsed.extracted_text is not None
    assert "First paragraph" in parsed.extracted_text
    assert "Second paragraph" in parsed.extracted_text
    assert parsed.image is None


def test_docx_extracts_tables() -> None:
    parsed = parse_docx_attachment(
        _docx(docx_with_text("Intro", tables=[[["Vendor", "Amount"], ["Acme", "100"]]]))
    )

    assert parsed.extracted_text is not None
    assert "Intro" in parsed.extracted_text
    assert "Vendor" in parsed.extracted_text
    assert "Acme" in parsed.extracted_text
    assert "100" in parsed.extracted_text


def test_docx_rejects_malformed_zip() -> None:
    with pytest.raises(AttachmentParseError):
        parse_docx_attachment(_docx(b"PK\x03\x04not-a-docx"))


def test_docx_ignores_embedded_objects() -> None:
    parsed = parse_docx_attachment(
        _docx(docx_with_zip_member("word/embeddings/oleObject1.bin"))
    )

    assert "Visible paragraph" in (parsed.extracted_text or "")
    assert "docx_embedded_object_ignored" in parsed.warnings


def test_docx_does_not_follow_external_relationships() -> None:
    parsed = parse_docx_attachment(_docx(docx_with_external_relationship()))

    assert "Contract body" in (parsed.extracted_text or "")
    assert "docx_external_relationship_ignored" in parsed.warnings
    assert "evil.example" not in (parsed.extracted_text or "")


def test_docx_truncates_extracted_text_at_bound() -> None:
    huge = "B" * (MAX_EXTRACTED_TEXT_CHARS + 20)
    parsed = parse_docx_attachment(_docx(docx_with_text(huge)))

    assert parsed.truncated is True
    assert parsed.character_count == MAX_EXTRACTED_TEXT_CHARS
    assert (parsed.extracted_text or "").startswith("B")


def test_docx_structural_mismatch_is_a_parse_error() -> None:
    payload = bytearray(docx_with_text("ok"))
    buffer = __import__("io").BytesIO()
    with zipfile.ZipFile(__import__("io").BytesIO(payload), "r") as source:
        with zipfile.ZipFile(buffer, "w") as dest:
            for info in source.infolist():
                if info.filename == "word/document.xml":
                    dest.writestr(info, b"<not-xml")
                else:
                    dest.writestr(info, source.read(info.filename))
    with pytest.raises(AttachmentParseError):
        parse_docx_attachment(_docx(buffer.getvalue()))
