"""Minimal, strictly typed event payloads; no historical business text."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from app.domain.enums import WorkItemEventType, WorkItemOrigin, WorkItemStatus
from app.domain.models.work_item_due import DueValue, FrozenValue
from app.domain.models.work_item_intent import canonical_json


class CreatedMetadata(FrozenValue):
    status: Literal["open"] = "open"
    due: DueValue
    creation_origin: WorkItemOrigin


class EditedMetadata(FrozenValue):
    changed_fields: tuple[Literal["title", "description", "due"], ...]
    old_due: DueValue | None = None
    new_due: DueValue | None = None

    @model_validator(mode="after")
    def valid_changes(self) -> Self:
        if not self.changed_fields or len(set(self.changed_fields)) != len(self.changed_fields):
            raise ValueError("invalid changed fields")
        has_due = "due" in self.changed_fields
        if (self.old_due is not None) != has_due or (self.new_due is not None) != has_due:
            raise ValueError("due history must accompany due changes only")
        return self


class StatusMetadata(FrozenValue):
    old_status: WorkItemStatus
    new_status: WorkItemStatus


class ContextMetadata(FrozenValue):
    from_context_id: UUID | None
    to_context_id: UUID | None

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if self.from_context_id == self.to_context_id:
            raise ValueError("context change requires distinct contexts")
        return self


class EmptyMetadata(FrozenValue):
    pass


_METADATA_TYPES = {
    WorkItemEventType.CREATED: CreatedMetadata,
    WorkItemEventType.EDITED: EditedMetadata,
    WorkItemEventType.STATUS_CHANGED: StatusMetadata,
    WorkItemEventType.ARCHIVED: EmptyMetadata,
    WorkItemEventType.RESTORED: EmptyMetadata,
    WorkItemEventType.CONTEXT_ASSOCIATED: ContextMetadata,
    WorkItemEventType.CONTEXT_DISASSOCIATED: ContextMetadata,
}


class WorkItemEvent(FrozenValue):
    id: UUID = Field(default_factory=uuid4)
    work_item_id: UUID
    owner_user_id: UUID
    actor_user_id: UUID
    event_type: WorkItemEventType
    occurred_at: datetime
    item_version: int = Field(ge=1, strict=True)
    event_ordinal: int = Field(ge=0, strict=True)
    context_at_event_id: UUID | None
    metadata: CreatedMetadata | EditedMetadata | StatusMetadata | ContextMetadata | EmptyMetadata

    @model_validator(mode="before")
    @classmethod
    def typed_metadata(cls, data):
        data = dict(data)
        if "event_type" not in data or "metadata" not in data:
            raise ValueError("event type and metadata are required")
        model = _METADATA_TYPES[WorkItemEventType(data["event_type"])]
        payload = data["metadata"]
        if isinstance(payload, FrozenValue):
            payload = payload.model_dump()
        data["metadata"] = model.model_validate(payload)
        return data

    @model_validator(mode="after")
    def event_invariants(self) -> Self:
        if self.actor_user_id != self.owner_user_id or self.occurred_at.utcoffset() is None:
            raise ValueError("invalid event actor or time")
        if len(canonical_json(self.metadata.model_dump(mode="json")).encode("utf-8")) > 8192:
            raise ValueError("event metadata exceeds 8 KiB")
        if self.event_type == WorkItemEventType.CONTEXT_ASSOCIATED:
            if (
                self.context_at_event_id is None
                or self.context_at_event_id != self.metadata.to_context_id
            ):
                raise ValueError("association event context mismatch")
        if self.event_type == WorkItemEventType.CONTEXT_DISASSOCIATED:
            if (
                self.context_at_event_id is None
                or self.context_at_event_id != self.metadata.from_context_id
            ):
                raise ValueError("disassociation event context mismatch")
        return self
