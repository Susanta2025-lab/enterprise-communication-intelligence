"""Vendor-neutral write port for authorized communication actions.

This interface is separate from ``CommunicationConnector``, which remains
read-only. Implementations must not leak vendor SDK, HTTP, or credential types.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.enums import WorkflowActionType
from app.domain.models.validation import require_non_empty_text


class CommunicationActionExecution(BaseModel):
    """Immutable authorization snapshot sent across the executor boundary.

    Carries the approved reply plus provider-neutral mailbox routing
    identifiers. It does not include the workflow entity, proposed text,
    analysis id, owner, credentials, or tokens.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: UUID
    action_type: WorkflowActionType
    approved_reply_body: str
    connector_account_id: UUID
    provider_message_id: str
    provider: str

    @field_validator("approved_reply_body")
    @classmethod
    def validate_approved_reply_body(cls, value: str) -> str:
        """Require a non-empty approved reply snapshot."""
        return require_non_empty_text(value, "approved_reply_body")

    @field_validator("provider_message_id")
    @classmethod
    def validate_provider_message_id(cls, value: str) -> str:
        """Require a non-empty provider message identifier."""
        return require_non_empty_text(value, "provider_message_id")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        """Require a non-empty mailbox provider slug from ConnectorAccount."""
        return require_non_empty_text(value, "provider")


class CommunicationActionExecutor(ABC):
    """Execute an already-authorized communication action.

    Success returns ``None``. Expected execution failure raises
    ``CommunicationActionExecutionError``. The caller must not hold a database
    transaction open across ``execute``.
    """

    @abstractmethod
    def execute(self, command: CommunicationActionExecution) -> None:
        """Perform the authorized side effect described by ``command``."""
