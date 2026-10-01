"""Explicit calendar dates and confirmed-zone instants. No midnight conversion."""

import re
from datetime import UTC, date, datetime, timezone
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


class FrozenValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    @field_validator("*")
    @classmethod
    def valid_text_encoding(cls, value):
        if isinstance(value, str):
            # Escaped JSON surrogates must not reach hashing or UTF-8 SQL storage.
            if "\x00" in value:
                raise ValueError("text cannot contain a null character")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("text must contain valid Unicode characters") from None
        return value


def confirmed_zone(value: str) -> str:
    if (
        not value
        or len(value) > 64
        or value in ("localtime", "posixrules")
        or value.startswith(("posix/", "right/"))
    ):
        raise ValueError("invalid confirmed timezone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("invalid confirmed timezone") from None
    return value


class NoDue(FrozenValue):
    kind: Literal["none"] = "none"


class DateDue(FrozenValue):
    kind: Literal["date"] = "date"
    date: date
    timezone: str

    _zone = field_validator("timezone")(confirmed_zone)

    @field_validator("date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        if type(value) is date:
            return value
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("date must be an ISO calendar date")
        return date.fromisoformat(value)


class TimedDue(FrozenValue):
    kind: Literal["datetime"] = "datetime"
    at: datetime
    timezone: str

    _zone = field_validator("timezone")(confirmed_zone)

    @field_validator("at", mode="before")
    @classmethod
    def rfc3339(cls, value):
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[Zz]|[+-]\d{2}:\d{2})",
            value,
        ):
            raise ValueError("at must be an aware RFC 3339 datetime")
        return datetime.fromisoformat(value.upper().replace("Z", "+00:00"))

    @model_validator(mode="after")
    def valid_wall_time(self) -> Self:
        if self.at.utcoffset() is None:
            raise ValueError("at must be aware")
        try:
            # A valid wall value must also be representable as the stored UTC instant.
            self.at.astimezone(UTC)
            local = self.at.astimezone(ZoneInfo(self.timezone))
        except OverflowError:
            raise ValueError("due instant is outside the supported calendar range") from None
        if (
            local.replace(tzinfo=None) != self.at.replace(tzinfo=None)
            or local.utcoffset() != self.at.utcoffset()
        ):
            raise ValueError("nonexistent time or offset/timezone mismatch")
        # Fixed offsets preserve the selected fold and stable equality after storage.
        object.__setattr__(self, "at", self.at.astimezone(timezone(self.at.utcoffset())))
        return self


DueValue = Annotated[NoDue | DateDue | TimedDue, Field(discriminator="kind")]
DUE_ADAPTER = TypeAdapter(DueValue)


def due_json(due: DueValue) -> dict:
    """Canonical intent representation; exact date, UTC instant, confirmed zone."""
    result = due.model_dump(mode="json")
    if isinstance(due, TimedDue):
        result["at"] = (
            due.at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
    return result


def stored_due(data: dict) -> DueValue:
    """Reconstitute a trusted UTC persisted instant in its confirmed zone."""
    data = dict(data)
    if data.get("kind") == "datetime":
        instant = data["at"]
        if isinstance(instant, str):
            instant = datetime.fromisoformat(instant.replace("Z", "+00:00"))
        if instant.tzinfo is None:  # SQLite stores UTC timestamps without an offset.
            instant = instant.replace(tzinfo=UTC)
        data["at"] = instant.astimezone(ZoneInfo(confirmed_zone(data["timezone"])))
    return DUE_ADAPTER.validate_python(data)
