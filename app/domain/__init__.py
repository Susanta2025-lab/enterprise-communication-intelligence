"""Provider-independent communication domain for ECI Platform."""

from app.domain.enums import (
    CommunicationCapability,
    ConnectorAccountStatus,
    MailboxAuthorizationProvider,
    MailboxAuthorizationPurpose,
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
    "CommunicationCapability",
    "CommunicationConnector",
    "CommunicationMessage",
    "CommunicationRequest",
    "ConnectorAccountStatus",
    "DraftReply",
    "InvalidWorkflowTransitionError",
    "MailboxAuthorizationProvider",
    "MailboxAuthorizationPurpose",
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
