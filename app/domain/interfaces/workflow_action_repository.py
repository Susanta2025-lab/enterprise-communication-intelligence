"""SQLAlchemy-free workflow-action persistence contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.enums import WorkflowActionStatus
from app.domain.models.workflow import WorkflowAction


class WorkflowActionSaveOutcome(StrEnum):
    """Result of a conditional owned update.

    Distinguishes a successful write from unknown/cross-user rows and from a
    stored status that no longer matches the expected source state.
    """

    SUCCESS = "success"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class WorkflowActionSaveResult:
    """Outcome of ``save_owned``. ``action`` is set only on success."""

    outcome: WorkflowActionSaveOutcome
    action: WorkflowAction | None = None


class WorkflowActionRepository(ABC):
    """Store and retrieve workflow actions with ownership enforced in every query.

    Methods do not commit. The caller owns the transaction.
    """

    @abstractmethod
    def add(self, action: WorkflowAction) -> WorkflowAction:
        """Persist ``action`` and return the stored domain object."""

    @abstractmethod
    def get_owned(self, action_id: UUID, user_id: UUID) -> WorkflowAction | None:
        """Return the action only when it is owned by ``user_id``."""

    @abstractmethod
    def list_owned(self, user_id: UUID, limit: int, offset: int) -> list[WorkflowAction]:
        """Return a bounded page of actions owned by ``user_id``, newest first."""

    @abstractmethod
    def save_owned(
        self,
        action: WorkflowAction,
        expected_status: WorkflowActionStatus,
    ) -> WorkflowActionSaveResult:
        """Conditionally persist lifecycle fields when the stored status matches.

        The update is scoped by ``action.id``, ``action.owner_user_id``, and
        ``expected_status``. Zero matching rows are classified as not-found or
        conflict by a follow-up ownership lookup.
        """
