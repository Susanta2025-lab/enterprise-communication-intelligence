"""SQLAlchemy-free attachment-analysis persistence contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NewAttachmentAnalysis:
    """Persistence-neutral input for storing a successful attachment analysis."""

    user_id: UUID
    connector_account_id: UUID
    provider_message_id: str
    provider_attachment_id: str
    media_type: str
    kind: str
    extracted_content_status: str
    truncated: bool
    warnings: list[str]
    summary_text: str
    priority: str
    category: str
    action_items: list[dict[str, Any]]
    provider: str
    filename: str = ""
    reported_size: int | None = None
    page_count: int | None = None
    character_count: int | None = None
    summary_confidence: float | None = None
    request_id: UUID | None = None
    attachment_analysis_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AttachmentAnalysisRecord:
    """Persistence-neutral stored attachment analysis owned by a user.

    Distinct from ``AnalysisRecord``. This id is never a valid
    ``workflow_actions.analysis_id`` source.
    """

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    connector_account_id: UUID
    provider_message_id: str
    provider_attachment_id: str
    filename: str
    media_type: str
    kind: str
    extracted_content_status: str
    truncated: bool
    warnings: list[str]
    reported_size: int | None
    page_count: int | None
    character_count: int | None
    summary_text: str
    summary_confidence: float | None
    priority: str
    category: str
    action_items: list[dict[str, Any]]
    provider: str
    request_id: UUID | None


class AttachmentAnalysisRepository(ABC):
    """Store and retrieve attachment analyses with ownership in every query."""

    @abstractmethod
    def save(self, analysis: NewAttachmentAnalysis) -> AttachmentAnalysisRecord:
        """Persist an attachment analysis for ``analysis.user_id``."""

    @abstractmethod
    def get_by_id_for_user(
        self,
        attachment_analysis_id: UUID,
        user_id: UUID,
    ) -> AttachmentAnalysisRecord | None:
        """Return the row only when it is owned by ``user_id``."""

    @abstractmethod
    def list_for_user(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
        *,
        connector_account_id: UUID | None = None,
        provider_message_id: str | None = None,
    ) -> list[AttachmentAnalysisRecord]:
        """Return a bounded page of attachment analyses owned by ``user_id``."""
