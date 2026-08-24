"""Unit tests for ConnectedMailboxMessageListingService."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    ConnectedMailboxNotAvailableError,
    ConnectorAccountNotFoundError,
    MailboxPaginationCursorInvalidError,
)
from app.application.services.connected_mailbox_listing import (
    ConnectedMailboxMessageListingService,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import (
    CommunicationConnectorNotAvailableError,
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ConnectorAuthenticationError,
    ConnectorInvalidCursorError,
    ConnectorMessageContentError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
    ServiceUnavailableError,
)
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces import CommunicationConnector, ConnectorMessageQuery, MessagePage
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.models import CommunicationMessage
from app.infrastructure.connectors.fake import FakeCommunicationConnector
from app.schemas.mailbox import ConnectorAccountMessageListQuery
from tests.support.connector_factory import StaticCommunicationConnectorFactory
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION, TEST_SUBJECT

_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_B = "subject-b"
_LIST_FIELDS = frozenset(
    {"provider_message_id", "sender", "subject", "sent_at", "received_at"}
)


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
        self.list_queries: list[ConnectorMessageQuery] = []
        self.fetch_ids: list[str] = []

    @property
    def provider(self) -> str:
        return self.inner.provider

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        self.list_queries.append(query)
        if self.error is not None:
            raise self.error
        return self.inner.list_messages(query)

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        self.fetch_ids.append(provider_message_id)
        raise AssertionError("listing service must not fetch by id")


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
    factory: StaticCommunicationConnectorFactory | None = None,
    tracker: _OpenTracker | None = None,
) -> tuple[ConnectedMailboxMessageListingService, StaticCommunicationConnectorFactory]:
    uow_factory: UnitOfWorkFactory | _OpenTracker
    if tracker is None:
        uow_factory = UnitOfWorkFactory(unit)
    else:
        uow_factory = tracker
    identity = IdentityResolver(uow_factory)
    connector_factory = factory or StaticCommunicationConnectorFactory(connector)
    service = ConnectedMailboxMessageListingService(
        identity,
        uow_factory,
        connector_factory,
    )
    return service, connector_factory


def _list(
    service: ConnectedMailboxMessageListingService,
    account_id: UUID,
    *,
    page_size: int = 10,
    cursor: str | None = None,
) -> object:
    return service.list_messages(
        _principal(),
        account_id,
        ConnectorAccountMessageListQuery(page_size=page_size, cursor=cursor),
    )


def test_owned_active_read_account_lists_frozen_metadata() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory = _service(unit, connector)

    response = _list(service, account.id, page_size=2)

    assert factory.calls == 1
    assert factory.accounts == [account]
    assert len(connector.list_queries) == 1
    assert connector.list_queries[0].limit == 2
    assert connector.list_queries[0].cursor is None
    assert connector.fetch_ids == []
    assert len(response.items) == 2
    first = response.items[0]
    assert first.provider_message_id == "fake-msg-001"
    assert first.sender == "finance.bot@example.com"
    assert first.subject == "Q3 budget review"
    assert first.sent_at is not None
    assert first.received_at is not None
    payload = first.model_dump()
    assert set(payload) == _LIST_FIELDS
    serialized = repr(response.model_dump())
    assert "Please review the Q3 budget proposal before Friday." not in serialized
    assert "body" not in payload
    assert "recipients" not in payload
    assert "thread_id" not in payload
    assert "credential_ref" not in serialized
    assert unit.analyses == {}
    assert unit.workflow_action_store == {}


def test_default_page_size_reaches_connector() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, _ = _service(unit, connector)

    _list(service, account.id)

    assert connector.list_queries[0].limit == 10


def test_continuation_cursor_is_round_tripped() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, _ = _service(unit, connector)

    first = _list(service, account.id, page_size=2)
    second = _list(service, account.id, page_size=2, cursor=first.next_cursor)
    third = _list(service, account.id, page_size=2, cursor=second.next_cursor)

    assert first.next_cursor == "n:2"
    assert second.next_cursor == "n:4"
    assert third.next_cursor is None
    assert connector.list_queries[1].cursor == first.next_cursor
    assert connector.list_queries[2].cursor == second.next_cursor
    assert [item.provider_message_id for item in first.items] == [
        "fake-msg-001",
        "fake-msg-002",
    ]
    assert [item.provider_message_id for item in third.items] == ["fake-msg-005"]


def test_unit_of_work_is_closed_before_factory_and_list() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    tracker = _OpenTracker(unit)
    connector = _RecordingConnector(FakeCommunicationConnector())
    factory = _GuardedFactory(connector, tracker)
    service, _ = _service(unit, connector, factory=factory, tracker=tracker)

    _list(service, account.id, page_size=1)

    assert tracker.open == 0
    assert factory.open_on_create == [0]
    assert len(connector.list_queries) == 1


def test_unknown_and_cross_user_accounts_are_identical_not_found() -> None:
    unit = InMemoryUnitOfWork()
    owner = _principal()
    other = _principal(issuer=_ISSUER_B, subject=_SUBJECT_B)
    owner_id = _seed_user(unit, owner)
    _seed_user(unit, other)
    account = _seed_account(unit, owner_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory = _service(unit, connector)

    with pytest.raises(ConnectorAccountNotFoundError) as missing:
        _list(service, uuid4())
    with pytest.raises(ConnectorAccountNotFoundError) as foreign:
        service.list_messages(
            other,
            account.id,
            ConnectorAccountMessageListQuery(),
        )

    assert str(missing.value) == str(foreign.value)
    assert factory.calls == 0
    assert connector.list_queries == []
    assert connector.fetch_ids == []


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
        service, factory = _service(unit, connector)

        with pytest.raises(ConnectedMailboxNotAvailableError) as exc_info:
            _list(service, account.id)

        assert exc_info.value.message == "Connected mailbox is not available."
        assert "disconnected" not in exc_info.value.message.lower()
        assert "reauth" not in exc_info.value.message.lower()
        assert factory.calls == 0
        assert connector.list_queries == []


def test_legacy_null_capabilities_remain_eligible() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id, granted_capabilities=None)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory = _service(unit, connector)

    response = _list(service, account.id, page_size=1)

    assert factory.calls == 1
    assert response.items[0].provider_message_id == "fake-msg-001"


def test_invalid_cursor_is_sanitized_client_error() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorInvalidCursorError(),
    )
    service, factory = _service(unit, connector)

    with pytest.raises(MailboxPaginationCursorInvalidError) as exc_info:
        _list(service, account.id, cursor="n:99")

    assert exc_info.value.message == "Mailbox pagination cursor is invalid."
    assert "connector" not in exc_info.value.message.lower()
    assert "gmail" not in exc_info.value.message.lower()
    assert factory.calls == 1
    assert connector.list_queries[0].cursor == "n:99"


@pytest.mark.parametrize(
    "error",
    [
        CommunicationCredentialUnavailableError(),
        ConnectorUnavailableError(),
        ConnectorRateLimitError(),
        ConnectorAuthenticationError(),
    ],
)
def test_transient_failures_are_unavailable(error: Exception) -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector(), error=error)
    service, _ = _service(unit, connector)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        _list(service, account.id)

    assert "gmail" not in exc_info.value.message.lower()
    assert "token" not in exc_info.value.message.lower()
    assert len(connector.list_queries) == 1


def test_permanent_refresh_failure_does_not_list() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())

    class _ReauthFactory(StaticCommunicationConnectorFactory):
        def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
            super().create_for_account(account)
            raise CommunicationCredentialReauthorizationRequiredError()

    factory = _ReauthFactory(connector)
    service, _ = _service(unit, connector, factory=factory)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(service, account.id)

    assert factory.calls == 1
    assert connector.list_queries == []
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE


def test_refresh_failure_during_list_does_not_mutate_status() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=CommunicationCredentialReauthorizationRequiredError(),
    )
    service, _ = _service(unit, connector)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(service, account.id)

    assert len(connector.list_queries) == 1
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE


def test_unroutable_factory_result_is_mailbox_unavailable() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())

    class _UnroutableFactory(StaticCommunicationConnectorFactory):
        def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
            super().create_for_account(account)
            raise CommunicationConnectorNotAvailableError()

    service, _ = _service(unit, connector, factory=_UnroutableFactory(connector))

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(service, account.id)


def test_invalid_message_content_does_not_persist() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorMessageContentError(),
    )
    service, _ = _service(unit, connector)

    with pytest.raises(ConnectorMessageContentError):
        _list(service, account.id)

    assert unit.analyses == {}
    assert unit.workflow_action_store == {}


def test_logs_omit_secrets_mailbox_content_and_cursor(log_events: list[dict]) -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, _principal())
    account = _seed_account(unit, user_id, credential_ref="oauth-secret-locator")
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, _ = _service(unit, connector)

    first = _list(service, account.id, page_size=1)
    _list(service, account.id, page_size=1, cursor=first.next_cursor)

    mailbox_events = [
        event
        for event in log_events
        if str(event.get("event", "")).startswith("connected_mailbox_list_")
    ]
    assert mailbox_events
    serialized = repr(mailbox_events)
    assert "Please review the Q3 budget proposal before Friday." not in serialized
    assert "oauth-secret-locator" not in serialized
    assert "finance.bot@example.com" not in serialized
    assert "Q3 budget review" not in serialized
    assert "fake-msg-001" not in serialized
    assert "n:1" not in serialized
    assert "refresh_token" not in serialized
    assert any(event.get("provider") == "gmail" for event in mailbox_events)


def test_module_stays_provider_neutral() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[3]
        / "app"
        / "application"
        / "services"
        / "connected_mailbox_listing.py"
    ).read_text(encoding="utf-8")
    assert "GmailCommunicationConnector" not in source
    assert "MicrosoftGraphCommunicationConnector" not in source
    assert "CommunicationActionExecutor" not in source
    assert "CommunicationAnalysisService" not in source
    assert "AIProvider" not in source
    assert "mark_reauth_required" not in source
