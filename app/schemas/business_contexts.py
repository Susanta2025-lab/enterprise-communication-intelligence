"""API schemas for BusinessContext CRUD, provenance association, and timeline."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.services.business_context_suggestions import (
    ContextSuggestionOutcome,
    ValidatedContextSuggestion,
)
from app.application.services.context_timeline import ContextTimelineEntry
from app.domain.enums import (
    AssociationSource,
    BusinessContextStatus,
    BusinessContextType,
    ContextMatchStrength,
    ContextTimelineEventType,
)
from app.domain.models.business_context import (
    DESCRIPTION_MAX_LENGTH,
    REFERENCE_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    BusinessContext,
)
from app.domain.models.business_context_communication_link import (
    BusinessContextCommunicationLink,
)


class BusinessContextCreateRequest(BaseModel):
    """Create an owned BusinessContext. Ownership and lifecycle are server-set."""

    model_config = ConfigDict(extra="forbid")

    type: BusinessContextType
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    reference: str | None = Field(default=None, max_length=REFERENCE_MAX_LENGTH)


class BusinessContextUpdateRequest(BaseModel):
    """Partial update of mutable fields on an active owned context.

    Omitted fields are unchanged. Explicit ``null`` clears optional
    ``description`` / ``reference``. Lifecycle and ownership fields are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    type: BusinessContextType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    reference: str | None = Field(default=None, max_length=REFERENCE_MAX_LENGTH)


class BusinessContextResponse(BaseModel):
    """Owned BusinessContext resource for the authenticated caller."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: BusinessContextType
    title: str
    description: str | None = None
    reference: str | None = None
    status: BusinessContextStatus
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BusinessContextListResponse(BaseModel):
    """Bounded page of owned BusinessContexts. Total count is omitted."""

    model_config = ConfigDict(extra="forbid")

    items: list[BusinessContextResponse]
    limit: int
    offset: int


class BusinessContextCommunicationAssociateRequest(BaseModel):
    """Associate a provider-backed message via owned connector provenance.

    There is no durable ``communications`` table; clients supply opaque
    ``(connector_account_id, provider_message_id)`` identifiers.
    """

    model_config = ConfigDict(extra="forbid")

    connector_account_id: UUID
    provider_message_id: str = Field(min_length=1, max_length=1024)
    analysis_id: UUID | None = None


class BusinessContextCommunicationLinkResponse(BaseModel):
    """Persisted provenance link metadata. No mailbox body or attachment bytes."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    business_context_id: UUID
    connector_account_id: UUID
    provider_message_id: str
    analysis_id: UUID | None = None
    associated_at: datetime
    association_source: AssociationSource


class BusinessContextCommunicationLinkListResponse(BaseModel):
    """Bounded page of provenance links for an owned context."""

    model_config = ConfigDict(extra="forbid")

    items: list[BusinessContextCommunicationLinkResponse]
    limit: int
    offset: int


class ContextTimelineEntryResponse(BaseModel):
    """One projected timeline item. No analysis payloads or attachment bytes."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: ContextTimelineEventType
    occurred_at: datetime
    title: str
    summary: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    connector_account_id: UUID | None = None
    provider_message_id: str | None = None


class ContextTimelineListResponse(BaseModel):
    """Bounded page of timeline entries for an owned context."""

    model_config = ConfigDict(extra="forbid")

    items: list[ContextTimelineEntryResponse]
    limit: int
    offset: int


class BusinessContextSuggestionRequestBody(BaseModel):
    """Request AI context suggestions for an owned analyzed communication.

    Server selects the candidate set. Clients must not supply candidate IDs.
    Suggestions are advisory and never create association links.
    """

    model_config = ConfigDict(extra="forbid")

    connector_account_id: UUID
    provider_message_id: str = Field(min_length=1, max_length=1024)
    analysis_id: UUID


class BusinessContextSuggestionItemResponse(BaseModel):
    """One advisory suggestion. Association requires a separate explicit action."""

    model_config = ConfigDict(extra="forbid")

    business_context_id: UUID
    type: BusinessContextType
    title: str
    reference: str | None = None
    match_strength: ContextMatchStrength
    rationale: str


class BusinessContextSuggestionListResponse(BaseModel):
    """Non-authoritative suggestion payload. No ownership IDs exposed."""

    model_config = ConfigDict(extra="forbid")

    suggestions: list[BusinessContextSuggestionItemResponse]
    no_match_reason: str | None = None


def business_context_response(context: BusinessContext) -> BusinessContextResponse:
    """Map a domain BusinessContext onto the HTTP response schema."""
    return BusinessContextResponse(
        id=context.id,
        type=context.type,
        title=context.title,
        description=context.description,
        reference=context.reference,
        status=context.status,
        archived_at=context.archived_at,
        created_at=context.created_at,
        updated_at=context.updated_at,
    )


def business_context_communication_link_response(
    link: BusinessContextCommunicationLink,
) -> BusinessContextCommunicationLinkResponse:
    """Map a domain provenance link onto the HTTP response schema."""
    return BusinessContextCommunicationLinkResponse(
        id=link.id,
        business_context_id=link.business_context_id,
        connector_account_id=link.connector_account_id,
        provider_message_id=link.provider_message_id,
        analysis_id=link.analysis_id,
        associated_at=link.associated_at,
        association_source=link.association_source,
    )


def context_timeline_entry_response(
    entry: ContextTimelineEntry,
) -> ContextTimelineEntryResponse:
    """Map a projected timeline entry onto the HTTP response schema."""
    return ContextTimelineEntryResponse(
        id=entry.id,
        type=entry.type,
        occurred_at=entry.occurred_at,
        title=entry.title,
        summary=entry.summary,
        source_type=entry.source_type,
        source_id=entry.source_id,
        connector_account_id=entry.connector_account_id,
        provider_message_id=entry.provider_message_id,
    )


def business_context_suggestion_item_response(
    item: ValidatedContextSuggestion,
) -> BusinessContextSuggestionItemResponse:
    """Map a validated advisory suggestion onto the HTTP response schema."""
    return BusinessContextSuggestionItemResponse(
        business_context_id=item.business_context_id,
        type=item.type,
        title=item.title,
        reference=item.reference,
        match_strength=item.match_strength,
        rationale=item.rationale,
    )


def business_context_suggestion_list_response(
    outcome: ContextSuggestionOutcome,
) -> BusinessContextSuggestionListResponse:
    """Map a suggestion outcome onto the HTTP response schema."""
    return BusinessContextSuggestionListResponse(
        suggestions=[
            business_context_suggestion_item_response(item)
            for item in outcome.suggestions
        ],
        no_match_reason=outcome.no_match_reason,
    )
