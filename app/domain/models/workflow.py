"""Domain model for approval-gated workflow actions."""

from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

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

_REHYDRATE_CONTEXT_KEY = "rehydrate"

_NONE_AFTER_PENDING = (
    "approved_reply_body",
    "approved_at",
    "rejected_at",
    "executed_at",
    "failed_at",
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
    proposed_reply_body: str
    status: WorkflowActionStatus = WorkflowActionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    executed_at: datetime | None = None
    failed_at: datetime | None = None
    approved_reply_body: str | None = None
    connector_account_id: UUID | None = None
    provider_message_id: str | None = None

    @field_validator("proposed_reply_body")
    @classmethod
    def validate_proposed_reply_body(cls, value: str) -> str:
        """Require a non-empty proposed reply snapshot."""
        return require_non_empty_text(value, "proposed_reply_body")

    @field_validator("approved_reply_body")
    @classmethod
    def validate_approved_reply_body(cls, value: str | None) -> str | None:
        """Normalize an approved snapshot when one is present."""
        if value is None:
            return None
        return require_non_empty_text(value, "approved_reply_body")

    @field_validator("provider_message_id")
    @classmethod
    def validate_provider_message_id(cls, value: str | None) -> str | None:
        """Normalize an optional provider message identifier."""
        if value is None:
            return None
        return require_non_empty_text(value, "provider_message_id")

    @model_validator(mode="after")
    def validate_lifecycle(self, info: ValidationInfo) -> Self:
        """Enforce PENDING-only public construction or persisted lifecycle invariants."""
        rehydrate = bool(info.context and info.context.get(_REHYDRATE_CONTEXT_KEY))
        if not rehydrate and self.status is not WorkflowActionStatus.PENDING:
            raise ValueError("workflow actions must be created with pending status")
        _validate_execution_target(self)
        _validate_status_invariants(self)
        return self

    @classmethod
    def rehydrate(cls, **data: Any) -> Self:
        """Reconstruct a persisted workflow action and validate its lifecycle."""
        return cls.model_validate(data, context={_REHYDRATE_CONTEXT_KEY: True})

    @property
    def is_terminal(self) -> bool:
        """Whether Phase 11 allows no further transitions from the current status."""
        return self.status in TERMINAL_WORKFLOW_STATUSES

    @property
    def has_execution_target(self) -> bool:
        """Whether both mailbox-routing identifiers are present.

        A half-populated pair is rejected at construction. Legacy and
        direct-text actions keep both fields unset and are not externally
        executable.
        """
        return (
            self.connector_account_id is not None and self.provider_message_id is not None
        )

    def approve(self) -> None:
        """Move ``PENDING`` → ``APPROVED`` by copying the proposed reply snapshot."""
        self._require_transition(WorkflowActionStatus.APPROVED)
        self.status = WorkflowActionStatus.APPROVED
        self.approved_at = datetime.now(UTC)
        self.approved_reply_body = self.proposed_reply_body

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


def _validate_execution_target(action: WorkflowAction) -> None:
    account_present = action.connector_account_id is not None
    message_present = action.provider_message_id is not None
    if account_present != message_present:
        raise ValueError(
            "execution target requires both connector_account_id and provider_message_id"
        )


def _validate_status_invariants(action: WorkflowAction) -> None:
    status = action.status
    if status is WorkflowActionStatus.PENDING:
        _require_absent(action, *_NONE_AFTER_PENDING)
        return
    if status is WorkflowActionStatus.APPROVED:
        _require_present(action, "approved_reply_body", "approved_at")
        _require_absent(action, "rejected_at", "executed_at", "failed_at")
        return
    if status is WorkflowActionStatus.REJECTED:
        _require_present(action, "rejected_at")
        _require_absent(
            action,
            "approved_reply_body",
            "approved_at",
            "executed_at",
            "failed_at",
        )
        return
    if status is WorkflowActionStatus.EXECUTING:
        _require_present(action, "approved_reply_body", "approved_at")
        _require_absent(action, "rejected_at", "executed_at", "failed_at")
        return
    if status is WorkflowActionStatus.EXECUTED:
        _require_present(action, "approved_reply_body", "approved_at", "executed_at")
        _require_absent(action, "rejected_at", "failed_at")
        return
    if status is WorkflowActionStatus.FAILED:
        _require_present(action, "approved_reply_body", "approved_at", "failed_at")
        _require_absent(action, "rejected_at", "executed_at")
        return
    raise ValueError("unsupported workflow action status")


def _require_present(action: WorkflowAction, *field_names: str) -> None:
    for name in field_names:
        if getattr(action, name) is None:
            raise ValueError(f"{action.status.value} workflow actions require {name}")


def _require_absent(action: WorkflowAction, *field_names: str) -> None:
    for name in field_names:
        if getattr(action, name) is not None:
            raise ValueError(f"{action.status.value} workflow actions cannot have {name}")
