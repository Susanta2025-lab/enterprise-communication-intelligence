"""Unit tests for provider-neutral attachment type, size, and signature policy."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.domain.attachment_policy import (
    MAX_ATTACHMENT_CONTENT_BYTES,
    MAX_PROCESSED_ATTACHMENT_CONTENT_BYTES,
    AttachmentContentBudget,
    detect_attachment_kind,
    evaluate_attachment_content,
    evaluate_attachment_metadata,
)
from app.domain.enums import AttachmentKind
from app.domain.exceptions import (
    AttachmentContentInvalidError,
    AttachmentExceedsLimitError,
    AttachmentUnsupportedError,
)
from app.domain.models import AttachmentContent, AttachmentMetadata


def _metadata(
    *,
    filename: str = "report.pdf",
    media_type: str = "application/pdf",
    reported_size: int = 32,
    attachment_id: str = "att-1",
) -> AttachmentMetadata:
    return AttachmentMetadata(
        provider_attachment_id=attachment_id,
        filename=filename,
        media_type=media_type,
        reported_size=reported_size,
    )


def _content(payload: bytes, metadata: AttachmentMetadata | None = None) -> AttachmentContent:
    item = metadata or _metadata(reported_size=len(payload))
    return AttachmentContent(
        metadata=item,
        content=payload,
        source_message_id="msg-1",
        source_attachment_id=item.provider_attachment_id,
    )


def _docx_bytes(*, extra: dict[str, bytes] | None = None, include_vba: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
        if include_vba:
            archive.writestr("word/vbaProject.bin", b"macro")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr("readme.txt", "hello")
    return buffer.getvalue()


_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_TXT = b"Quarterly notes for the review.\n"


def test_valid_pdf_passes_metadata_and_content() -> None:
    metadata = _metadata(
        filename="report.pdf",
        media_type="application/pdf",
        reported_size=len(_PDF),
    )
    assert evaluate_attachment_metadata(metadata) is AttachmentKind.PDF
    assert evaluate_attachment_content(_content(_PDF, metadata)) is AttachmentKind.PDF


def test_valid_docx_container_shape_passes() -> None:
    payload = _docx_bytes()
    metadata = _metadata(
        filename="brief.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        reported_size=len(payload),
    )
    assert evaluate_attachment_content(_content(payload, metadata)) is AttachmentKind.DOCX


def test_valid_jpeg_and_png_and_txt_pass() -> None:
    jpeg_meta = _metadata(filename="photo.jpg", media_type="image/jpeg", reported_size=len(_JPEG))
    png_meta = _metadata(filename="logo.png", media_type="image/png", reported_size=len(_PNG))
    txt_meta = _metadata(filename="notes.txt", media_type="text/plain", reported_size=len(_TXT))
    assert evaluate_attachment_content(_content(_JPEG, jpeg_meta)) is AttachmentKind.JPEG
    assert evaluate_attachment_content(_content(_PNG, png_meta)) is AttachmentKind.PNG
    assert evaluate_attachment_content(_content(_TXT, txt_meta)) is AttachmentKind.TXT
    jpeg_meta = _metadata(filename="photo.jpeg", media_type="image/jpeg", reported_size=len(_JPEG))
    assert evaluate_attachment_metadata(jpeg_meta) is AttachmentKind.JPEG


def test_unsupported_extension_and_mime_fail_closed() -> None:
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_metadata(
            _metadata(filename="archive.zip", media_type="application/zip")
        )
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_metadata(
            _metadata(filename="report.pdf", media_type="application/octet-stream")
        )


def test_extension_mime_mismatch_fails() -> None:
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_metadata(
            _metadata(filename="report.pdf", media_type="image/png")
        )


def test_signature_mismatch_fails() -> None:
    metadata = _metadata(
        filename="report.pdf",
        media_type="application/pdf",
        reported_size=len(_PNG),
    )
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_content(_content(_PNG, metadata))


def test_arbitrary_zip_renamed_docx_fails() -> None:
    payload = _zip_bytes()
    metadata = _metadata(
        filename="brief.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        reported_size=len(payload),
    )
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_content(_content(payload, metadata))
    assert detect_attachment_kind(payload) is None


def test_docm_is_rejected() -> None:
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_metadata(
            _metadata(
                filename="macro.docm",
                media_type="application/vnd.ms-word.document.macroEnabled.12",
            )
        )


def test_docx_with_vba_project_fails() -> None:
    payload = _docx_bytes(include_vba=True)
    metadata = _metadata(
        filename="brief.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        reported_size=len(payload),
    )
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_content(_content(payload, metadata))


def test_executable_signature_fails() -> None:
    payload = b"MZ" + b"\x00" * 32
    metadata = _metadata(filename="notes.txt", media_type="text/plain", reported_size=len(payload))
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_content(_content(payload, metadata))


def test_zero_length_is_rejected() -> None:
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_metadata(_metadata(reported_size=0))
    metadata = _metadata(reported_size=1)
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_content(_content(b"", metadata))


def test_reported_over_five_mib_fails_before_bytes() -> None:
    with pytest.raises(AttachmentExceedsLimitError):
        evaluate_attachment_metadata(
            _metadata(reported_size=MAX_ATTACHMENT_CONTENT_BYTES + 1)
        )


def test_actual_over_five_mib_fails() -> None:
    payload = b"%PDF-" + b"A" * MAX_ATTACHMENT_CONTENT_BYTES
    metadata = _metadata(reported_size=len(payload))
    with pytest.raises(AttachmentExceedsLimitError):
        evaluate_attachment_content(_content(payload, metadata))


def test_actual_larger_than_reported_fails() -> None:
    metadata = _metadata(reported_size=4)
    with pytest.raises(AttachmentContentInvalidError):
        evaluate_attachment_content(_content(_PDF, metadata))


def test_binary_is_not_accepted_as_txt() -> None:
    payload = bytes(range(256))
    metadata = _metadata(filename="notes.txt", media_type="text/plain", reported_size=len(payload))
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_content(_content(payload, metadata))


def test_encrypted_pdf_marker_fails() -> None:
    payload = b"%PDF-1.4\n/Encrypt 2 0 R\n%%EOF\n"
    metadata = _metadata(reported_size=len(payload))
    with pytest.raises(AttachmentUnsupportedError):
        evaluate_attachment_content(_content(payload, metadata))


def test_session_budget_allows_two_typical_files_and_rejects_a_third() -> None:
    budget = AttachmentContentBudget()
    assert budget.limit_bytes == MAX_PROCESSED_ATTACHMENT_CONTENT_BYTES
    budget.consume(5 * 1024 * 1024)
    budget.consume(5 * 1024 * 1024)
    with pytest.raises(AttachmentExceedsLimitError):
        budget.consume(1)
    assert budget.remaining_bytes() == 0
