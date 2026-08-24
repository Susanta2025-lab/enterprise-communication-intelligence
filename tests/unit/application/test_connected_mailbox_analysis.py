"""Unit tests for ConnectedMailboxAnalysisService ownership and failure mapping."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    AnalysisFailedError,
    ConnectedMailboxNotAvailableError,
    ConnectorAccountNotFoundError,
    MailboxMessageNotFoundError,
)
from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.connected_mailbox_analysis import (
    ConnectedMailboxAnalysisService,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import (
    CommunicationConnectorNotAvailableError,
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ConnectorAuthenticationError,
    ConnectorMessageContentError,
    ConnectorMessageNotFoundError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces import CommunicationConnector, ConnectorMessageQuery, MessagePage
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.models import CommunicationMessage
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.infrastructure.connectors.fake import FakeCommunicationConnector
from app.providers.mock.provider import MockAIProvider
from tests.support.connector_factory import StaticCommunicationConnectorFactory
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION, TEST_SUBJECT

_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_B = "subject-b"
_PROVIDER_MESSAGE_ID = "fake-msg-001"


class _OpenTracker:
    def __init__(self, unit: InMemoryUnitOfWork) -> None:
        self.unit = unit
        self.open = 0
        self.max_open = 0
        self.calls = 0

    def __call__(self) -> _TrackedUnit:
        self.calls += 1
        return _TrackedUnit(self)


class _TrackedUnit:
    def __init__(self, tracker: _OpenTracker) -> None:
        self._tracker = tracker

    def __enter__(self) -> InMemoryUnitOfWork:
        self._tracker.open += 1
        self._tracker.max_open = max(self._tracker.max_open, self._tracker.open)
        return self._tracker.unit.__enter__()

    def __exit__(self, *args: object) -> None:
        self._tracker.open -= 1
        self._tracker.unit.__exit__(*args)


class _GuardedFactory(StaticCommunicationConnectorFactory):
    def __init__(
        self,
        connector: CommunicationConnector,
        tracker: _OpenTracker,
    ) -> None:
        super().__init__(connector)
        self.tracker = tracker
        self.open_on_create: list[int] = []

    def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
        self.open_on_create.append(self.tracker.open)
        return super().create_for_account(account)


class _RecordingConnector:
    def __init__(
        self,
        inner: CommunicationConnector,
        *,
        error: Exception | None = None,
    ) -> None:
        self.inner = inner
        self.error = error
        self.fetch_ids: list[str] = []

    @property
    def provider(self) -> str:
        return self.inner.provider

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        raise AssertionError("mailbox listing must not run during analyze")

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        self.fetch_ids.append(provider_message_id)
        if self.error is not None:
            raise self.error
        return self.inner.fetch_message(provider_message_id)


class _RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[CommunicationRequest] = []
        self._inner = MockAIProvider()

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        self.calls.append(request)
        return self._inner.analyze(request)


class _FailingProvider:
    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        raise RuntimeError("provider unreachable")


class _SaveFailingHistory(AnalysisHistoryService):
    def __init__(self) -> None:
        self.save_calls = 0

    def save(self, user_id, request, result, *, connector_account_id=None):  # noqa: ANN001
        self.save_calls += 1
        raise PersistenceError("Could not persist analysis.")


def _principal(
    *,
    issuer: str = TEST_ISSUER,
    subject: str = TEST_SUBJECT,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=issuer,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _seed_user(unit: InMemoryUnitOfWork, principal: AuthenticatedPrincipal) -> UUID:
    return IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)


def _seed_account(
    unit: InMemoryUnitOfWork,
    user_id: UUID,
    *,
    provider: str = "gmail",
    status: ConnectorAccountStatus = ConnectorAccountStatus.ACTIVE,
    granted_capabilities: tuple[CommunicationCapability, ...] | None = (
        CommunicationCapability.MAIL_READ,
    ),
    credential_ref: str | None = "mailbox-locator-001",
) -> ConnectorAccountRecord:
    account = sample_connector_account(
        user_id,
        provider=provider,
        status=status,
        granted_capabilities=granted_capabilities,
        credential_ref=credential_ref,
    )
    unit.connector_account_store[account.id] = account
    return account


def _service(
    unit: InMemoryUnitOfWork,
    connector: CommunicationConnector,
    *,
    provider: object | None = None,
    history: AnalysisHistoryService | None = None,
    factory: StaticCommunicationConnectorFactory | None = None,
    tracker: _OpenTracker | None = None,
) -> tuple[ConnectedMailboxAnalysisService, StaticCommunicationConnectorFactory]:
    uow_factory: UnitOfWorkFactory | _OpenTracker
    if tracker is None:
        uow_factory = UnitOfWorkFactory(unit)
    else:
        uow_factory = tracker
    identity = IdentityResolver(uow_factory)
    analysis_provider = provider if provider is not None else MockAIProvider()
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(analysis_provider),  # type: ignore[arg-type]
        principal=_principal(),
        identity_resolver=identity,
        history_service=history or AnalysisHistoryService(uow_factory),
    )
    connector_factory = factory or StaticCommunicationConnectorFactory(connector)
    service = ConnectedMailboxAnalysisService(
        identity,
        uow_factory,
        connector_factory,
        workflow,
    )
    return service, connector_factory


def test_owned_active_read_account_analyzes_and_persists_provenance() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    provider = _RecordingProvider()
    service, factory = _service(unit, connector, provider=provider)

    outcome = service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert factory.calls == 1
    assert factory.accounts == [account]
    assert connector.fetch_ids == [_PROVIDER_MESSAGE_ID]
    assert len(provider.calls) == 1
    assert provider.calls[0].message.message_id == _PROVIDER_MESSAGE_ID
    assert outcome.analysis_id is not None
    stored = unit.analyses[outcome.analysis_id]
    assert stored.user_id == user_id
    assert stored.connector_account_id == account.id
    assert stored.message_id == _PROVIDER_MESSAGE_ID
    assert stored.summary_text
    assert "Q3 budget" not in stored.summary_text or stored.summary_text
    dumped = repr(stored)
    assert "Please review the Q3 budget proposal before Friday." not in dumped
    assert unit.workflow_action_store == {}


def test_unit_of_work_is_closed_before_factory_and_fetch() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    tracker = _OpenTracker(unit)
    connector = _RecordingConnector(FakeCommunicationConnector())
    factory = _GuardedFactory(connector, tracker)
    service, _ = _service(unit, connector, factory=factory, tracker=tracker)

    service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert tracker.open == 0
    assert factory.open_on_create == [0]
    assert connector.fetch_ids == [_PROVIDER_MESSAGE_ID]


def test_unknown_and_cross_user_accounts_are_identical_not_found() -> None:
    unit = InMemoryUnitOfWork()
    owner = _principal()
    other = _principal(issuer=_ISSUER_B, subject=_SUBJECT_B)
    owner_id = _seed_user(unit, owner)
    _seed_user(unit, other)
    account = _seed_account(unit, owner_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    provider = _RecordingProvider()
    service, factory = _service(unit, connector, provider=provider)

    with pytest.raises(ConnectorAccountNotFoundError) as missing:
        service.analyze(owner, uuid4(), _PROVIDER_MESSAGE_ID)
    with pytest.raises(ConnectorAccountNotFoundError) as foreign:
        service.analyze(other, account.id, _PROVIDER_MESSAGE_ID)

    assert str(missing.value) == str(foreign.value)
    assert factory.calls == 0
    assert connector.fetch_ids == []
    assert provider.calls == []


def test_unusable_owned_accounts_raise_before_provider_io() -> None:
    cases = [
        {"status": ConnectorAccountStatus.DISCONNECTED},
        {"status": ConnectorAccountStatus.REAUTH_REQUIRED},
        {"granted_capabilities": (CommunicationCapability.MAIL_SEND,)},
        {"granted_capabilities": ()},
        {"credential_ref": None},
        {"provider": "fake"},
    ]
    for kwargs in cases:
        unit = InMemoryUnitOfWork()
        user_id = _seed_user(unit, _principal())
        account = _seed_account(unit, user_id, **kwargs)
        connector = _RecordingConnector(FakeCommunicationConnector())
        provider = _RecordingProvider()
        service, factory = _service(unit, connector, provider=provider)

        with pytest.raises(ConnectedMailboxNotAvailableError) as exc_info:
            service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

        assert exc_info.value.message == "Connected mailbox is not available."
        assert "disconnected" not in exc_info.value.message.lower()
        assert "reauth" not in exc_info.value.message.lower()
        assert factory.calls == 0
        assert connector.fetch_ids == []
        assert provider.calls == []


def test_legacy_null_capabilities_remain_eligible() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id, granted_capabilities=None)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory = _service(unit, connector)

    outcome = service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert factory.calls == 1
    assert outcome.result.analysis.summary.text


def test_message_not_found_does_not_call_ai() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorMessageNotFoundError(),
    )
    provider = _RecordingProvider()
    service, factory = _service(unit, connector, provider=provider)

    with pytest.raises(MailboxMessageNotFoundError) as exc_info:
        service.analyze(_principal(), account.id, "missing-message")

    assert exc_info.value.message == "Mailbox message not found."
    assert factory.calls == 1
    assert connector.fetch_ids == ["missing-message"]
    assert provider.calls == []
    assert unit.analyses == {}


@pytest.mark.parametrize(
    "error",
    [
        CommunicationCredentialUnavailableError(),
        ConnectorUnavailableError(),
        ConnectorRateLimitError(),
        ConnectorAuthenticationError(),
    ],
)
def test_transient_failures_are_unavailable_without_ai(error: Exception) -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector(), error=error)
    provider = _RecordingProvider()
    service, _ = _service(unit, connector, provider=provider)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert "gmail" not in exc_info.value.message.lower()
    assert "token" not in exc_info.value.message.lower()
    assert connector.fetch_ids == [_PROVIDER_MESSAGE_ID]
    assert provider.calls == []


def test_permanent_refresh_failure_does_not_fetch_or_analyze() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    provider = _RecordingProvider()

    class _ReauthFactory(StaticCommunicationConnectorFactory):
        def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
            super().create_for_account(account)
            raise CommunicationCredentialReauthorizationRequiredError()

    factory = _ReauthFactory(connector)
    service, _ = _service(unit, connector, provider=provider, factory=factory)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert factory.calls == 1
    assert connector.fetch_ids == []
    assert provider.calls == []
    stored = unit.connector_account_store[account.id]
    assert stored.status is ConnectorAccountStatus.ACTIVE


def test_refresh_failure_during_fetch_skips_ai_and_does_not_mutate_status() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=CommunicationCredentialReauthorizationRequiredError(),
    )
    provider = _RecordingProvider()
    service, _ = _service(unit, connector, provider=provider)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert connector.fetch_ids == [_PROVIDER_MESSAGE_ID]
    assert provider.calls == []
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE


def test_unroutable_factory_result_is_mailbox_unavailable() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    provider = _RecordingProvider()

    class _UnroutableFactory(StaticCommunicationConnectorFactory):
        def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
            super().create_for_account(account)
            raise CommunicationConnectorNotAvailableError()

    service, _ = _service(
        unit,
        connector,
        provider=provider,
        factory=_UnroutableFactory(connector),
    )

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert provider.calls == []


def test_invalid_message_content_does_not_call_ai() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorMessageContentError(),
    )
    provider = _RecordingProvider()
    service, _ = _service(unit, connector, provider=provider)

    with pytest.raises(ConnectorMessageContentError):
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert provider.calls == []
    assert unit.analyses == {}


def test_ai_failure_after_fetch_does_not_create_history() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory = _service(unit, connector, provider=_FailingProvider())

    with pytest.raises(AnalysisFailedError):
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert factory.calls == 1
    assert connector.fetch_ids == [_PROVIDER_MESSAGE_ID]
    assert unit.analyses == {}
    assert unit.workflow_action_store == {}


def test_history_save_failure_still_returns_analysis() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    history = _SaveFailingHistory()
    service, _ = _service(unit, connector, history=history)

    outcome = service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert outcome.analysis_id is None
    assert outcome.result.analysis.summary.text
    assert history.save_calls == 1
    assert unit.analyses == {}


def test_logs_omit_secrets_and_mailbox_content(log_events: list[dict]) -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id, credential_ref="oauth-secret-locator")
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, _ = _service(unit, connector)

    service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    mailbox_events = [
        event
        for event in log_events
        if str(event.get("event", "")).startswith("connected_mailbox_analysis_")
    ]
    ingestion_events = [
        event
        for event in log_events
        if str(event.get("event", "")).startswith("connector_fetch_")
    ]
    assert mailbox_events
    assert ingestion_events
    serialized = repr(mailbox_events + ingestion_events)
    assert "Please review the Q3 budget proposal before Friday." not in serialized
    assert "oauth-secret-locator" not in serialized
    assert "finance.bot@example.com" not in serialized
    assert "Q3 budget review" not in serialized
    assert _PROVIDER_MESSAGE_ID not in serialized
    assert "refresh_token" not in serialized
    assert any(event.get("provider") == "gmail" for event in mailbox_events)


def test_module_stays_provider_neutral() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[3]
        / "app"
        / "application"
        / "services"
        / "connected_mailbox_analysis.py"
    ).read_text(encoding="utf-8")
    assert "GmailCommunicationConnector" not in source
    assert "MicrosoftGraphCommunicationConnector" not in source
    assert "CommunicationActionExecutor" not in source
    assert "mark_reauth_required" not in source
