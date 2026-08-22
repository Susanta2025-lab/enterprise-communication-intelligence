"""Below-HTTP workflow execution: approve then execute through the fake write port."""

from uuid import uuid4

import pytest

from app.application.exceptions import WorkflowActionNotExecutableError
from app.application.services.identity import IdentityResolver
from app.application.services.workflow_action_execution import WorkflowActionExecutionService
from app.application.services.workflow_actions import WorkflowActionService
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import WorkflowActionStatus
from app.infrastructure.executors.fake import FakeCommunicationActionExecutor
from tests.support.executor_factory import StaticCommunicationActionExecutorFactory
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_analysis_record,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_PERMISSION

_ISSUER = "https://issuer-a.example.invalid/"
_SUBJECT = "subject-a"
_DRAFT_BODY = "Thanks, I will review the report and respond by Friday."
_PROVIDER_MESSAGE_ID = "provider-msg-001"
_PROVIDER = "fake"


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _mailbox_wired_services(
    executor: FakeCommunicationActionExecutor | None = None,
) -> tuple[
    WorkflowActionService,
    WorkflowActionExecutionService,
    InMemoryUnitOfWork,
    FakeCommunicationActionExecutor,
]:
    user_id = uuid4()
    account = sample_connector_account(user_id, provider=_PROVIDER)
    analysis = sample_analysis_record(
        user_id,
        extra={
            "connector_account_id": account.id,
            "message_id": _PROVIDER_MESSAGE_ID,
            "draft_reply": {
                "body": _DRAFT_BODY,
                "tone": "professional",
                "confidence": 0.8,
            },
        },
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        analyses={analysis.id: analysis},
        connector_accounts={account.id: account},
    )
    factory = UnitOfWorkFactory(unit)
    identity = IdentityResolver(factory)
    fake = executor if executor is not None else FakeCommunicationActionExecutor()
    workflow = WorkflowActionService(identity, factory)
    execution = WorkflowActionExecutionService(
        identity,
        factory,
        StaticCommunicationActionExecutorFactory(fake),
    )
    return workflow, execution, unit, fake


def _direct_text_wired_services() -> tuple[
    WorkflowActionService,
    WorkflowActionExecutionService,
    InMemoryUnitOfWork,
    FakeCommunicationActionExecutor,
]:
    user_id = uuid4()
    analysis = sample_analysis_record(
        user_id,
        extra={
            "draft_reply": {
                "body": _DRAFT_BODY,
                "tone": "professional",
                "confidence": 0.8,
            }
        },
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        analyses={analysis.id: analysis},
    )
    factory = UnitOfWorkFactory(unit)
    identity = IdentityResolver(factory)
    fake = FakeCommunicationActionExecutor()
    workflow = WorkflowActionService(identity, factory)
    execution = WorkflowActionExecutionService(
        identity,
        factory,
        StaticCommunicationActionExecutorFactory(fake),
    )
    return workflow, execution, unit, fake


def test_create_approve_execute_reaches_executed() -> None:
    """Realistic proposal → approval → fake execution without an HTTP execute route."""
    workflow, execution, unit, fake = _mailbox_wired_services()
    analysis_id = next(iter(unit.analyses))

    created = workflow.create(_principal(), analysis_id)
    approved = workflow.approve(_principal(), created.id)
    executed = execution.execute(_principal(), approved.id)

    assert created.status is WorkflowActionStatus.PENDING
    assert created.has_execution_target is True
    assert approved.status is WorkflowActionStatus.APPROVED
    assert executed.status is WorkflowActionStatus.EXECUTED
    assert executed.executed_at is not None
    assert executed.failed_at is None
    assert len(fake.calls) == 1
    assert fake.calls[0].action_id == created.id
    assert fake.calls[0].approved_reply_body == _DRAFT_BODY
    assert fake.calls[0].provider_message_id == _PROVIDER_MESSAGE_ID
    assert fake.calls[0].provider == _PROVIDER
    assert unit.workflow_action_store[created.id].status is WorkflowActionStatus.EXECUTED


def test_create_approve_delete_analysis_execute_reaches_executed() -> None:
    """Execution remains valid after the source analysis is hard-deleted."""
    workflow, execution, unit, fake = _mailbox_wired_services()
    analysis_id = next(iter(unit.analyses))
    user_id = next(iter(unit.identities.values()))

    created = workflow.create(_principal(), analysis_id)
    workflow.approve(_principal(), created.id)
    assert unit.analysis_repository.delete_for_user(analysis_id, user_id) is True
    unit.analysis_repository.get_calls = 0

    executed = execution.execute(_principal(), created.id)

    assert executed.status is WorkflowActionStatus.EXECUTED
    assert executed.analysis_id == analysis_id
    assert executed.approved_reply_body == _DRAFT_BODY
    assert executed.has_execution_target is True
    assert len(fake.calls) == 1
    command = fake.calls[0]
    assert command.approved_reply_body == _DRAFT_BODY
    assert command.provider_message_id == _PROVIDER_MESSAGE_ID
    assert command.provider == _PROVIDER
    assert command.connector_account_id == created.connector_account_id
    assert unit.analysis_repository.get_calls == 0
    assert analysis_id not in unit.analyses


def test_expected_fake_failure_reaches_failed_without_http() -> None:
    """Known fake failure persists FAILED below the HTTP surface."""
    workflow, execution, unit, fake = _mailbox_wired_services(
        FakeCommunicationActionExecutor(fail=True)
    )
    analysis_id = next(iter(unit.analyses))

    created = workflow.create(_principal(), analysis_id)
    workflow.approve(_principal(), created.id)
    failed = execution.execute(_principal(), created.id)

    assert failed.status is WorkflowActionStatus.FAILED
    assert failed.failed_at is not None
    assert failed.executed_at is None
    assert len(fake.calls) == 1
    assert unit.workflow_action_store[created.id].status is WorkflowActionStatus.FAILED


def test_direct_text_workflow_is_not_executable() -> None:
    """Direct-text proposals remain approvable but cannot execute."""
    workflow, execution, unit, fake = _direct_text_wired_services()
    analysis_id = next(iter(unit.analyses))

    created = workflow.create(_principal(), analysis_id)
    approved = workflow.approve(_principal(), created.id)

    assert created.has_execution_target is False
    assert approved.has_execution_target is False
    with pytest.raises(WorkflowActionNotExecutableError):
        execution.execute(_principal(), approved.id)

    assert fake.calls == []
    assert unit.workflow_action_store[created.id].status is WorkflowActionStatus.APPROVED
