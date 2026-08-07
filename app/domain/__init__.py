"""Provider-independent communication domain for ECI Platform."""

from app.domain.enums import MessageCategory, PriorityLevel, SourceType
from app.domain.interfaces import AIProvider
from app.domain.models import (
    ActionItem,
    CommunicationAnalysis,
    CommunicationMessage,
    DraftReply,
    MessageMetadata,
    Priority,
    Summary,
)
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest

__all__ = [
    "AIProvider",
    "ActionItem",
    "CommunicationAnalysis",
    "CommunicationAnalysisResult",
    "CommunicationMessage",
    "CommunicationRequest",
    "DraftReply",
    "MessageCategory",
    "MessageMetadata",
    "Priority",
    "PriorityLevel",
    "SourceType",
    "Summary",
]
