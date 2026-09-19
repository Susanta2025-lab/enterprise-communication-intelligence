"""Structured output schema for LLM BusinessContext suggestions."""

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.enums import ContextMatchStrength
from app.domain.schemas.context_suggestion import (
    BusinessContextSuggestionItem,
    BusinessContextSuggestionRequest,
    BusinessContextSuggestionResult,
)

_MAX_SUGGESTIONS = 3


class ContextSuggestionOutputError(ValueError):
    """Raised when an AI provider returns unusable suggestion output."""


class ContextSuggestionItemOutput(BaseModel):
    """One suggestion field set requested from the model."""

    model_config = ConfigDict(extra="forbid")

    business_context_id: str
    match_strength: ContextMatchStrength
    rationale: str


class ContextSuggestionOutput(BaseModel):
    """Strict JSON shape requested from an LLM suggestion provider."""

    model_config = ConfigDict(extra="forbid")

    suggestions: list[ContextSuggestionItemOutput] = Field(default_factory=list)
    no_match_reason: str | None = None


def parse_context_suggestion_output(output_text: str) -> ContextSuggestionOutput:
    """Parse and validate model output against the suggestion schema."""
    if not output_text.strip():
        raise ContextSuggestionOutputError(
            "AI provider returned an empty context suggestion response."
        )

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ContextSuggestionOutputError(
            "AI provider returned malformed JSON."
        ) from exc

    try:
        return ContextSuggestionOutput.model_validate(payload)
    except ValidationError as exc:
        raise ContextSuggestionOutputError(
            "AI provider returned JSON that does not match the suggestion schema."
        ) from exc


def to_business_context_suggestion_result(
    output: ContextSuggestionOutput,
    request: BusinessContextSuggestionRequest,
    *,
    provider: str,
) -> BusinessContextSuggestionResult:
    """Map validated LLM output onto the domain suggestion result.

    Truncates to the allowed suggestion bound. Does not validate candidate
    ownership; the application service must discard hallucinated IDs.
    """
    del request  # retained for signature parity with analysis mapping
    try:
        items: list[BusinessContextSuggestionItem] = []
        for raw in output.suggestions[:_MAX_SUGGESTIONS]:
            items.append(
                BusinessContextSuggestionItem(
                    business_context_id=raw.business_context_id,
                    match_strength=raw.match_strength,
                    rationale=raw.rationale.strip() or "Suggested match.",
                )
            )
        reason = output.no_match_reason
        if reason is not None:
            reason = reason.strip() or None
        if items:
            reason = None
        return BusinessContextSuggestionResult(
            suggestions=items,
            no_match_reason=reason,
            provider=provider,
        )
    except ValidationError as exc:
        raise ContextSuggestionOutputError(
            "AI provider returned suggestions that failed domain validation."
        ) from exc
