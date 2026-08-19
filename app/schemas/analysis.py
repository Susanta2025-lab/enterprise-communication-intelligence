"""API schemas for communication analysis and history responses."""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from app.domain.enums import MessageCategory, SourceType
from app.domain.interfaces.analysis_repository import AnalysisRecord
from app.domain.models import ActionItem, DraftReply, Priority, Summary
from app.domain.schemas import CommunicationAnalysisResult


class CommunicationAnalysisResponse(CommunicationAnalysisResult):
    """Analyze API response with an optional persisted analysis resource id."""

    analysis_id: UUID | None = Field(
        default=None,
        description="Persisted analysis identifier when history storage succeeded.",
    )

    @model_serializer(mode="wrap")
    def _omit_null_analysis_id(self, serializer: SerializerFunctionWrapHandler) -> dict:
        data = serializer(self)
        if data.get("analysis_id") is None:
            data.pop("analysis_id", None)
        return data


class AnalysisHistoryItem(BaseModel):
    """Owned analysis history resource. Does not include identity or raw content."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID
    created_at: datetime
    request_id: UUID | None = None
    provider: str | None = None
    source_type: SourceType
    message_id: str | None = None
    summary: Summary
    priority: Priority
    category: MessageCategory
    action_items: list[ActionItem] = Field(default_factory=list)
    draft_reply: DraftReply | None = None


class AnalysisHistoryListResponse(BaseModel):
    """Bounded page of owned analyses. Total count is omitted in Phase 9B."""

    model_config = ConfigDict(extra="forbid")

    items: list[AnalysisHistoryItem]
    limit: int
    offset: int


def history_item_from_record(record: AnalysisRecord) -> AnalysisHistoryItem:
    """Map a persistence-neutral record onto the history API item."""
    return AnalysisHistoryItem(
        analysis_id=record.id,
        created_at=record.created_at,
        request_id=record.request_id,
        provider=record.provider,
        source_type=SourceType(record.source_type),
        message_id=record.message_id,
        summary=Summary(text=record.summary_text, confidence=record.summary_confidence),
        priority=Priority(level=record.priority),
        category=MessageCategory(record.category),
        action_items=[ActionItem.model_validate(item) for item in record.action_items],
        draft_reply=(
            DraftReply.model_validate(record.draft_reply)
            if record.draft_reply is not None
            else None
        ),
    )
