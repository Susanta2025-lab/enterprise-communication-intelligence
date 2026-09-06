"""Public schemas for attachment analysis and history."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import (
    AttachmentDisposition,
    AttachmentExtractedContentStatus,
    AttachmentKind,
    MessageCategory,
)
from app.domain.interfaces.attachment_analysis_repository import AttachmentAnalysisRecord
from app.domain.models import ActionItem, Priority, Summary
from app.domain.models.validation import require_non_empty_text


class ConnectorAccountAttachmentListQuery(BaseModel):
    """Metadata-only attachment list for one provider message."""

    model_config = ConfigDict(extra="forbid")

    provider_message_id: str

    @field_validator("provider_message_id")
    @classmethod
    def validate_provider_message_id(cls, value: str) -> str:
        """Require a non-empty opaque provider message identifier."""
        return require_non_empty_text(value, "provider_message_id")


class ConnectorAccountAttachmentListItem(BaseModel):
    """Public attachment metadata. Never includes bytes, URLs, or Content-ID."""

    model_config = ConfigDict(extra="forbid")

    provider_attachment_id: str
    filename: str = ""
    media_type: str
    reported_size: int = Field(ge=0)
    is_inline: bool = False
    disposition: AttachmentDisposition = AttachmentDisposition.UNKNOWN


class ConnectorAccountAttachmentListResponse(BaseModel):
    """Bounded attachment-metadata page for one owned mailbox message."""

    model_config = ConfigDict(extra="forbid")

    items: list[ConnectorAccountAttachmentListItem]
    truncated: bool = False


class ConnectorAccountAttachmentAnalyzeRequest(BaseModel):
    """Explicit analyze body for one provider attachment on one message."""

    model_config = ConfigDict(extra="forbid")

    provider_message_id: str
    provider_attachment_id: str

    @field_validator("provider_message_id")
    @classmethod
    def validate_provider_message_id(cls, value: str) -> str:
        """Require a non-empty opaque provider message identifier."""
        return require_non_empty_text(value, "provider_message_id")

    @field_validator("provider_attachment_id")
    @classmethod
    def validate_provider_attachment_id(cls, value: str) -> str:
        """Require a non-empty opaque provider attachment identifier."""
        return require_non_empty_text(value, "provider_attachment_id")


class AttachmentAnalysisResponse(BaseModel):
    """Structured attachment-analysis result. Never includes bytes or extracted text.

    ``attachment_analysis_id`` is distinct from email ``analysis_id`` and is
    not accepted by workflow Propose/Approve/Execute/Send routes.
    """

    model_config = ConfigDict(extra="forbid")

    attachment_analysis_id: UUID
    created_at: datetime
    connector_account_id: UUID
    provider_message_id: str
    provider_attachment_id: str
    filename: str = ""
    media_type: str
    kind: AttachmentKind
    extracted_content_status: AttachmentExtractedContentStatus
    truncated: bool
    warnings: list[str] = Field(default_factory=list)
    page_count: int | None = None
    summary: Summary
    priority: Priority
    category: MessageCategory
    action_items: list[ActionItem] = Field(default_factory=list)
    provider: str | None = None


class AttachmentAnalysisListResponse(BaseModel):
    """Bounded page of owned attachment analyses."""

    model_config = ConfigDict(extra="forbid")

    items: list[AttachmentAnalysisResponse]
    limit: int
    offset: int


def attachment_analysis_from_record(record: AttachmentAnalysisRecord) -> AttachmentAnalysisResponse:
    """Map a persistence-neutral record onto the public attachment-analysis item."""
    return AttachmentAnalysisResponse(
        attachment_analysis_id=record.id,
        created_at=record.created_at,
        connector_account_id=record.connector_account_id,
        provider_message_id=record.provider_message_id,
        provider_attachment_id=record.provider_attachment_id,
        filename=record.filename,
        media_type=record.media_type,
        kind=AttachmentKind(record.kind),
        extracted_content_status=AttachmentExtractedContentStatus(
            record.extracted_content_status
        ),
        truncated=record.truncated,
        warnings=list(record.warnings),
        page_count=record.page_count,
        summary=Summary(text=record.summary_text, confidence=record.summary_confidence),
        priority=Priority(level=record.priority),
        category=MessageCategory(record.category),
        action_items=[ActionItem.model_validate(item) for item in record.action_items],
        provider=record.provider,
    )
