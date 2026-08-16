"""Structured output schema and mapping for LLM communication analysis."""

import json
from datetime import datetime

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


class AnalysisOutputError(ValueError):
    """Raised when an AI provider returns unusable analysis output."""


class AnalysisActionItemOutput(BaseModel):
    """Action item fields requested from the model."""

    model_config = ConfigDict(extra="forbid")

    description: str
    owner: str | None
    due_at: datetime | None
    priority: PriorityLevel | None


class AnalysisDraftReplyOutput(BaseModel):
    """Draft reply fields requested from the model."""

    model_config = ConfigDict(extra="forbid")

    body: str
    tone: str | None
    confidence: float | None


class AnalysisOutput(BaseModel):
    """Strict JSON shape requested from an LLM analysis provider."""

    model_config = ConfigDict(extra="forbid")

    summary_text: str
    summary_confidence: float | None
    priority_level: PriorityLevel
    priority_rationale: str | None
    priority_confidence: float | None
    category: MessageCategory
    action_items: list[AnalysisActionItemOutput]
    draft_reply: AnalysisDraftReplyOutput | None


def parse_analysis_output(output_text: str) -> AnalysisOutput:
    """Parse and validate model output against the analysis schema."""
    if not output_text.strip():
        raise AnalysisOutputError("AI provider returned an empty analysis response.")

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise AnalysisOutputError("AI provider returned malformed JSON.") from exc

    try:
        return AnalysisOutput.model_validate(payload)
    except ValidationError as exc:
        raise AnalysisOutputError(
            "AI provider returned JSON that does not match the analysis schema."
        ) from exc


def to_communication_analysis(
    output: AnalysisOutput,
    request: CommunicationRequest,
) -> CommunicationAnalysis:
    """Map validated LLM output onto the existing domain analysis model."""
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
    except AnalysisOutputError:
        raise
    except ValidationError as exc:
        raise AnalysisOutputError(
            "AI provider returned analysis that failed domain validation."
        ) from exc


def _to_action_item(item: AnalysisActionItemOutput) -> ActionItem:
    """Convert a structured action-item payload into a domain action item."""
    return ActionItem(
        description=item.description,
        owner=item.owner,
        due_at=item.due_at,
        priority=item.priority,
    )
