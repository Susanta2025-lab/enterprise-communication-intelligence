"""Provider-independent communication domain for ECI Platform."""

from app.domain.enums import (
    MessageCategory,
    PriorityLevel,
    SourceType,
    WorkflowActionStatus,
    WorkflowActionType,
)
from app.domain.exceptions import InvalidWorkflowTransitionError
from app.domain.interfaces import AIProvider, CommunicationConnector
from app.domain.models import (
    ActionItem,
    CommunicationAnalysis,
    CommunicationMessage,
    DraftReply,
    MessageMetadata,
    Priority,
    Summary,
    WorkflowAction,
)
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest

__all__ = [
    "AIProvider",
    "ActionItem",
    "CommunicationAnalysis",
    "CommunicationAnalysisResult",
    "CommunicationConnector",
    "CommunicationMessage",
    "CommunicationRequest",
    "DraftReply",
    "InvalidWorkflowTransitionError",
    "MessageCategory",
    "MessageMetadata",
    "Priority",
    "PriorityLevel",
    "SourceType",
    "Summary",
    "WorkflowAction",
    "WorkflowActionStatus",
    "WorkflowActionType",
]
