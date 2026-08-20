"""Domain model for approval-gated workflow actions."""

from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.exceptions import InvalidWorkflowTransitionError
from app.domain.models.validation import require_non_empty_text

_ALLOWED_TRANSITIONS: dict[WorkflowActionStatus, frozenset[WorkflowActionStatus]] = {
    WorkflowActionStatus.PENDING: frozenset(
        {WorkflowActionStatus.APPROVED, WorkflowActionStatus.REJECTED}
    ),
    WorkflowActionStatus.APPROVED: frozenset({WorkflowActionStatus.EXECUTING}),
    WorkflowActionStatus.EXECUTING: frozenset(
        {WorkflowActionStatus.EXECUTED, WorkflowActionStatus.FAILED}
    ),
    WorkflowActionStatus.REJECTED: frozenset(),
    WorkflowActionStatus.EXECUTED: frozenset(),
    WorkflowActionStatus.FAILED: frozenset(),
}

TERMINAL_WORKFLOW_STATUSES = frozenset(
    {
        WorkflowActionStatus.REJECTED,
        WorkflowActionStatus.EXECUTED,
        WorkflowActionStatus.FAILED,
    }
)


class WorkflowAction(BaseModel):
    """An explicit, approval-gated business action.

    Distinct from ``ActionItem``, which is AI-extracted analysis output, and from
    ``CommunicationAnalysisWorkflowService``, which orchestrates analysis
    persistence. Analyzing a communication does not create a ``WorkflowAction``.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    action_type: WorkflowActionType
    analysis_id: UUID
    owner_user_id: UUID
    status: WorkflowActionStatus = WorkflowActionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    executed_at: datetime | None = None
    failed_at: datetime | None = None
    approved_reply_body: str | None = None

    @model_validator(mode="after")
    def validate_created_pending(self) -> Self:
        """New workflow actions start pending with no later lifecycle fields."""
        if self.status is not WorkflowActionStatus.PENDING:
            raise ValueError("workflow actions must be created with pending status")
        if self.approved_at is not None:
            raise ValueError("pending workflow actions cannot have approved_at")
        if self.rejected_at is not None:
            raise ValueError("pending workflow actions cannot have rejected_at")
        if self.executed_at is not None:
            raise ValueError("pending workflow actions cannot have executed_at")
        if self.failed_at is not None:
            raise ValueError("pending workflow actions cannot have failed_at")
        if self.approved_reply_body is not None:
            raise ValueError("pending workflow actions cannot have approved_reply_body")
        return self

    @property
    def is_terminal(self) -> bool:
        """Whether Phase 11 allows no further transitions from the current status."""
        return self.status in TERMINAL_WORKFLOW_STATUSES

    def approve(self, *, approved_reply_body: str) -> None:
        """Move ``PENDING`` → ``APPROVED`` and snapshot the approved reply body."""
        self._require_transition(WorkflowActionStatus.APPROVED)
        snapshot = require_non_empty_text(approved_reply_body, "approved_reply_body")
        self.status = WorkflowActionStatus.APPROVED
        self.approved_at = datetime.now(UTC)
        self.approved_reply_body = snapshot

    def reject(self) -> None:
        """Move ``PENDING`` → ``REJECTED``."""
        self._require_transition(WorkflowActionStatus.REJECTED)
        self.status = WorkflowActionStatus.REJECTED
        self.rejected_at = datetime.now(UTC)

    def mark_executing(self) -> None:
        """Move ``APPROVED`` → ``EXECUTING``."""
        self._require_transition(WorkflowActionStatus.EXECUTING)
        self.status = WorkflowActionStatus.EXECUTING

    def mark_executed(self) -> None:
        """Move ``EXECUTING`` → ``EXECUTED``."""
        self._require_transition(WorkflowActionStatus.EXECUTED)
        self.status = WorkflowActionStatus.EXECUTED
        self.executed_at = datetime.now(UTC)

    def mark_failed(self) -> None:
        """Move ``EXECUTING`` → ``FAILED``."""
        self._require_transition(WorkflowActionStatus.FAILED)
        self.status = WorkflowActionStatus.FAILED
        self.failed_at = datetime.now(UTC)

    def _require_transition(self, target: WorkflowActionStatus) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.status]
        if target not in allowed:
            raise InvalidWorkflowTransitionError()
