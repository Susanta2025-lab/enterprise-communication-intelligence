"""Validated typed filters shared by HTTP and persistence."""

from datetime import UTC, date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.enums import WorkItemKind, WorkItemStatus
from app.domain.models.work_item_due import DateDue, FrozenValue, TimedDue


class WorkItemQuery(FrozenValue):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    kind: WorkItemKind | None = None
    status: WorkItemStatus | None = None
    archive: Literal["active", "archived", "all"] = "active"
    business_context_id: UUID | None = None
    unassociated: bool = False
    due_kind: Literal["none", "date", "datetime"] | None = None
    due_date_from: date | None = None
    due_date_to: date | None = None
    due_at_from: datetime | None = None
    due_at_to: datetime | None = None
    overdue: bool | None = None
    sort: Literal["created_desc", "due_asc"] = "created_desc"

    @field_validator("due_date_from", "due_date_to", mode="before")
    @classmethod
    def dates(cls, value):
        return DateDue.calendar_date(value) if value is not None else None

    @field_validator("due_at_from", "due_at_to", mode="before")
    @classmethod
    def instants(cls, value):
        if value is None:
            return None
        value = TimedDue.rfc3339(value)
        if value.utcoffset() is None:
            raise ValueError("range instant must be aware")
        try:
            return value.astimezone(UTC)
        except OverflowError:
            raise ValueError("range instant is outside the supported calendar range") from None

    @model_validator(mode="after")
    def combinations(self) -> Self:
        if self.business_context_id and self.unassociated:
            raise ValueError("context and unassociated are mutually exclusive")
        date_range = self.due_date_from is not None or self.due_date_to is not None
        time_range = self.due_at_from is not None or self.due_at_to is not None
        if date_range and time_range:
            raise ValueError("mixed due ranges")
        mode = "date" if date_range else "datetime" if time_range else None
        if mode and self.due_kind not in (None, mode):
            raise ValueError("range does not match due kind")
        for lower, upper in (
            (self.due_date_from, self.due_date_to),
            (self.due_at_from, self.due_at_to),
        ):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError("reversed due range")
        if self.sort == "due_asc" and self.due_kind not in ("date", "datetime"):
            raise ValueError("due sorting requires explicit date or datetime kind")
        return self

    @property
    def effective_due_kind(self):
        if self.due_date_from is not None or self.due_date_to is not None:
            return "date"
        if self.due_at_from is not None or self.due_at_to is not None:
            return "datetime"
        return self.due_kind
