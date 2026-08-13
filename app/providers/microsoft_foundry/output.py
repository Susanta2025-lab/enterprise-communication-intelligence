"""Structured output schema and mapping for Microsoft Foundry responses."""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.enums import MessageCategory, PriorityLevel
from app.domain.models import (
    ActionItem,
    CommunicationAnalysis,
    DraftReply,
    Priority,
    Summary,
)
from app.domain.schemas import CommunicationRequest

_UNSUPPORTED_SCHEMA_KEYS = (
    "title",
    "default",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
)


class FoundryOutputError(ValueError):
    """Raised when Microsoft Foundry returns unusable analysis output."""


class FoundryActionItemOutput(BaseModel):
    """Action item fields requested from the model."""

    model_config = ConfigDict(extra="forbid")

    description: str
    owner: str | None
    due_at: str | None
    priority: PriorityLevel | None


class FoundryDraftReplyOutput(BaseModel):
    """Draft reply fields requested from the model."""

    model_config = ConfigDict(extra="forbid")

    body: str
    tone: str | None
    confidence: float | None


class FoundryAnalysisOutput(BaseModel):
    """Strict JSON shape requested from Microsoft Foundry."""

    model_config = ConfigDict(extra="forbid")

    summary_text: str
    summary_confidence: float | None
    priority_level: PriorityLevel
    priority_rationale: str | None
    priority_confidence: float | None
    category: MessageCategory
    action_items: list[FoundryActionItemOutput]
    draft_reply: FoundryDraftReplyOutput | None


def build_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic model into an OpenAI-strict JSON schema."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    _make_schema_strict(schema)
    for definition in definitions.values():
        if isinstance(definition, dict):
            _make_schema_strict(definition)
    if definitions:
        schema["$defs"] = definitions
    return schema


def parse_foundry_output(output_text: str) -> FoundryAnalysisOutput:
    """Parse and validate model output against the Foundry analysis schema."""
    if not output_text.strip():
        raise FoundryOutputError("Microsoft Foundry returned an empty analysis response.")

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise FoundryOutputError("Microsoft Foundry returned malformed JSON.") from exc

    try:
        return FoundryAnalysisOutput.model_validate(payload)
    except ValidationError as exc:
        raise FoundryOutputError(
            "Microsoft Foundry returned JSON that does not match the analysis schema."
        ) from exc


def to_communication_analysis(
    output: FoundryAnalysisOutput,
    request: CommunicationRequest,
) -> CommunicationAnalysis:
    """Map validated Foundry output onto the existing domain analysis model."""
    try:
        action_items: list[ActionItem] = []
        if request.include_action_items:
            action_items = [_to_action_item(item) for item in output.action_items]

        draft_reply: DraftReply | None = None
        if request.include_draft_reply and output.draft_reply is not None:
            draft_reply = DraftReply(
                body=output.draft_reply.body,
                tone=output.draft_reply.tone,
                confidence=output.draft_reply.confidence,
            )

        return CommunicationAnalysis(
            message_id=request.message.message_id,
            summary=Summary(
                text=output.summary_text,
                confidence=output.summary_confidence,
            ),
            priority=Priority(
                level=output.priority_level,
                rationale=output.priority_rationale,
                confidence=output.priority_confidence,
            ),
            category=output.category,
            action_items=action_items,
            draft_reply=draft_reply,
        )
    except FoundryOutputError:
        raise
    except ValidationError as exc:
        raise FoundryOutputError(
            "Microsoft Foundry returned analysis that failed domain validation."
        ) from exc


def _to_action_item(item: FoundryActionItemOutput) -> ActionItem:
    """Convert a Foundry action-item payload into a domain action item."""
    return ActionItem(
        description=item.description,
        owner=item.owner,
        due_at=_parse_optional_datetime(item.due_at),
        priority=item.priority,
    )


def _parse_optional_datetime(value: str | None) -> datetime | None:
    """Parse an optional ISO-8601 timestamp from the model output."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise FoundryOutputError(
            "Microsoft Foundry returned an invalid action-item due date."
        ) from exc


def _make_schema_strict(schema: dict[str, Any]) -> None:
    """Normalize a JSON schema fragment for strict structured output."""
    for key in _UNSUPPORTED_SCHEMA_KEYS:
        schema.pop(key, None)

    if "properties" in schema:
        schema["type"] = "object"
        schema["additionalProperties"] = False
        properties = schema["properties"]
        schema["required"] = list(properties)
        for subschema in properties.values():
            if isinstance(subschema, dict):
                _make_schema_strict(subschema)

    items = schema.get("items")
    if isinstance(items, dict):
        _make_schema_strict(items)

    for combinator in ("anyOf", "oneOf", "allOf"):
        for subschema in schema.get(combinator, []):
            if isinstance(subschema, dict):
                _make_schema_strict(subschema)


FOUNDRY_ANALYSIS_JSON_SCHEMA = build_strict_json_schema(FoundryAnalysisOutput)
