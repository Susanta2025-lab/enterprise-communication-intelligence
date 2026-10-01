"""Owner-scoped timeline read value; never a historical item snapshot."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.enums import ContextTimelineEventType


@dataclass(frozen=True, slots=True)
class ContextTimelineEntry:
    """One projected timeline item with a deterministic identity."""

    id: str
    type: ContextTimelineEventType
    occurred_at: datetime
    title: str
    summary: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    connector_account_id: UUID | None = None
    provider_message_id: str | None = None
