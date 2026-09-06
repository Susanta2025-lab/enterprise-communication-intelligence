"""Provider-neutral attachment metadata and transient content types."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import AttachmentDisposition
from app.domain.models.validation import require_non_empty_text


class AttachmentMetadata(BaseModel):
    """Declared attachment facts. Never contains bytes or download URLs.

    ``filename`` is display-only and is not an authorization boundary.
    ``media_type`` and ``reported_size`` are provider-claimed and untrusted.
    """

    model_config = ConfigDict(extra="forbid")

    provider_attachment_id: str = Field(min_length=1)
    filename: str = ""
    media_type: str = Field(min_length=1)
    reported_size: int = Field(ge=0)
    disposition: AttachmentDisposition = AttachmentDisposition.UNKNOWN
    is_inline: bool = False
    content_id: str | None = None

    @field_validator("provider_attachment_id")
    @classmethod
    def validate_provider_attachment_id(cls, value: str) -> str:
        """Reject blank provider attachment identifiers."""
        return require_non_empty_text(value, "provider_attachment_id")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        """Trim display filenames. Blank remains a valid display fallback."""
        return value.strip()

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        """Normalize declared MIME to a lowercase type without parameters."""
        normalized = require_non_empty_text(value, "media_type")
        return normalized.split(";", 1)[0].strip().lower()

    @field_validator("content_id")
    @classmethod
    def validate_content_id(cls, value: str | None) -> str | None:
        """Keep optional Content-ID without surrounding angle brackets."""
        if value is None:
            return None
        normalized = value.strip()
        if normalized.startswith("<") and normalized.endswith(">") and len(normalized) >= 2:
            normalized = normalized[1:-1].strip()
        if not normalized:
            return None
        return normalized


class AttachmentContent(BaseModel):
    """Transient attachment bytes. Never persisted and never on CommunicationMessage."""

    model_config = ConfigDict(extra="forbid")

    metadata: AttachmentMetadata
    content: bytes
    source_message_id: str = Field(min_length=1)
    source_attachment_id: str = Field(min_length=1)

    @field_validator("source_message_id")
    @classmethod
    def validate_source_message_id(cls, value: str) -> str:
        """Reject blank source message identifiers."""
        return require_non_empty_text(value, "source_message_id")

    @field_validator("source_attachment_id")
    @classmethod
    def validate_source_attachment_id(cls, value: str) -> str:
        """Reject blank source attachment identifiers."""
        return require_non_empty_text(value, "source_attachment_id")
