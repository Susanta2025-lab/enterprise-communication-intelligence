"""Domain models for communication analysis outputs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import MessageCategory, PriorityLevel
from app.domain.models.validation import require_non_empty_text


class Summary(BaseModel):
    """Concise summary of a communication."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject empty summary text."""
        return require_non_empty_text(value, "text")


class Priority(BaseModel):
    """Priority classification for a communication."""

    model_config = ConfigDict(extra="forbid")

    level: PriorityLevel
    rationale: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str | None) -> str | None:
        """Normalize optional rationale text."""
        if value is None:
            return None
        return require_non_empty_text(value, "rationale")


class ActionItem(BaseModel):
    """An actionable follow-up extracted from a communication."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    owner: str | None = None
    due_at: datetime | None = None
    priority: PriorityLevel | None = None

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        """Reject empty action-item descriptions."""
        return require_non_empty_text(value, "description")

    @field_validator("owner")
    @classmethod
    def validate_owner(cls, value: str | None) -> str | None:
        """Normalize optional owner identity."""
        if value is None:
            return None
        return require_non_empty_text(value, "owner")


class DraftReply(BaseModel):
    """Suggested reply content for a communication."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)
    tone: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        """Reject empty draft reply bodies."""
        return require_non_empty_text(value, "body")

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, value: str | None) -> str | None:
        """Normalize optional tone descriptors."""
        if value is None:
            return None
        return require_non_empty_text(value, "tone")


class CommunicationAnalysis(BaseModel):
    """Structured analysis produced for a communication message."""

    model_config = ConfigDict(extra="forbid")

    summary: Summary
    priority: Priority
    category: MessageCategory = MessageCategory.GENERAL
    action_items: list[ActionItem] = Field(default_factory=list)
    draft_reply: DraftReply | None = None
    message_id: str | None = None

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, value: str | None) -> str | None:
        """Normalize optional analyzed message identifiers."""
        if value is None:
            return None
        return require_non_empty_text(value, "message_id")
