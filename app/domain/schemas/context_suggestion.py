"""Provider-neutral schemas for non-authoritative BusinessContext suggestions."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import BusinessContextType, ContextMatchStrength


class CommunicationSuggestionEvidence(BaseModel):
    """Minimal owned analysis fields used as suggestion input.

    Prefer high-level persisted analysis over raw mailbox bodies. All text is
    untrusted data for the model, not instructions.
    """

    model_config = ConfigDict(extra="forbid")

    summary_text: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=64)
    priority: str = Field(min_length=1, max_length=64)
    action_item_descriptions: list[str] = Field(default_factory=list, max_length=10)


class BusinessContextSuggestionCandidate(BaseModel):
    """Bounded owned active-context metadata supplied to the model."""

    model_config = ConfigDict(extra="forbid")

    business_context_id: UUID
    type: BusinessContextType
    title: str = Field(min_length=1, max_length=200)
    reference: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=400)


class BusinessContextSuggestionRequest(BaseModel):
    """Provider-neutral request for BusinessContext candidate matching."""

    model_config = ConfigDict(extra="forbid")

    evidence: CommunicationSuggestionEvidence
    candidates: list[BusinessContextSuggestionCandidate] = Field(max_length=50)


class BusinessContextSuggestionItem(BaseModel):
    """One non-authoritative model suggestion before application validation."""

    model_config = ConfigDict(extra="forbid")

    business_context_id: UUID
    match_strength: ContextMatchStrength
    rationale: str = Field(min_length=1, max_length=500)


class BusinessContextSuggestionResult(BaseModel):
    """Provider-neutral structured suggestion output.

    Suggestions are advisory only. They never create
    ``BusinessContextCommunicationLink`` rows.
    """

    model_config = ConfigDict(extra="forbid")

    suggestions: list[BusinessContextSuggestionItem] = Field(default_factory=list)
    no_match_reason: str | None = Field(default=None, max_length=500)
    provider: str | None = Field(
        default=None,
        description="Opaque provider identifier that produced the suggestions.",
    )
