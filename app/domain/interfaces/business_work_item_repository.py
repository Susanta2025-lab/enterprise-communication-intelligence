"""Owner-scoped aggregate persistence. No independent source/event write port."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.models.business_work_item import BusinessWorkItem, WorkItemCommand
from app.domain.models.business_work_item_event import WorkItemEvent
from app.domain.models.business_work_item_source import WorkItemSource
from app.domain.models.work_item_intent import CreationIntent
from app.domain.models.work_item_query import WorkItemQuery


@dataclass(frozen=True)
class WorkItemCreationResult:
    item: BusinessWorkItem
    replayed: bool


class BusinessWorkItemRepository(ABC):
    @abstractmethod
    def get_by_creation_key_owned(
        self, user_id: UUID, creation_key: str
    ) -> BusinessWorkItem | None:
        """Find replay before source revalidation or conflict disclosure."""

    @abstractmethod
    def list_owned(
        self, user_id: UUID, query: WorkItemQuery, now: datetime
    ) -> tuple[BusinessWorkItem, ...]:
        """Filter in SQL before deterministic bounded pagination."""

    @abstractmethod
    def create_owned(
        self, user_id: UUID, creation_key: str, intent: CreationIntent
    ) -> WorkItemCreationResult:
        """Insert aggregate, sources and created event, or safely replay owned intent."""

    @abstractmethod
    def get_owned(self, item_id: UUID, user_id: UUID) -> BusinessWorkItem | None:
        """Unknown and foreign IDs are indistinguishable."""

    @abstractmethod
    def mutate_owned(
        self, item_id: UUID, user_id: UUID, command: WorkItemCommand
    ) -> BusinessWorkItem:
        """Validate expected version including no-ops; atomically append required events."""

    @abstractmethod
    def sources_owned(self, item_id: UUID, user_id: UUID) -> tuple[WorkItemSource, ...]:
        """Retained immutable references; no provider retrieval."""

    @abstractmethod
    def events_owned(
        self, item_id: UUID, user_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> tuple[WorkItemEvent, ...]:
        """Bounded journal ordered by resulting version, ordinal, ID."""

    @abstractmethod
    def context_events_owned(
        self, context_id: UUID, user_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> tuple[WorkItemEvent, ...]:
        """Owned context-at-event query; no scan of all owner history."""
