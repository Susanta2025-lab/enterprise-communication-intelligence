"""Provider-neutral public contract for connected mailbox read and analysis.

These schemas freeze the Phase 14 HTTP shape. Routes that perform listing or
mailbox-backed analysis are not served in Phase 14A.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.validation import require_non_empty_text

MAILBOX_MESSAGE_LIST_DEFAULT_PAGE_SIZE = 10
MAILBOX_MESSAGE_LIST_MAX_PAGE_SIZE = 100


class ConnectorAccountMessageListQuery(BaseModel):
    """Bounded mailbox-list query. ``cursor`` is opaque transport data."""

    model_config = ConfigDict(extra="forbid")

    page_size: int = Field(
        default=MAILBOX_MESSAGE_LIST_DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAILBOX_MESSAGE_LIST_MAX_PAGE_SIZE,
    )
    cursor: str | None = None

    @field_validator("cursor")
    @classmethod
    def validate_cursor(cls, value: str | None) -> str | None:
        """Reject blank continuation tokens; callers must not parse values."""
        if value is None:
            return None
        return require_non_empty_text(value, "cursor")


class ConnectorAccountMessageListItem(BaseModel):
    """Provider-neutral list metadata for selecting a mailbox message.

    Full bodies, attachments, credential locators, tokens, thread ids, and
    provider pagination URLs are not part of this contract.
    """

    model_config = ConfigDict(extra="forbid")

    provider_message_id: str
    sender: str
    subject: str | None = None
    sent_at: datetime | None = None
    received_at: datetime | None = None

    @field_validator("provider_message_id")
    @classmethod
    def validate_provider_message_id(cls, value: str) -> str:
        """Require a non-empty opaque provider identifier."""
        return require_non_empty_text(value, "provider_message_id")

    @field_validator("sender")
    @classmethod
    def validate_sender(cls, value: str) -> str:
        """Require a non-empty sender identity."""
        return require_non_empty_text(value, "sender")

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str | None) -> str | None:
        """Normalize optional subject text and reject blank strings."""
        if value is None:
            return None
        return require_non_empty_text(value, "subject")


class ConnectorAccountMessageListResponse(BaseModel):
    """Bounded mailbox-list page. ``next_cursor`` is opaque or null."""

    model_config = ConfigDict(extra="forbid")

    items: list[ConnectorAccountMessageListItem]
    next_cursor: str | None = None

    @field_validator("next_cursor")
    @classmethod
    def validate_next_cursor(cls, value: str | None) -> str | None:
        """Reject blank continuation tokens; None remains the terminal page."""
        if value is None:
            return None
        return require_non_empty_text(value, "next_cursor")


class ConnectorAccountMessageAnalyzeRequest(BaseModel):
    """Mailbox-backed analyze body. Provider identifiers stay out of the URL."""

    model_config = ConfigDict(extra="forbid")

    provider_message_id: str

    @field_validator("provider_message_id")
    @classmethod
    def validate_provider_message_id(cls, value: str) -> str:
        """Require a non-empty opaque provider identifier."""
        return require_non_empty_text(value, "provider_message_id")
