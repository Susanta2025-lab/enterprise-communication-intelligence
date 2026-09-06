"""Domain-level input and output schemas for communication analysis."""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    AIImageInput,
    AttachmentTextSection,
    CommunicationAnalysis,
    CommunicationMessage,
)


class CommunicationRequest(BaseModel):
    """Business input required to analyze a communication.

    ``attachment_texts`` and ``attachment_images`` are untrusted data sections.
    They are never system or developer instructions. Existing email-only
    callers omit both lists and keep the prior analysis contract.
    """

    model_config = ConfigDict(extra="forbid")

    message: CommunicationMessage
    include_draft_reply: bool = True
    include_action_items: bool = True
    attachment_texts: list[AttachmentTextSection] = Field(default_factory=list)
    attachment_images: list[AIImageInput] = Field(default_factory=list)


class CommunicationAnalysisResult(BaseModel):
    """Business output produced by communication analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis: CommunicationAnalysis
    provider: str | None = Field(
        default=None,
        description="Opaque provider identifier that produced the analysis.",
    )
