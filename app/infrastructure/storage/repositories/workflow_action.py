"""SQLAlchemy WorkflowActionRepository implementation."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.interfaces.workflow_action_repository import (
    WorkflowActionRepository,
    WorkflowActionSaveOutcome,
    WorkflowActionSaveResult,
)
from app.domain.models.workflow import WorkflowAction
from app.infrastructure.storage.models import WorkflowAction as WorkflowActionRow

_GENERIC_FAILURE = "Could not persist workflow action."
_INVALID_STORED = "Stored workflow action is invalid."
_MAX_LIST_LIMIT = 100


class SqlAlchemyWorkflowActionRepository(WorkflowActionRepository):
    """Persist workflow actions with ownership enforced in SQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, action: WorkflowAction) -> WorkflowAction:
        """Persist ``action`` and return the stored domain object."""
        row = WorkflowActionRow(
            id=action.id,
            user_id=action.owner_user_id,
            analysis_id=action.analysis_id,
            action_type=action.action_type.value,
            status=action.status.value,
            proposed_reply_body=action.proposed_reply_body,
            approved_reply_body=action.approved_reply_body,
            created_at=action.created_at,
            approved_at=action.approved_at,
            rejected_at=action.rejected_at,
            executed_at=action.executed_at,
            failed_at=action.failed_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise PersistenceError(_GENERIC_FAILURE) from exc
        return _to_domain(row)

    def get_owned(self, action_id: UUID, user_id: UUID) -> WorkflowAction | None:
        """Return the action only when it is owned by ``user_id``."""
        statement = (
            select(WorkflowActionRow)
            .where(
                WorkflowActionRow.id == action_id,
                WorkflowActionRow.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(statement).first()
        if row is None:
            return None
        return _to_domain(row)

    def list_owned(self, user_id: UUID, limit: int, offset: int) -> list[WorkflowAction]:
        """Return a bounded page of actions owned by ``user_id``, newest first.

        Non-positive ``limit`` or negative ``offset`` yield an empty page so
        those values are never passed to SQL.
        """
        if limit < 1 or offset < 0:
            return []
        statement = (
            select(WorkflowActionRow)
            .where(WorkflowActionRow.user_id == user_id)
            .order_by(WorkflowActionRow.created_at.desc(), WorkflowActionRow.id.desc())
            .limit(min(limit, _MAX_LIST_LIMIT))
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return [_to_domain(row) for row in self._session.scalars(statement).all()]

    def save_owned(
        self,
        action: WorkflowAction,
        expected_status: WorkflowActionStatus,
    ) -> WorkflowActionSaveResult:
        """Conditionally persist lifecycle fields when the stored status matches."""
        statement = (
            update(WorkflowActionRow)
            .where(
                WorkflowActionRow.id == action.id,
                WorkflowActionRow.user_id == action.owner_user_id,
                WorkflowActionRow.status == expected_status.value,
            )
            .values(
                status=action.status.value,
                approved_reply_body=action.approved_reply_body,
                approved_at=action.approved_at,
                rejected_at=action.rejected_at,
                executed_at=action.executed_at,
                failed_at=action.failed_at,
            )
            .execution_options(synchronize_session="fetch")
        )
        try:
            result = self._session.execute(statement)
        except (IntegrityError, SQLAlchemyError):
            raise PersistenceError(_GENERIC_FAILURE) from None
        if result.rowcount == 1:
            loaded = self.get_owned(action.id, action.owner_user_id)
            if loaded is None:
                raise PersistenceError(_GENERIC_FAILURE)
            return WorkflowActionSaveResult(
                outcome=WorkflowActionSaveOutcome.SUCCESS,
                action=loaded,
            )
        existing = self.get_owned(action.id, action.owner_user_id)
        if existing is None:
            return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.NOT_FOUND)
        return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.CONFLICT)


def _to_domain(row: WorkflowActionRow) -> WorkflowAction:
    try:
        return WorkflowAction.rehydrate(
            id=row.id,
            action_type=WorkflowActionType(row.action_type),
            analysis_id=row.analysis_id,
            owner_user_id=row.user_id,
            proposed_reply_body=row.proposed_reply_body,
            status=WorkflowActionStatus(row.status),
            created_at=row.created_at,
            approved_at=row.approved_at,
            rejected_at=row.rejected_at,
            executed_at=row.executed_at,
            failed_at=row.failed_at,
            approved_reply_body=row.approved_reply_body,
        )
    except (ValidationError, ValueError):
        raise PersistenceError(_INVALID_STORED) from None
