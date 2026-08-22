"""SQLAlchemy-free analysis persistence contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NewAnalysis:
    """Persistence-neutral input for storing an analysis result."""

    user_id: UUID
    provider: str
    priority: str
    category: str
    source_type: str
    summary_text: str
    action_items: list[dict[str, Any]]
    request_id: UUID | None = None
    message_id: str | None = None
    summary_confidence: float | None = None
    draft_reply: dict[str, Any] | None = None
    analysis_id: UUID | None = None
    connector_account_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    """Persistence-neutral stored analysis owned by a user."""

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    request_id: UUID | None
    provider: str
    priority: str
    category: str
    source_type: str
    message_id: str | None
    summary_text: str
    summary_confidence: float | None
    action_items: list[dict[str, Any]]
    draft_reply: dict[str, Any] | None
    connector_account_id: UUID | None = None


class AnalysisRepository(ABC):
    """Store and retrieve analyses with ownership enforced in every query."""

    @abstractmethod
    def save(self, analysis: NewAnalysis) -> AnalysisRecord:
        """Persist an analysis for ``analysis.user_id`` and return the stored record."""

    @abstractmethod
    def get_by_id_for_user(self, analysis_id: UUID, user_id: UUID) -> AnalysisRecord | None:
        """Return the analysis only when it is owned by ``user_id``."""

    @abstractmethod
    def list_for_user(self, user_id: UUID, limit: int, offset: int) -> list[AnalysisRecord]:
        """Return a bounded page of analyses owned by ``user_id``, newest first."""

    @abstractmethod
    def delete_for_user(self, analysis_id: UUID, user_id: UUID) -> bool:
        """Delete the analysis only when owned by ``user_id``.

        Returns:
            True when a row was deleted. False when the id is unknown or owned
            by a different user. Those cases are indistinguishable.
        """
