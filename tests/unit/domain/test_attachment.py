"""Unit tests for provider-neutral attachment domain types."""

import pytest
from pydantic import ValidationError

from app.domain.enums import AttachmentDisposition, SourceType
from app.domain.models import (
    AttachmentContent,
    AttachmentMetadata,
    CommunicationMessage,
    MessageMetadata,
)


def _metadata(**overrides: object) -> AttachmentMetadata:
    payload: dict[str, object] = {
        "provider_attachment_id": "att-001",
        "filename": "report.pdf",
        "media_type": "application/pdf",
        "reported_size": 2048,
        "disposition": AttachmentDisposition.ATTACHMENT,
        "is_inline": False,
    }
    payload.update(overrides)
    return AttachmentMetadata.model_validate(payload)


def test_attachment_metadata_accepts_valid_payload() -> None:
    metadata = _metadata(content_id="<image001@example>")

    assert metadata.provider_attachment_id == "att-001"
    assert metadata.filename == "report.pdf"
    assert metadata.media_type == "application/pdf"
    assert metadata.reported_size == 2048
    assert metadata.disposition is AttachmentDisposition.ATTACHMENT
    assert metadata.is_inline is False
    assert metadata.content_id == "image001@example"


def test_attachment_metadata_strips_media_type_parameters() -> None:
    metadata = _metadata(media_type="  Application/PDF; name=report.pdf  ")

    assert metadata.media_type == "application/pdf"


def test_attachment_metadata_allows_empty_filename() -> None:
    metadata = _metadata(filename="   ")

    assert metadata.filename == ""


def test_attachment_metadata_rejects_blank_id() -> None:
    with pytest.raises(ValidationError):
        _metadata(provider_attachment_id="   ")


def test_attachment_metadata_rejects_negative_size() -> None:
    with pytest.raises(ValidationError):
        _metadata(reported_size=-1)


def test_attachment_metadata_forbids_bytes_and_provider_urls() -> None:
    with pytest.raises(ValidationError):
        AttachmentMetadata.model_validate(
            {
                "provider_attachment_id": "att-001",
                "filename": "report.pdf",
                "media_type": "application/pdf",
                "reported_size": 1,
                "content": b"secret",
            }
        )
    with pytest.raises(ValidationError):
        AttachmentMetadata.model_validate(
            {
                "provider_attachment_id": "att-001",
                "filename": "report.pdf",
                "media_type": "application/pdf",
                "reported_size": 1,
                "download_url": "https://gmail.googleapis.com/download",
            }
        )
    with pytest.raises(ValidationError):
        _metadata(disposition="gmail-part")


def test_attachment_metadata_has_no_vendor_fields() -> None:
    assert "attachmentId" not in AttachmentMetadata.model_fields
    assert "odata_type" not in AttachmentMetadata.model_fields
    assert "contentBytes" not in AttachmentMetadata.model_fields
    assert "content_bytes" not in AttachmentMetadata.model_fields
    assert "webUrl" not in AttachmentMetadata.model_fields


def test_attachment_content_keeps_bytes_off_metadata() -> None:
    metadata = _metadata()
    content = AttachmentContent(
        metadata=metadata,
        content=b"%PDF-1.4",
        source_message_id="msg-001",
        source_attachment_id="att-001",
    )

    assert content.content == b"%PDF-1.4"
    assert "content" not in AttachmentMetadata.model_fields
    assert content.source_message_id == "msg-001"
    assert content.source_attachment_id == "att-001"


def test_attachment_content_rejects_blank_source_ids() -> None:
    metadata = _metadata()
    with pytest.raises(ValidationError):
        AttachmentContent(
            metadata=metadata,
            content=b"x",
            source_message_id="   ",
            source_attachment_id="att-001",
        )
    with pytest.raises(ValidationError):
        AttachmentContent(
            metadata=metadata,
            content=b"x",
            source_message_id="msg-001",
            source_attachment_id="   ",
        )


def test_communication_message_rejects_attachment_fields() -> None:
    payload = {
        "body": "Please review the quarterly report.",
        "metadata": MessageMetadata(
            source_type=SourceType.EMAIL,
            sender="alice@example.com",
        ),
        "attachments": [_metadata().model_dump()],
    }
    with pytest.raises(ValidationError):
        CommunicationMessage.model_validate(payload)
    with pytest.raises(ValidationError):
        CommunicationMessage.model_validate({**payload, "attachments": None})
    CommunicationMessage(
        body="Please review the quarterly report.",
        metadata=MessageMetadata(
            source_type=SourceType.EMAIL,
            sender="alice@example.com",
        ),
    )
    assert "attachments" not in CommunicationMessage.model_fields
    assert "attachment_metadata" not in CommunicationMessage.model_fields
