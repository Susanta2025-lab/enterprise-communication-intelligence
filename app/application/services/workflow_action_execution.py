"""Execute an already-approved workflow action through a write port.

``WorkflowActionService`` remains the proposal/approval lifecycle. This service
validates mailbox routing before ``APPROVED`` → ``EXECUTING``, commits that
transition before any executor call, holds no unit of work across that call,
then records ``EXECUTED`` or ``FAILED``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID

from app.application.exceptions import (
    WorkflowActionConflictError,
    WorkflowActionNotExecutableError,
    WorkflowActionNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import (
    CommunicationActionExecutionError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import ConnectorAccountStatus, WorkflowActionStatus
from app.domain.interfaces.communication_action_executor import (
    CommunicationActionExecution,
    CommunicationActionExecutor,
)
from app.domain.interfaces.communication_action_executor_factory import (
    CommunicationActionExecutorFactory,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.interfaces.workflow_action_repository import (
    WorkflowActionSaveOutcome,
    WorkflowActionSaveResult,
)
from app.domain.models.workflow import WorkflowAction

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."


class WorkflowActionExecutionService:
    """Commit execution eligibility, invoke the write port, then persist the outcome."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
        executor_factory: CommunicationActionExecutorFactory,
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory
        self._executor_factory = executor_factory

    def execute(
        self,
        principal: AuthenticatedPrincipal,
        action_id: UUID,
    ) -> WorkflowAction:
        """Execute an owned APPROVED action and return the persisted terminal row."""
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        command, executor = self._commit_executing(user_id, action_id, started_at)

        try:
            executor.execute(command)
        except CommunicationActionExecutionError as exc:
            logger.warning(
                "workflow_action_execution_failed",
                operation="execute",
                workflow_action_id=str(action_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            saved = self._commit_terminal(
                user_id,
                action_id,
                started_at,
                succeeded=False,
            )
            logger.info(
                "workflow_action_execution_recorded_failed",
                operation="execute",
                workflow_action_id=str(saved.id),
                duration_ms=elapsed_ms(started_at),
                status=saved.status.value,
            )
            return saved

        saved = self._commit_terminal(
            user_id,
            action_id,
            started_at,
            succeeded=True,
        )
        logger.info(
            "workflow_action_executed",
            operation="execute",
            workflow_action_id=str(saved.id),
            connector_account_id=str(command.connector_account_id),
            provider=command.provider,
            duration_ms=elapsed_ms(started_at),
            status=saved.status.value,
        )
        return saved

    def _commit_executing(
        self,
        user_id: UUID,
        action_id: UUID,
        started_at: float,
    ) -> tuple[CommunicationActionExecution, CommunicationActionExecutor]:
        try:
            with self._unit_of_work_factory() as uow:
                action = uow.workflow_actions.get_owned(action_id, user_id)
                if action is None:
                    raise WorkflowActionNotFoundError()
                if action.status is not WorkflowActionStatus.APPROVED:
                    action.mark_executing()
                if not action.has_execution_target:
                    logger.info(
                        "workflow_action_not_executable",
                        operation="execute",
                        workflow_action_id=str(action.id),
                        has_execution_target=False,
                        status=action.status.value,
                        duration_ms=elapsed_ms(started_at),
                    )
                    raise WorkflowActionNotExecutableError()
                connector_account_id = action.connector_account_id
                if connector_account_id is None:
                    raise WorkflowActionNotExecutableError()
                account = uow.connector_accounts.get_owned(connector_account_id, user_id)
                if not _connector_account_is_usable(account):
                    logger.info(
                        "workflow_action_not_executable",
                        operation="execute",
                        workflow_action_id=str(action.id),
                        connector_account_id=str(connector_account_id),
                        has_execution_target=True,
                        status=action.status.value,
                        duration_ms=elapsed_ms(started_at),
                    )
                    raise WorkflowActionNotExecutableError()
                executor = self._executor_factory.create_for_account(account)
                if executor is None:
                    logger.info(
                        "workflow_action_not_executable",
                        operation="execute",
                        workflow_action_id=str(action.id),
                        connector_account_id=str(connector_account_id),
                        provider=account.provider,
                        has_execution_target=True,
                        status=action.status.value,
                        duration_ms=elapsed_ms(started_at),
                    )
                    raise WorkflowActionNotExecutableError()
                action.mark_executing()
                result = uow.workflow_actions.save_owned(
                    action,
                    expected_status=WorkflowActionStatus.APPROVED,
                )
                saved = _require_save_success(result)
                command = _execution_command(saved, provider=account.provider)
                uow.commit()
        except WorkflowActionNotFoundError:
            raise
        except WorkflowActionNotExecutableError:
            raise
        except WorkflowActionConflictError:
            raise
        except PersistenceError as exc:
            logger.warning(
                "workflow_action_persistence_failed",
                operation="execute",
                workflow_action_id=str(action_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "workflow_action_execution_started",
            operation="execute",
            workflow_action_id=str(command.action_id),
            connector_account_id=str(command.connector_account_id),
            provider=command.provider,
            has_execution_target=True,
            duration_ms=elapsed_ms(started_at),
            status=WorkflowActionStatus.EXECUTING.value,
        )
        return command, executor

    def _commit_terminal(
        self,
        user_id: UUID,
        action_id: UUID,
        started_at: float,
        *,
        succeeded: bool,
    ) -> WorkflowAction:
        try:
            with self._unit_of_work_factory() as uow:
                action = uow.workflow_actions.get_owned(action_id, user_id)
                if action is None:
                    raise WorkflowActionNotFoundError()
                if succeeded:
                    action.mark_executed()
                else:
                    action.mark_failed()
                result = uow.workflow_actions.save_owned(
                    action,
                    expected_status=WorkflowActionStatus.EXECUTING,
                )
                saved = _require_save_success(result)
                uow.commit()
        except WorkflowActionNotFoundError:
            raise
        except WorkflowActionConflictError:
            raise
        except PersistenceError as exc:
            logger.warning(
                "workflow_action_persistence_failed",
                operation="execute",
                workflow_action_id=str(action_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None
        return saved

    def _require_existing_user(self, principal: AuthenticatedPrincipal) -> UUID:
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise WorkflowActionNotFoundError()
        return user_id


def _connector_account_is_usable(account: ConnectorAccountRecord | None) -> bool:
    return account is not None and account.status is ConnectorAccountStatus.ACTIVE


def _execution_command(
    action: WorkflowAction,
    *,
    provider: str,
) -> CommunicationActionExecution:
    approved_reply_body = action.approved_reply_body
    connector_account_id = action.connector_account_id
    provider_message_id = action.provider_message_id
    if (
        approved_reply_body is None
        or connector_account_id is None
        or provider_message_id is None
    ):
        raise PersistenceError("Could not persist workflow action.")
    return CommunicationActionExecution(
        action_id=action.id,
        action_type=action.action_type,
        approved_reply_body=approved_reply_body,
        connector_account_id=connector_account_id,
        provider_message_id=provider_message_id,
        provider=provider,
    )


def _require_save_success(result: WorkflowActionSaveResult) -> WorkflowAction:
    if result.outcome is WorkflowActionSaveOutcome.SUCCESS and result.action is not None:
        return result.action
    if result.outcome is WorkflowActionSaveOutcome.NOT_FOUND:
        raise WorkflowActionNotFoundError()
    if result.outcome is WorkflowActionSaveOutcome.CONFLICT:
        raise WorkflowActionConflictError()
    raise PersistenceError("Could not persist workflow action.")
