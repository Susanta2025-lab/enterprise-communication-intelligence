"""Prove Graph executor exception types against existing workflow lifecycle handling.

This does not wire Microsoft Graph into production execution. It uses stub
executors that raise the same exception classes the Graph adapter uses.
"""

from __future__ import annotations

import pytest

from app.application.services.identity import IdentityResolver
from app.application.services.workflow_action_execution import WorkflowActionExecutionService
from app.core.exceptions import (
    CommunicationActionExecutionError,
    CommunicationCredentialUnavailableError,
    ECIPlatformError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.domain.enums import WorkflowActionStatus
from app.domain.interfaces.communication_action_executor import (
    CommunicationActionExecution,
    CommunicationActionExecutor,
)
from tests.support.in_memory_persistence import UnitOfWorkFactory
from tests.unit.application.test_workflow_action_execution_service import (
    _approved_action,
    _principal,
    _seeded_unit,
)


class _RaisingExecutor(CommunicationActionExecutor):
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[CommunicationActionExecution] = []

    def execute(self, command: CommunicationActionExecution) -> None:
        self.calls.append(command)
        raise self.error


def test_graph_exception_types_are_siblings_not_failed_subtypes() -> None:
    assert issubclass(CommunicationActionExecutionError, ECIPlatformError)
    assert issubclass(ServiceUnavailableError, ECIPlatformError)
    assert issubclass(CommunicationCredentialUnavailableError, ECIPlatformError)
    assert issubclass(PersistenceError, ECIPlatformError)
    assert not issubclass(CommunicationActionExecutionError, ServiceUnavailableError)
    assert not issubclass(ServiceUnavailableError, CommunicationActionExecutionError)
    assert not issubclass(
        CommunicationCredentialUnavailableError,
        CommunicationActionExecutionError,
    )
    assert not issubclass(PersistenceError, CommunicationActionExecutionError)


def test_communication_action_execution_error_becomes_failed() -> None:
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    factory = UnitOfWorkFactory(unit)
    executor = _RaisingExecutor(CommunicationActionExecutionError())
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    result = service.execute(_principal(), approved.id)

    assert result.status is WorkflowActionStatus.FAILED
    assert result.failed_at is not None
    assert len(executor.calls) == 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.FAILED


def test_service_unavailable_leaves_executing() -> None:
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    factory = UnitOfWorkFactory(unit)
    executor = _RaisingExecutor(
        ServiceUnavailableError("Communication action execution is currently unavailable."),
    )
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    with pytest.raises(ServiceUnavailableError):
        service.execute(_principal(), approved.id)

    assert len(executor.calls) == 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.EXECUTING
    assert stored.failed_at is None
    assert stored.executed_at is None
