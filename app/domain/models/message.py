"""Domain models for inbound communication messages."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import SourceType
from app.domain.models.validation import require_non_empty_text


class MessageMetadata(BaseModel):
    """Channel-neutral metadata describing a communication."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    sender: str = Field(min_length=1)
    recipients: list[str] = Field(default_factory=list)
    subject: str | None = None
    source_id: str | None = None
    thread_id: str | None = None
    sent_at: datetime | None = None
    received_at: datetime | None = None
    labels: list[str] = Field(default_factory=list)

    @field_validator("sender")
    @classmethod
    def validate_sender(cls, value: str) -> str:
        """Ensure sender identity is present."""
        return require_non_empty_text(value, "sender")

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str | None) -> str | None:
        """Normalize optional subject text and reject blank strings."""
        if value is None:
            return None
        return require_non_empty_text(value, "subject")

    @field_validator("recipients", "labels")
    @classmethod
    def validate_text_lists(cls, values: list[str]) -> list[str]:
        """Ensure list entries are non-empty after trimming."""
        return [require_non_empty_text(item, "list item") for item in values]


class CommunicationMessage(BaseModel):
    """A single business communication awaiting or undergoing analysis."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)
    metadata: MessageMetadata
    message_id: str | None = None

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        """Reject empty communication bodies."""
        return require_non_empty_text(value, "body")

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, value: str | None) -> str | None:
        """Normalize optional message identifiers."""
        if value is None:
            return None
        return require_non_empty_text(value, "message_id")
