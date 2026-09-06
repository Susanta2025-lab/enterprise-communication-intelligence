"""PDF text extraction tests. OCR is not used."""

import pytest

from app.domain.attachment_policy import MAX_EXTRACTED_TEXT_CHARS, MAX_PDF_PAGES
from app.domain.enums import AttachmentKind
from app.domain.exceptions import (
    AttachmentEncryptedError,
    AttachmentExceedsLimitError,
    AttachmentNoExtractableTextError,
    AttachmentParseError,
)
from app.infrastructure.attachments.pdf import parse_pdf_attachment
from tests.unit.infrastructure.attachments.fixtures import (
    attachment_content,
    pdf_blank_pages,
    pdf_encrypted,
    pdf_with_ignored_actions,
    pdf_with_text,
)


def _pdf(payload: bytes, filename: str = "report.pdf"):
    return attachment_content(payload, filename=filename, media_type="application/pdf")


def test_pdf_extracts_normal_text() -> None:
    parsed = parse_pdf_attachment(_pdf(pdf_with_text("Quarterly budget narrative")))

    assert parsed.kind is AttachmentKind.PDF
    assert parsed.extracted_text is not None
    assert "Quarterly budget narrative" in parsed.extracted_text
    assert parsed.page_count == 1
    assert parsed.truncated is False
    assert parsed.image is None


def test_pdf_extracts_multipage_text() -> None:
    parsed = parse_pdf_attachment(_pdf(pdf_with_text("Page one facts", "Page two facts")))

    assert parsed.page_count == 2
    assert "Page one facts" in (parsed.extracted_text or "")
    assert "Page two facts" in (parsed.extracted_text or "")


def test_pdf_rejects_more_than_fifty_pages() -> None:
    with pytest.raises(AttachmentExceedsLimitError):
        parse_pdf_attachment(_pdf(pdf_blank_pages(MAX_PDF_PAGES + 1)))


def test_pdf_rejects_encrypted() -> None:
    with pytest.raises(AttachmentEncryptedError):
        parse_pdf_attachment(_pdf(pdf_encrypted()))


def test_pdf_rejects_malformed() -> None:
    with pytest.raises(AttachmentParseError):
        parse_pdf_attachment(_pdf(b"%PDF-1.4\nthis is not a valid document\n"))


def test_pdf_image_only_has_no_extractable_text() -> None:
    with pytest.raises(AttachmentNoExtractableTextError):
        parse_pdf_attachment(_pdf(pdf_blank_pages(1)))


def test_pdf_ignores_javascript_and_launch_actions() -> None:
    parsed = parse_pdf_attachment(_pdf(pdf_with_ignored_actions("Visible contract text")))

    assert "Visible contract text" in (parsed.extracted_text or "")
    assert "pdf_javascript_ignored" in parsed.warnings
    assert "pdf_launch_ignored" in parsed.warnings


def test_pdf_truncates_extracted_text_at_bound() -> None:
    huge = "A" * (MAX_EXTRACTED_TEXT_CHARS + 50)
    parsed = parse_pdf_attachment(_pdf(pdf_with_text(huge)))

    assert parsed.truncated is True
    assert parsed.character_count == MAX_EXTRACTED_TEXT_CHARS
    assert parsed.extracted_text == "A" * MAX_EXTRACTED_TEXT_CHARS
