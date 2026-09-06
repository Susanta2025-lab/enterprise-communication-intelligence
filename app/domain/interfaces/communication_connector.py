"""Vendor-neutral contract for fetching communications from external channels."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models import AttachmentContent, AttachmentMetadata, CommunicationMessage
from app.domain.models.validation import require_non_empty_text


class ConnectorMessageQuery(BaseModel):
    """Bounded, vendor-neutral list request.

    ``cursor`` is an opaque continuation token. Application code must not
    interpret adapter pagination state.
    """

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=100)
    cursor: str | None = None

    @field_validator("cursor")
    @classmethod
    def validate_cursor(cls, value: str | None) -> str | None:
        """Reject blank continuation tokens; adapters interpret valid values."""
        if value is None:
            return None
        return require_non_empty_text(value, "cursor")


class MessagePage(BaseModel):
    """A bounded page of already-normalized communications."""

    model_config = ConfigDict(extra="forbid")

    items: list[CommunicationMessage]
    next_cursor: str | None = None

    @field_validator("next_cursor")
    @classmethod
    def validate_next_cursor(cls, value: str | None) -> str | None:
        """Reject blank continuation tokens; None remains the terminal page."""
        if value is None:
            return None
        return require_non_empty_text(value, "next_cursor")


class AttachmentMetadataPage(BaseModel):
    """Attachment metadata for one provider message. Never includes bytes."""

    model_config = ConfigDict(extra="forbid")

    items: list[AttachmentMetadata]
    truncated: bool = False


class CommunicationConnector(ABC):
    """Fetch already-normalized communications from an external channel.

    Implementations must not leak vendor SDK, HTTP, or raw source types
    through this interface. Analysis, authorization, and persistence stay
    outside the adapter.

    ``list_attachments`` is metadata-only. ``fetch_attachment_content``
    retrieves one explicitly selected attachment and is not used by list
    or message-fetch paths.
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """Opaque connector identifier, for example ``fake``."""

    @abstractmethod
    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        """Return a bounded page of normalized messages."""

    @abstractmethod
    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        """Return one normalized message by opaque provider identifier."""

    @abstractmethod
    def list_attachments(self, provider_message_id: str) -> AttachmentMetadataPage:
        """Return attachment metadata for one provider message without bytes."""

    @abstractmethod
    def fetch_attachment_content(
        self,
        provider_message_id: str,
        provider_attachment_id: str,
    ) -> AttachmentContent:
        """Return bytes for one explicitly selected attachment on one message."""
