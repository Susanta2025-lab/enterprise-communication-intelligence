"""Domain model for user-owned BusinessContext aggregates."""

from datetime import UTC, datetime
from typing import Any, Self, cast
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.domain.enums import BusinessContextStatus, BusinessContextType
from app.domain.exceptions import (
    BusinessContextNotMutableError,
    InvalidBusinessContextTransitionError,
)
from app.domain.models.validation import require_non_empty_text

TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 4000
REFERENCE_MAX_LENGTH = 128

_REHYDRATE_CONTEXT_KEY = "rehydrate"
_UNSET: object = object()


class BusinessContext(BaseModel):
    """Flat, single-user-owned organizational context (matter / case / project).

    Ownership is always the internal application ``users.id``. Email, mailbox
    identity, and Platform Owner role never authorize access. Hierarchy and
    shared tenancy are out of Phase 20 scope.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    owner_user_id: UUID
    type: BusinessContextType
    title: str
    description: str | None = None
    reference: str | None = None
    status: BusinessContextStatus = BusinessContextStatus.ACTIVE
    archived_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """Require a non-empty title within the ADR-029 length bound."""
        normalized = require_non_empty_text(value, "title")
        if len(normalized) > TITLE_MAX_LENGTH:
            raise ValueError(f"title must be at most {TITLE_MAX_LENGTH} characters")
        return normalized

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        """Normalize optional description; blank becomes absent."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > DESCRIPTION_MAX_LENGTH:
            raise ValueError(
                f"description must be at most {DESCRIPTION_MAX_LENGTH} characters"
            )
        return normalized

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str | None) -> str | None:
        """Normalize optional reference; blank becomes absent. Not unique."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > REFERENCE_MAX_LENGTH:
            raise ValueError(
                f"reference must be at most {REFERENCE_MAX_LENGTH} characters"
            )
        return normalized

    @model_validator(mode="after")
    def validate_lifecycle(self, info: ValidationInfo) -> Self:
        """Enforce active-only public construction or persisted lifecycle invariants."""
        rehydrate = bool(info.context and info.context.get(_REHYDRATE_CONTEXT_KEY))
        if not rehydrate and self.status is not BusinessContextStatus.ACTIVE:
            raise ValueError("business contexts must be created with active status")
        _validate_status_archived_at(self)
        return self

    @classmethod
    def rehydrate(cls, **data: Any) -> Self:
        """Reconstruct a persisted business context and validate its lifecycle."""
        return cls.model_validate(data, context={_REHYDRATE_CONTEXT_KEY: True})

    def apply_update(
        self,
        *,
        type: BusinessContextType | None = None,
        title: str | None = None,
        description: str | None | object = _UNSET,
        reference: str | None | object = _UNSET,
    ) -> None:
        """Mutate editable fields when the context is active.

        ``description`` and ``reference`` default to unchanged. Pass ``None``
        explicitly to clear an optional field.
        """
        if self.status is not BusinessContextStatus.ACTIVE:
            raise BusinessContextNotMutableError()
        if type is not None:
            self.type = type
        if title is not None:
            self.title = self.validate_title(title)
        if description is not _UNSET:
            self.description = self.validate_description(cast(str | None, description))
        if reference is not _UNSET:
            self.reference = self.validate_reference(cast(str | None, reference))
        self.updated_at = datetime.now(UTC)

    def archive(self) -> None:
        """Move ``ACTIVE`` → ``ARCHIVED``. Idempotent when already archived."""
        if self.status is BusinessContextStatus.ARCHIVED:
            return
        if self.status is not BusinessContextStatus.ACTIVE:
            raise InvalidBusinessContextTransitionError()
        now = datetime.now(UTC)
        self.status = BusinessContextStatus.ARCHIVED
        self.archived_at = now
        self.updated_at = now

    def restore(self) -> None:
        """Move ``ARCHIVED`` → ``ACTIVE``. Idempotent when already active."""
        if self.status is BusinessContextStatus.ACTIVE:
            return
        if self.status is not BusinessContextStatus.ARCHIVED:
            raise InvalidBusinessContextTransitionError()
        self.status = BusinessContextStatus.ACTIVE
        self.archived_at = None
        self.updated_at = datetime.now(UTC)


def _validate_status_archived_at(context: BusinessContext) -> None:
    if context.status is BusinessContextStatus.ACTIVE:
        if context.archived_at is not None:
            raise ValueError("active business contexts cannot have archived_at")
        return
    if context.status is BusinessContextStatus.ARCHIVED:
        if context.archived_at is None:
            raise ValueError("archived business contexts require archived_at")
        return
    raise ValueError("unsupported business context status")
