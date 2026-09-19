"""Domain model for BusinessContext ↔ provider-message provenance links."""

from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.domain.enums import AssociationSource
from app.domain.models.validation import require_non_empty_text

_REHYDRATE_CONTEXT_KEY = "rehydrate"


class BusinessContextCommunicationLink(BaseModel):
    """Authoritative many-to-many provenance association.

    Identifies a provider-backed mailbox message by owned connector provenance
    ``(connector_account_id, provider_message_id)``. Does not store message
    bodies, subjects, attachment bytes, or analysis payloads. There is no
    durable ``communications`` table.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    business_context_id: UUID
    owner_user_id: UUID
    connector_account_id: UUID
    provider_message_id: str
    associated_by_user_id: UUID
    associated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    association_source: AssociationSource = AssociationSource.MANUAL
    analysis_id: UUID | None = None

    @field_validator("provider_message_id")
    @classmethod
    def validate_provider_message_id(cls, value: str) -> str:
        """Require a non-empty opaque provider message id after trim."""
        return require_non_empty_text(value, "provider_message_id")

    @model_validator(mode="after")
    def validate_ownership_and_source(self, info: ValidationInfo) -> Self:
        """Enforce Phase 20 ownership and association-source invariants."""
        if self.associated_by_user_id != self.owner_user_id:
            raise ValueError(
                "associated_by_user_id must equal owner_user_id for Phase 20"
            )
        rehydrate = bool(info.context and info.context.get(_REHYDRATE_CONTEXT_KEY))
        if not rehydrate and self.association_source is not AssociationSource.MANUAL:
            raise ValueError("Phase 20 associations must use association_source=manual")
        if self.association_source is not AssociationSource.MANUAL:
            raise ValueError("unsupported association_source")
        return self

    @classmethod
    def rehydrate(cls, **data: Any) -> Self:
        """Reconstruct a persisted provenance link."""
        return cls.model_validate(data, context={_REHYDRATE_CONTEXT_KEY: True})
