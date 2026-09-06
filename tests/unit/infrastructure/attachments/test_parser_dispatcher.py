"""SafeAttachmentParser routes by kind and does not invent a type."""

import pytest

from app.domain.enums import AttachmentKind
from app.domain.exceptions import AttachmentUnsupportedError
from app.infrastructure.attachments import SafeAttachmentParser
from tests.unit.infrastructure.attachments.fixtures import (
    attachment_content,
    pdf_with_text,
    tiny_jpeg,
)


def test_dispatcher_parses_matching_pdf_kind() -> None:
    parsed = SafeAttachmentParser().parse(
        attachment_content(
            pdf_with_text("Dispatcher text"),
            filename="report.pdf",
            media_type="application/pdf",
        ),
        AttachmentKind.PDF,
    )
    assert parsed.kind is AttachmentKind.PDF
    assert "Dispatcher text" in (parsed.extracted_text or "")


def test_dispatcher_rejects_kind_mismatch() -> None:
    with pytest.raises(AttachmentUnsupportedError):
        SafeAttachmentParser().parse(
            attachment_content(
                tiny_jpeg(),
                filename="photo.jpg",
                media_type="image/jpeg",
            ),
            AttachmentKind.PDF,
        )
