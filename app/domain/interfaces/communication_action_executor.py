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

    Carries only the approved reply. It does not include the workflow entity,
    proposed text, analysis id, owner, or provider routing fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: UUID
    action_type: WorkflowActionType
    approved_reply_body: str

    @field_validator("approved_reply_body")
    @classmethod
    def validate_approved_reply_body(cls, value: str) -> str:
        """Require a non-empty approved reply snapshot."""
        return require_non_empty_text(value, "approved_reply_body")


class CommunicationActionExecutor(ABC):
    """Execute an already-authorized communication action.

    Success returns ``None``. Expected execution failure raises
    ``CommunicationActionExecutionError``. The caller must not hold a database
    transaction open across ``execute``.
    """

    @abstractmethod
    def execute(self, command: CommunicationActionExecution) -> None:
        """Perform the authorized side effect described by ``command``."""
