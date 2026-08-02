"""Domain-level input and output schemas for communication analysis."""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import CommunicationAnalysis, CommunicationMessage


class CommunicationRequest(BaseModel):
    """Business input required to analyze a communication."""

    model_config = ConfigDict(extra="forbid")

    message: CommunicationMessage
    include_draft_reply: bool = True
    include_action_items: bool = True


class CommunicationAnalysisResult(BaseModel):
    """Business output produced by communication analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis: CommunicationAnalysis
    provider: str | None = Field(
        default=None,
        description="Opaque provider identifier that produced the analysis.",
    )
