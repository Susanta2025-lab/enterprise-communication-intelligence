"""Owned tracking aggregate. Completion records a user declaration only."""

from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from app.domain.enums import WorkItemEventType, WorkItemKind, WorkItemOrigin, WorkItemStatus
from app.domain.exceptions import WorkItemConflictError, WorkItemNotFoundError
from app.domain.models.business_work_item_event import WorkItemEvent
from app.domain.models.business_work_item_source import validate_digest
from app.domain.models.work_item_due import DateDue, DueValue, FrozenValue, NoDue, TimedDue
from app.domain.models.work_item_intent import (
    CreationIntent,
    description_text,
    origin_candidate_key,
    title_text,
    validate_creation_key,
)

ACTIVE = (WorkItemStatus.OPEN, WorkItemStatus.IN_PROGRESS)


class WorkItemEdit(FrozenValue):
    title: str | None = None
    description: str | None = None
    due: DueValue | None = None
    business_context_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def title_value(cls, value):
        if value is None:
            raise ValueError("title cannot be null")
        return title_text(value)

    _description = field_validator("description")(description_text)

    @field_validator("due")
    @classmethod
    def due_value(cls, value):
        if value is None:
            raise ValueError("due cannot be null")
        return value


class WorkItemCommand(FrozenValue):
    operation: Literal["edit", "status", "archive", "restore"]
    expected_version: int = Field(ge=1, strict=True)
    edit: WorkItemEdit | None = None
    status: WorkItemStatus | None = None
    reopen: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (
            (self.operation == "edit") != (self.edit is not None)
            or (self.operation == "status") != (self.status is not None)
            or (self.reopen and self.operation != "status")
        ):
            raise ValueError("invalid mutation command")
        return self


class BusinessWorkItem(FrozenValue):
    id: UUID
    owner_user_id: UUID
    kind: WorkItemKind
    title: str
    description: str | None = None
    business_context_id: UUID | None = None
    due: DueValue = NoDue()
    status: WorkItemStatus = WorkItemStatus.OPEN
    version: int = Field(default=1, ge=1, strict=True)
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    creation_origin: WorkItemOrigin
    confirmed_by_user_id: UUID | None = None
    confirmed_at: datetime | None = None
    creation_key: str
    creation_request_hash: str
    origin_candidate_key: str | None = None

    _title = field_validator("title")(title_text)
    _description = field_validator("description")(description_text)
    _key = field_validator("creation_key")(validate_creation_key)
    _hash = field_validator("creation_request_hash")(validate_digest)

    @model_validator(mode="after")
    def invariants(self) -> Self:
        if (self.status == WorkItemStatus.COMPLETED) != (self.completed_at is not None):
            raise ValueError("invalid completion timestamp")
        if (self.status == WorkItemStatus.CANCELLED) != (self.cancelled_at is not None):
            raise ValueError("invalid cancellation timestamp")
        for timestamp in (
            self.created_at,
            self.updated_at,
            self.completed_at,
            self.cancelled_at,
            self.archived_at,
            self.confirmed_at,
        ):
            if timestamp is not None and (
                timestamp.utcoffset() is None or timestamp < self.created_at
            ):
                raise ValueError("invalid server timestamp")
        confirmation = (self.confirmed_by_user_id, self.confirmed_at, self.origin_candidate_key)
        if self.creation_origin == WorkItemOrigin.MANUAL:
            if any(v is not None for v in confirmation):
                raise ValueError("manual item cannot have confirmation metadata")
        elif (
            any(v is None for v in confirmation) or self.confirmed_by_user_id != self.owner_user_id
        ):
            raise ValueError("invalid confirmation metadata")
        if self.origin_candidate_key is not None:
            validate_digest(self.origin_candidate_key)
        return self

    @classmethod
    def create(cls, owner_user_id: UUID, creation_key: str, intent: CreationIntent):
        now = datetime.now(UTC)
        item = cls(
            id=uuid4(),
            owner_user_id=owner_user_id,
            kind=intent.kind,
            title=intent.title,
            description=intent.description,
            due=intent.due,
            business_context_id=intent.business_context_id,
            creation_origin=intent.creation_origin,
            creation_key=creation_key,
            creation_request_hash=intent.request_hash(),
            origin_candidate_key=(
                origin_candidate_key(intent.origin_candidate) if intent.origin_candidate else None
            ),
            confirmed_by_user_id=owner_user_id if intent.confirmed else None,
            confirmed_at=now if intent.confirmed else None,
            created_at=now,
            updated_at=now,
        )
        event = item._event(
            WorkItemEventType.CREATED,
            0,
            item.business_context_id,
            {
                "status": "open",
                "due": item.due,
                "creation_origin": item.creation_origin,
            },
        )
        return item, (event,)

    def overdue(self, now: datetime) -> bool:
        if now.utcoffset() is None:
            raise ValueError("reference time must be aware")
        if self.archived_at or self.status not in ACTIVE:
            return False
        if isinstance(self.due, DateDue):
            return now.astimezone(ZoneInfo(self.due.timezone)).date() > self.due.date
        return isinstance(self.due, TimedDue) and now > self.due.at

    def apply(self, owner_user_id: UUID, command: WorkItemCommand):
        """Return validated next state and genuine events, or a validated no-op."""
        if owner_user_id != self.owner_user_id:
            raise WorkItemNotFoundError()
        if command.expected_version != self.version:
            raise WorkItemConflictError("work_item_version_conflict")
        op = command.operation
        if self.archived_at and op not in ("restore", "archive"):
            raise WorkItemConflictError("work_item_not_editable")
        changes = {}
        events = []
        context = self.business_context_id
        if op == "edit":
            if self.status not in ACTIVE:
                raise WorkItemConflictError("work_item_not_editable")
            patch = command.edit
            for field in sorted(patch.model_fields_set):
                value = getattr(patch, field)
                if value != getattr(self, field):
                    changes[field] = value
            details = tuple(f for f in ("title", "description", "due") if f in changes)
            if details:
                payload = {"changed_fields": details}
                if "due" in changes:
                    payload.update(old_due=self.due, new_due=changes["due"])
                events.append((WorkItemEventType.EDITED, context, payload))
            if "business_context_id" in changes:
                target = changes["business_context_id"]
                payload = {"from_context_id": context, "to_context_id": target}
                if context:
                    events.append((WorkItemEventType.CONTEXT_DISASSOCIATED, context, payload))
                if target:
                    events.append((WorkItemEventType.CONTEXT_ASSOCIATED, target, payload))
        elif op == "status":
            reopening = self.status not in ACTIVE and command.status == WorkItemStatus.OPEN
            if command.reopen != reopening or (
                self.status not in ACTIVE and command.status != self.status and not reopening
            ):
                raise WorkItemConflictError("work_item_invalid_transition")
            if command.status != self.status:
                changes["status"] = command.status
                events.append(
                    (
                        WorkItemEventType.STATUS_CHANGED,
                        context,
                        {
                            "old_status": self.status,
                            "new_status": command.status,
                        },
                    )
                )
        elif op == "archive" and self.archived_at is None:
            changes["archived_at"] = True
            events.append((WorkItemEventType.ARCHIVED, context, {}))
        elif op == "restore" and self.archived_at is not None:
            changes["archived_at"] = None
            events.append((WorkItemEventType.RESTORED, context, {}))
        if not changes:
            return self, ()
        now = datetime.now(UTC)
        if changes.get("archived_at") is True:
            changes["archived_at"] = now
        if "status" in changes:
            changes["completed_at"] = now if changes["status"] == WorkItemStatus.COMPLETED else None
            changes["cancelled_at"] = now if changes["status"] == WorkItemStatus.CANCELLED else None
        data = self.model_dump()
        data.update(changes, updated_at=now, version=self.version + 1)
        updated = BusinessWorkItem.model_validate(data)
        return updated, tuple(updated._event(t, i, c, m) for i, (t, c, m) in enumerate(events))

    def _event(self, event_type, ordinal, context, metadata):
        return WorkItemEvent(
            work_item_id=self.id,
            owner_user_id=self.owner_user_id,
            actor_user_id=self.owner_user_id,
            event_type=event_type,
            occurred_at=self.updated_at,
            item_version=self.version,
            event_ordinal=ordinal,
            context_at_event_id=context,
            metadata=metadata,
        )
