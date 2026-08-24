"""Provider-independent communication domain models."""

from app.domain.models.analysis import (
    ActionItem,
    CommunicationAnalysis,
    DraftReply,
    Priority,
    Summary,
)
from app.domain.models.capabilities import (
    is_mail_read_allowed,
    is_mail_send_executable,
    normalize_communication_capabilities,
    parse_stored_communication_capabilities,
    require_requested_communication_capabilities,
    serialize_communication_capabilities,
)
from app.domain.models.message import CommunicationMessage, MessageMetadata
from app.domain.models.workflow import WorkflowAction

__all__ = [
    "ActionItem",
    "CommunicationAnalysis",
    "CommunicationMessage",
    "DraftReply",
    "MessageMetadata",
    "Priority",
    "Summary",
    "WorkflowAction",
    "normalize_communication_capabilities",
    "parse_stored_communication_capabilities",
    "is_mail_read_allowed",
    "is_mail_send_executable",
    "require_requested_communication_capabilities",
    "serialize_communication_capabilities",
]
