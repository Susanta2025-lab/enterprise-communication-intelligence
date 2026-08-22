"""Unit tests for WorkflowActionExecutionService."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    WorkflowActionConflictError,
    WorkflowActionNotExecutableError,
    WorkflowActionNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.application.services.workflow_action_execution import WorkflowActionExecutionService
from app.application.services.workflow_actions import WorkflowActionService
from app.core.exceptions import (
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import ConnectorAccountStatus, WorkflowActionStatus, WorkflowActionType
from app.domain.exceptions import InvalidWorkflowTransitionError
from app.domain.interfaces.communication_action_executor import (
    CommunicationActionExecution,
    CommunicationActionExecutor,
)
from app.domain.interfaces.workflow_action_repository import (
    WorkflowActionSaveOutcome,
    WorkflowActionSaveResult,
)
from app.domain.models.workflow import WorkflowAction
from app.infrastructure.executors.fake import FakeCommunicationActionExecutor
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_analysis_record,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_PERMISSION

_ISSUER_A = "https://issuer-a.example.invalid/"
_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_A = "subject-a"
_SUBJECT_B = "subject-b"
_DRAFT_BODY = "Thanks, I will review the report and respond by Friday."
_APPROVED_BODY = "Authorized reply snapshot that differs from the proposal."
_PROVIDER_MESSAGE_ID = "provider-msg-001"
_PROVIDER = "fake"


def _principal(
    *,
    issuer: str = _ISSUER_A,
    subject: str = _SUBJECT_A,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=issuer,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _analysis(
    user_id: UUID,
    *,
    draft_body: str | None = _DRAFT_BODY,
    connector_account_id: UUID | None = None,
    message_id: str | None = "msg-001",
):
    extra: dict[str, object] = {}
    if connector_account_id is not None:
        extra["connector_account_id"] = connector_account_id
    extra["message_id"] = message_id
    if draft_body is None:
        extra["draft_reply"] = None
    else:
        extra["draft_reply"] = {
            "body": draft_body,
            "tone": "professional",
            "confidence": 0.8,
        }
    return sample_analysis_record(user_id, extra=extra)


def _workflow_service(unit: InMemoryUnitOfWork) -> WorkflowActionService:
    factory = UnitOfWorkFactory(unit)
    return WorkflowActionService(IdentityResolver(factory), factory)


def _execution_service(
    unit: InMemoryUnitOfWork,
    executor: CommunicationActionExecutor | None = None,
) -> tuple[
    WorkflowActionExecutionService,
    FakeCommunicationActionExecutor | CommunicationActionExecutor,
]:
    factory = UnitOfWorkFactory(unit)
    fake = executor if executor is not None else FakeCommunicationActionExecutor()
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, fake)
    return service, fake


def _seeded_unit() -> tuple[InMemoryUnitOfWork, UUID, UUID]:
    user_id = uuid4()
    account = sample_connector_account(user_id, provider=_PROVIDER)
    analysis = _analysis(
        user_id,
        connector_account_id=account.id,
        message_id=_PROVIDER_MESSAGE_ID,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        analyses={analysis.id: analysis},
        connector_accounts={account.id: account},
    )
    return unit, user_id, analysis.id


def _targetless_unit() -> tuple[InMemoryUnitOfWork, UUID, UUID]:
    user_id = uuid4()
    analysis = _analysis(user_id, connector_account_id=None, message_id="msg-001")
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        analyses={analysis.id: analysis},
    )
    return unit, user_id, analysis.id


def _approved_action(
    unit: InMemoryUnitOfWork,
    analysis_id: UUID,
) -> WorkflowAction:
    workflow = _workflow_service(unit)
    created = workflow.create(_principal(), analysis_id)
    return workflow.approve(_principal(), created.id)


def _rehydrate(**overrides: object) -> WorkflowAction:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": uuid4(),
        "action_type": WorkflowActionType.REPLY,
        "analysis_id": uuid4(),
        "owner_user_id": uuid4(),
        "proposed_reply_body": _DRAFT_BODY,
        "status": WorkflowActionStatus.APPROVED,
        "created_at": now,
        "approved_at": now,
        "rejected_at": None,
        "executed_at": None,
        "failed_at": None,
        "approved_reply_body": _DRAFT_BODY,
        "connector_account_id": None,
        "provider_message_id": None,
    }
    payload.update(overrides)
    return WorkflowAction.rehydrate(**payload)


def _shared_unit(
    unit: InMemoryUnitOfWork,
    *,
    fail_on_enter: Exception | None = None,
) -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork(
        identities=unit.identities,
        analyses=unit.analyses,
        connector_accounts=unit.connector_account_store,
        workflow_actions=unit.workflow_action_store,
        fail_on_enter=fail_on_enter,
    )


class _InspectingExecutor(FakeCommunicationActionExecutor):
    """Records committed TX1 state at the moment the fake execute is invoked."""

    def __init__(
        self,
        store: InMemoryUnitOfWork,
        tx1: InMemoryUnitOfWork,
        tx2: InMemoryUnitOfWork,
        factory: UnitOfWorkFactory,
    ) -> None:
        super().__init__()
        self._store = store
        self._tx1 = tx1
        self._tx2 = tx2
        self._factory = factory
        self.status_at_call: WorkflowActionStatus | None = None
        self.tx1_commit_calls_at_call: int | None = None
        self.tx1_closed_at_call: bool | None = None
        self.tx2_entered_at_call: bool | None = None
        self.factory_calls_at_call: int | None = None

    def execute(self, command: CommunicationActionExecution) -> None:
        stored = self._store.workflow_action_store[command.action_id]
        self.status_at_call = stored.status
        self.tx1_commit_calls_at_call = self._tx1.commit_calls
        self.tx1_closed_at_call = self._tx1.closed
        self.tx2_entered_at_call = self._tx2.entered
        self.factory_calls_at_call = self._factory.calls
        super().execute(command)


class _BoomExecutor(CommunicationActionExecutor):
    """Raises an unexpected exception instead of CommunicationActionExecutionError."""

    def __init__(self) -> None:
        self.calls: list[CommunicationActionExecution] = []

    def execute(self, command: CommunicationActionExecution) -> None:
        self.calls.append(command)
        raise RuntimeError("unexpected adapter bug")


def test_execute_success_persists_executed() -> None:
    """APPROVED → EXECUTING → fake success → EXECUTED."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    service, executor = _execution_service(unit)
    unit.analysis_repository.get_calls = 0

    result = service.execute(_principal(), approved.id)

    assert result.status is WorkflowActionStatus.EXECUTED
    assert result.executed_at is not None
    assert result.failed_at is None
    assert result.approved_reply_body == _DRAFT_BODY
    assert len(executor.calls) == 1
    assert executor.calls[0].action_id == approved.id
    assert executor.calls[0].approved_reply_body == _DRAFT_BODY
    assert executor.calls[0].provider_message_id == _PROVIDER_MESSAGE_ID
    assert executor.calls[0].provider == _PROVIDER
    assert executor.calls[0].connector_account_id is not None
    assert unit.analysis_repository.get_calls == 0
    assert unit.identity_repository.create_calls == 0
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.EXECUTED


def test_execute_expected_fake_failure_persists_failed() -> None:
    """Known executor failure becomes durable FAILED and is not re-raised."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    service, executor = _execution_service(unit, FakeCommunicationActionExecutor(fail=True))

    result = service.execute(_principal(), approved.id)

    assert result.status is WorkflowActionStatus.FAILED
    assert result.failed_at is not None
    assert result.executed_at is None
    assert len(executor.calls) == 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.FAILED


@pytest.mark.parametrize(
    "status",
    [
        WorkflowActionStatus.PENDING,
        WorkflowActionStatus.REJECTED,
        WorkflowActionStatus.EXECUTING,
        WorkflowActionStatus.EXECUTED,
        WorkflowActionStatus.FAILED,
    ],
)
def test_non_approved_status_does_not_call_executor(status: WorkflowActionStatus) -> None:
    """Only APPROVED may begin execution."""
    now = datetime.now(UTC)
    user_id = uuid4()
    fields: dict[str, object] = {
        "owner_user_id": user_id,
        "status": status,
        "created_at": now,
    }
    if status is WorkflowActionStatus.PENDING:
        fields.update(approved_reply_body=None, approved_at=None)
    elif status is WorkflowActionStatus.REJECTED:
        fields.update(
            approved_reply_body=None,
            approved_at=None,
            rejected_at=now,
        )
    elif status is WorkflowActionStatus.EXECUTED:
        fields.update(executed_at=now)
    elif status is WorkflowActionStatus.FAILED:
        fields.update(failed_at=now)
    action = _rehydrate(**fields)
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        workflow_actions={action.id: action},
    )
    service, executor = _execution_service(unit)

    with pytest.raises(InvalidWorkflowTransitionError):
        service.execute(_principal(), action.id)

    assert executor.calls == []
    assert unit.workflow_action_store[action.id].status is status


def test_missing_identity_is_not_found_and_skips_executor() -> None:
    """Missing identity mapping does not create a user or call the executor."""
    unit = InMemoryUnitOfWork()
    action = _rehydrate()
    unit.workflow_action_store[action.id] = action
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionNotFoundError):
        service.execute(_principal(), action.id)

    assert executor.calls == []
    assert unit.identity_repository.create_calls == 0


def test_unknown_action_is_not_found_and_skips_executor() -> None:
    """Unknown action ids raise not-found with zero executor calls."""
    unit, _user_id, _analysis_id = _seeded_unit()
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionNotFoundError):
        service.execute(_principal(), uuid4())

    assert executor.calls == []


def test_cross_user_action_is_not_found_and_skips_executor() -> None:
    """Another user's action is indistinguishable from unknown."""
    owner = uuid4()
    other = uuid4()
    action = _rehydrate(owner_user_id=owner)
    unit = InMemoryUnitOfWork(
        identities={
            (_ISSUER_A, _SUBJECT_A): other,
            (_ISSUER_B, _SUBJECT_B): owner,
        },
        workflow_actions={action.id: action},
    )
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionNotFoundError):
        service.execute(_principal(), action.id)

    assert executor.calls == []
    assert unit.workflow_action_store[action.id].status is WorkflowActionStatus.APPROVED


def test_tx1_conflict_does_not_call_executor() -> None:
    """Optimistic TX1 conflict fails closed before the side effect."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    captured: list[object] = []

    def _conflict(
        action: WorkflowAction,
        expected_status: object,
    ) -> WorkflowActionSaveResult:
        captured.append(expected_status)
        return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.CONFLICT)

    unit.workflow_actions.save_owned = _conflict  # type: ignore[method-assign]
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionConflictError):
        service.execute(_principal(), approved.id)

    assert captured == [WorkflowActionStatus.APPROVED]
    assert executor.calls == []


def test_tx1_not_found_does_not_call_executor() -> None:
    """TX1 save_owned NOT_FOUND fails closed before the side effect."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)

    def _not_found(
        action: WorkflowAction,
        expected_status: object,
    ) -> WorkflowActionSaveResult:
        return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.NOT_FOUND)

    unit.workflow_actions.save_owned = _not_found  # type: ignore[method-assign]
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionNotFoundError):
        service.execute(_principal(), approved.id)

    assert executor.calls == []


def test_tx1_commit_failure_does_not_call_executor() -> None:
    """TX1 persistence failure never reaches the executor."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    unit.fail_commit = True
    service, executor = _execution_service(unit)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.execute(_principal(), approved.id)

    assert exc_info.value.message == "Persistence is currently unavailable."
    assert executor.calls == []


def test_tx1_persistence_enter_failure_does_not_call_executor() -> None:
    """TX1 unit-of-work enter failure never reaches the executor."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    tx1 = _shared_unit(
        unit,
        fail_on_enter=PersistenceError("Could not persist workflow action."),
    )
    factory = UnitOfWorkFactory(unit, tx1)
    executor = FakeCommunicationActionExecutor()
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.execute(_principal(), approved.id)

    assert exc_info.value.message == "Persistence is currently unavailable."
    assert executor.calls == []
    assert unit.workflow_action_store[approved.id].status is WorkflowActionStatus.APPROVED


def test_executing_is_committed_before_executor_runs() -> None:
    """Executor runs only after TX1 commit and after that unit of work has closed."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    tx1 = _shared_unit(unit)
    tx2 = _shared_unit(unit)
    factory = UnitOfWorkFactory(unit, tx1, tx2)
    executor = _InspectingExecutor(unit, tx1, tx2, factory)
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    result = service.execute(_principal(), approved.id)

    assert result.status is WorkflowActionStatus.EXECUTED
    assert executor.status_at_call is WorkflowActionStatus.EXECUTING
    assert executor.tx1_commit_calls_at_call == 1
    assert executor.tx1_closed_at_call is True
    assert executor.tx2_entered_at_call is False
    assert executor.factory_calls_at_call == 2
    assert len(executor.calls) == 1
    assert tx2.commit_calls == 1
    assert tx2.closed is True


def test_second_execute_does_not_call_executor_again() -> None:
    """A stored EXECUTING/EXECUTED row cannot begin execution a second time."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    service, executor = _execution_service(unit)

    first = service.execute(_principal(), approved.id)
    assert first.status is WorkflowActionStatus.EXECUTED
    assert len(executor.calls) == 1

    with pytest.raises(InvalidWorkflowTransitionError):
        service.execute(_principal(), approved.id)

    assert len(executor.calls) == 1
    assert unit.workflow_action_store[approved.id].status is WorkflowActionStatus.EXECUTED


def test_analysis_hard_delete_does_not_block_execution() -> None:
    """Execution uses the approved snapshot and does not load analysis history."""
    unit, user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    assert unit.analysis_repository.delete_for_user(analysis_id, user_id) is True
    service, executor = _execution_service(unit)
    unit.analysis_repository.get_calls = 0

    result = service.execute(_principal(), approved.id)

    assert result.status is WorkflowActionStatus.EXECUTED
    assert result.approved_reply_body == _DRAFT_BODY
    assert result.has_execution_target is True
    assert len(executor.calls) == 1
    command = executor.calls[0]
    assert command.provider_message_id == _PROVIDER_MESSAGE_ID
    assert command.provider == _PROVIDER
    assert command.connector_account_id == approved.connector_account_id
    assert unit.analysis_repository.get_calls == 0
    assert analysis_id not in unit.analyses


def test_executor_receives_approved_snapshot_not_proposal() -> None:
    """The write command is built from approved_reply_body, even when it differs."""
    user_id = uuid4()
    account = sample_connector_account(user_id, provider=_PROVIDER)
    action = _rehydrate(
        owner_user_id=user_id,
        proposed_reply_body=_DRAFT_BODY,
        approved_reply_body=_APPROVED_BODY,
        connector_account_id=account.id,
        provider_message_id=_PROVIDER_MESSAGE_ID,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts={account.id: account},
        workflow_actions={action.id: action},
    )
    service, executor = _execution_service(unit)

    result = service.execute(_principal(), action.id)

    assert result.status is WorkflowActionStatus.EXECUTED
    assert len(executor.calls) == 1
    command = executor.calls[0]
    assert command.approved_reply_body == _APPROVED_BODY
    assert command.approved_reply_body != _DRAFT_BODY
    assert command.connector_account_id == account.id
    assert command.provider_message_id == _PROVIDER_MESSAGE_ID
    assert command.provider == _PROVIDER
    assert not hasattr(command, "proposed_reply_body")
    assert not hasattr(command, "credential_ref")
    assert set(CommunicationActionExecution.model_fields) == {
        "action_id",
        "action_type",
        "approved_reply_body",
        "connector_account_id",
        "provider_message_id",
        "provider",
    }


def test_tx2_persistence_failure_after_success_leaves_executing() -> None:
    """Fake success plus TX2 persistence failure must not record EXECUTED."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    tx2 = InMemoryUnitOfWork(
        identities=unit.identities,
        analyses=unit.analyses,
        connector_accounts=unit.connector_account_store,
        workflow_actions=unit.workflow_action_store,
        fail_on_enter=PersistenceError("Could not persist workflow action."),
    )
    factory = UnitOfWorkFactory(unit, unit, tx2)
    executor = FakeCommunicationActionExecutor()
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    with pytest.raises(ServiceUnavailableError):
        service.execute(_principal(), approved.id)

    assert len(executor.calls) == 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.EXECUTING
    assert stored.executed_at is None
    assert stored.failed_at is None


def test_tx2_persistence_failure_after_fake_failure_leaves_executing() -> None:
    """FAILED persistence failure must not swallow the persistence problem."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    tx2 = InMemoryUnitOfWork(
        identities=unit.identities,
        analyses=unit.analyses,
        connector_accounts=unit.connector_account_store,
        workflow_actions=unit.workflow_action_store,
        fail_on_enter=PersistenceError("Could not persist workflow action."),
    )
    factory = UnitOfWorkFactory(unit, unit, tx2)
    executor = FakeCommunicationActionExecutor(fail=True)
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    with pytest.raises(ServiceUnavailableError):
        service.execute(_principal(), approved.id)

    assert len(executor.calls) == 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.EXECUTING
    assert stored.failed_at is None
    assert stored.executed_at is None


def test_unexpected_executor_exception_does_not_record_failed() -> None:
    """Uncertain executor failures must not be converted into durable FAILED."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    factory = UnitOfWorkFactory(unit)
    boom = _BoomExecutor()
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, boom)
    commits_before = unit.commit_calls

    with pytest.raises(RuntimeError, match="unexpected adapter bug"):
        service.execute(_principal(), approved.id)

    assert len(boom.calls) == 1
    assert factory.calls == 2
    assert unit.commit_calls == commits_before + 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.EXECUTING
    assert stored.failed_at is None
    assert stored.executed_at is None


def test_tx2_not_found_does_not_return_terminal_or_retry() -> None:
    """TX2 reload NOT_FOUND raises the established not-found error after one execute."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    tx2 = _shared_unit(unit)

    def _missing(_action_id: UUID, _user_id: UUID) -> WorkflowAction | None:
        return None

    tx2.workflow_actions.get_owned = _missing  # type: ignore[method-assign]
    factory = UnitOfWorkFactory(unit, unit, tx2)
    executor = FakeCommunicationActionExecutor()
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    with pytest.raises(WorkflowActionNotFoundError):
        service.execute(_principal(), approved.id)

    assert len(executor.calls) == 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.EXECUTING
    assert stored.executed_at is None
    assert stored.failed_at is None


def test_tx2_conflict_does_not_return_terminal_or_retry() -> None:
    """TX2 expected-status conflict raises WorkflowActionConflictError after one execute."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    tx2 = _shared_unit(unit)

    def _conflict(
        _action: WorkflowAction,
        expected_status: object,
    ) -> WorkflowActionSaveResult:
        assert expected_status is WorkflowActionStatus.EXECUTING
        return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.CONFLICT)

    tx2.workflow_actions.save_owned = _conflict  # type: ignore[method-assign]
    factory = UnitOfWorkFactory(unit, unit, tx2)
    executor = FakeCommunicationActionExecutor()
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    with pytest.raises(WorkflowActionConflictError):
        service.execute(_principal(), approved.id)

    assert len(executor.calls) == 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.EXECUTING
    assert stored.executed_at is None
    assert stored.failed_at is None


def test_tx2_save_not_found_does_not_return_terminal_or_retry() -> None:
    """TX2 save_owned NOT_FOUND raises WorkflowActionNotFoundError after one execute."""
    unit, _user_id, analysis_id = _seeded_unit()
    approved = _approved_action(unit, analysis_id)
    tx2 = _shared_unit(unit)

    def _not_found(
        _action: WorkflowAction,
        expected_status: object,
    ) -> WorkflowActionSaveResult:
        assert expected_status is WorkflowActionStatus.EXECUTING
        return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.NOT_FOUND)

    tx2.workflow_actions.save_owned = _not_found  # type: ignore[method-assign]
    factory = UnitOfWorkFactory(unit, unit, tx2)
    executor = FakeCommunicationActionExecutor()
    service = WorkflowActionExecutionService(IdentityResolver(factory), factory, executor)

    with pytest.raises(WorkflowActionNotFoundError):
        service.execute(_principal(), approved.id)

    assert len(executor.calls) == 1
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.EXECUTING
    assert stored.executed_at is None
    assert stored.failed_at is None


def test_targetless_approved_action_fails_before_execution_state_write() -> None:
    """Direct-text and Phase 11 rows are not executable and do not change state."""
    unit, _user_id, analysis_id = _targetless_unit()
    approved = _approved_action(unit, analysis_id)
    commits_before = unit.commit_calls
    saves_before = unit.workflow_actions.save_calls
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionNotExecutableError) as exc_info:
        service.execute(_principal(), approved.id)

    assert exc_info.value.message == "Workflow action is not executable."
    assert "connector" not in exc_info.value.message.lower()
    assert executor.calls == []
    assert unit.commit_calls == commits_before
    assert unit.workflow_actions.save_calls == saves_before
    stored = unit.workflow_action_store[approved.id]
    assert stored.status is WorkflowActionStatus.APPROVED
    assert stored.has_execution_target is False


def test_cross_user_connector_account_is_not_executable() -> None:
    """An owned action whose snapshotted account belongs to another user fails closed."""
    owner = uuid4()
    other = uuid4()
    foreign_account = sample_connector_account(other, provider=_PROVIDER)
    action = _rehydrate(
        owner_user_id=owner,
        connector_account_id=foreign_account.id,
        provider_message_id=_PROVIDER_MESSAGE_ID,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): owner},
        connector_accounts={foreign_account.id: foreign_account},
        workflow_actions={action.id: action},
    )
    commits_before = unit.commit_calls
    saves_before = unit.workflow_actions.save_calls
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionNotExecutableError) as exc_info:
        service.execute(_principal(), action.id)

    assert exc_info.value.message == "Workflow action is not executable."
    assert str(other) not in exc_info.value.message
    assert str(foreign_account.id) not in exc_info.value.message
    assert executor.calls == []
    assert unit.commit_calls == commits_before
    assert unit.workflow_actions.save_calls == saves_before
    assert unit.workflow_action_store[action.id].status is WorkflowActionStatus.APPROVED


def test_disconnected_connector_account_is_not_executable() -> None:
    """A snapshotted account that is now disconnected fails before the EXECUTING write."""
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider=_PROVIDER,
        status=ConnectorAccountStatus.DISCONNECTED,
        credential_ref=None,
    )
    action = _rehydrate(
        owner_user_id=user_id,
        connector_account_id=account.id,
        provider_message_id=_PROVIDER_MESSAGE_ID,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts={account.id: account},
        workflow_actions={action.id: action},
    )
    commits_before = unit.commit_calls
    saves_before = unit.workflow_actions.save_calls
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionNotExecutableError):
        service.execute(_principal(), action.id)

    assert executor.calls == []
    assert unit.commit_calls == commits_before
    assert unit.workflow_actions.save_calls == saves_before
    assert unit.workflow_action_store[action.id].status is WorkflowActionStatus.APPROVED


def test_missing_connector_account_is_not_executable() -> None:
    """A snapshotted account that no longer exists fails before the EXECUTING write."""
    user_id = uuid4()
    missing_account_id = uuid4()
    action = _rehydrate(
        owner_user_id=user_id,
        connector_account_id=missing_account_id,
        provider_message_id=_PROVIDER_MESSAGE_ID,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        workflow_actions={action.id: action},
    )
    commits_before = unit.commit_calls
    saves_before = unit.workflow_actions.save_calls
    service, executor = _execution_service(unit)

    with pytest.raises(WorkflowActionNotExecutableError):
        service.execute(_principal(), action.id)

    assert executor.calls == []
    assert unit.commit_calls == commits_before
    assert unit.workflow_actions.save_calls == saves_before
    assert unit.workflow_action_store[action.id].status is WorkflowActionStatus.APPROVED


def test_provider_is_resolved_from_owned_connector_account() -> None:
    """Mailbox provider comes from ConnectorAccount, not the caller or AI provider."""
    user_id = uuid4()
    account = sample_connector_account(user_id, provider="microsoft_graph")
    action = _rehydrate(
        owner_user_id=user_id,
        connector_account_id=account.id,
        provider_message_id=_PROVIDER_MESSAGE_ID,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts={account.id: account},
        workflow_actions={action.id: action},
    )
    service, executor = _execution_service(unit)

    result = service.execute(_principal(), action.id)

    assert result.status is WorkflowActionStatus.EXECUTED
    assert executor.calls[0].provider == "microsoft_graph"
    assert executor.calls[0].provider != "mock"


def test_active_account_without_credential_ref_is_structurally_executable() -> None:
    """12A treats ACTIVE as executable without inspecting credential_ref."""
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider=_PROVIDER,
        credential_ref=None,
    )
    action = _rehydrate(
        owner_user_id=user_id,
        connector_account_id=account.id,
        provider_message_id=_PROVIDER_MESSAGE_ID,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts={account.id: account},
        workflow_actions={action.id: action},
    )
    service, executor = _execution_service(unit)

    result = service.execute(_principal(), action.id)

    assert result.status is WorkflowActionStatus.EXECUTED
    assert len(executor.calls) == 1
    assert executor.calls[0].provider == _PROVIDER
    assert "credential_ref" not in CommunicationActionExecution.model_fields
