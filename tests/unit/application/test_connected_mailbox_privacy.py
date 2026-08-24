"""Privacy hardening for connected-mailbox list and analyze."""

from __future__ import annotations

import pytest

from app.application.exceptions import (
    AnalysisFailedError,
    ConnectedMailboxNotAvailableError,
    MailboxPaginationCursorInvalidError,
)
from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.connected_mailbox_analysis import (
    ConnectedMailboxAnalysisService,
)
from app.application.services.connected_mailbox_listing import (
    ConnectedMailboxMessageListingService,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ConnectorAuthenticationError,
    ConnectorInvalidCursorError,
    ConnectorMessageContentError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces import CommunicationConnector, ConnectorMessageQuery, MessagePage
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.models import CommunicationMessage
from app.infrastructure.connectors.fake import FakeCommunicationConnector
from app.providers.mock.provider import MockAIProvider
from app.schemas.mailbox import ConnectorAccountMessageListQuery
from tests.support.connector_factory import StaticCommunicationConnectorFactory
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION, TEST_SUBJECT

SECRET_REFRESH_TOKEN_SENTINEL = "SECRET_REFRESH_TOKEN_SENTINEL"
SECRET_ACCESS_TOKEN_SENTINEL = "SECRET_ACCESS_TOKEN_SENTINEL"
SECRET_CREDENTIAL_REF_SENTINEL = "SECRET_CREDENTIAL_REF_SENTINEL"
SECRET_SUBJECT_SENTINEL = "SECRET_SUBJECT_SENTINEL"
SECRET_BODY_SENTINEL = "SECRET_BODY_SENTINEL"
SECRET_CURSOR_SENTINEL = "SECRET_CURSOR_SENTINEL"
SECRET_PROVIDER_PAYLOAD_SENTINEL = "SECRET_PROVIDER_PAYLOAD_SENTINEL"

_PROVIDER_MESSAGE_ID = "fake-msg-001"
_SENTINELS = (
    SECRET_REFRESH_TOKEN_SENTINEL,
    SECRET_ACCESS_TOKEN_SENTINEL,
    SECRET_CREDENTIAL_REF_SENTINEL,
    SECRET_SUBJECT_SENTINEL,
    SECRET_BODY_SENTINEL,
    SECRET_CURSOR_SENTINEL,
    SECRET_PROVIDER_PAYLOAD_SENTINEL,
)


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
        if self.error is not None:
            raise self.error
        return self.inner.fetch_message(provider_message_id)


class _ReauthFactory(StaticCommunicationConnectorFactory):
    def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
        super().create_for_account(account)
        raise CommunicationCredentialReauthorizationRequiredError(
            SECRET_REFRESH_TOKEN_SENTINEL
        )


class _FailingProvider:
    def analyze(self, request: object) -> object:
        raise RuntimeError(SECRET_BODY_SENTINEL)


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _seed(unit: InMemoryUnitOfWork) -> ConnectorAccountRecord:
    user_id = IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(_principal())
    account = sample_connector_account(
        user_id,
        provider="gmail",
        status=ConnectorAccountStatus.ACTIVE,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
        credential_ref=SECRET_CREDENTIAL_REF_SENTINEL,
        external_account_id="mailbox-001",
    )
    unit.connector_account_store[account.id] = account
    return account


def _listing_service(
    uow_factory: UnitOfWorkFactory,
    connector: CommunicationConnector,
    *,
    factory: StaticCommunicationConnectorFactory | None = None,
) -> ConnectedMailboxMessageListingService:
    return ConnectedMailboxMessageListingService(
        IdentityResolver(uow_factory),
        uow_factory,
        factory or StaticCommunicationConnectorFactory(connector),
    )


def _analysis_service(
    uow_factory: UnitOfWorkFactory,
    connector: CommunicationConnector,
    *,
    provider: object | None = None,
    factory: StaticCommunicationConnectorFactory | None = None,
) -> ConnectedMailboxAnalysisService:
    identity = IdentityResolver(uow_factory)
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(provider or MockAIProvider()),  # type: ignore[arg-type]
        principal=_principal(),
        identity_resolver=identity,
        history_service=AnalysisHistoryService(uow_factory),
    )
    return ConnectedMailboxAnalysisService(
        identity,
        uow_factory,
        factory or StaticCommunicationConnectorFactory(connector),
        workflow,
    )


def _assert_no_sentinels(payload: object) -> None:
    serialized = repr(payload)
    for sentinel in _SENTINELS:
        assert sentinel not in serialized


def test_permanent_refresh_failure_omits_sentinels_from_error_and_logs(
    log_events: list[dict],
) -> None:
    unit = InMemoryUnitOfWork()
    account = _seed(unit)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service = _listing_service(
        UnitOfWorkFactory(unit),
        connector,
        factory=_ReauthFactory(connector),
    )

    with pytest.raises(ConnectedMailboxNotAvailableError) as exc_info:
        service.list_messages(
            _principal(),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    assert exc_info.value.message == "Connected mailbox is not available."
    _assert_no_sentinels(exc_info.value.message)
    _assert_no_sentinels(log_events)
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.REAUTH_REQUIRED


def test_transient_refresh_failure_omits_sentinels(log_events: list[dict]) -> None:
    unit = InMemoryUnitOfWork()
    account = _seed(unit)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=CommunicationCredentialUnavailableError(SECRET_ACCESS_TOKEN_SENTINEL),
    )
    service = _listing_service(UnitOfWorkFactory(unit), connector)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.list_messages(
            _principal(),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    _assert_no_sentinels(exc_info.value.message)
    _assert_no_sentinels(log_events)
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE


def test_mailbox_http_401_omits_sentinels(log_events: list[dict]) -> None:
    unit = InMemoryUnitOfWork()
    account = _seed(unit)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorAuthenticationError(SECRET_PROVIDER_PAYLOAD_SENTINEL),
    )
    service = _listing_service(UnitOfWorkFactory(unit), connector)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.list_messages(
            _principal(),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    _assert_no_sentinels(exc_info.value.message)
    _assert_no_sentinels(log_events)
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE


def test_invalid_cursor_omits_cursor_sentinel(log_events: list[dict]) -> None:
    unit = InMemoryUnitOfWork()
    account = _seed(unit)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorInvalidCursorError(),
    )
    service = _listing_service(UnitOfWorkFactory(unit), connector)

    with pytest.raises(MailboxPaginationCursorInvalidError) as exc_info:
        service.list_messages(
            _principal(),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10, cursor=SECRET_CURSOR_SENTINEL),
        )

    assert exc_info.value.message == "Mailbox pagination cursor is invalid."
    _assert_no_sentinels(exc_info.value.message)
    _assert_no_sentinels(log_events)


def test_normalization_failure_omits_body_sentinel(log_events: list[dict]) -> None:
    unit = InMemoryUnitOfWork()
    account = _seed(unit)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorMessageContentError(),
    )
    service = _analysis_service(UnitOfWorkFactory(unit), connector)

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    _assert_no_sentinels(exc_info.value.message)
    _assert_no_sentinels(log_events)
    assert unit.analyses == {}


def test_ai_failure_omits_body_sentinel(log_events: list[dict]) -> None:
    unit = InMemoryUnitOfWork()
    account = _seed(unit)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service = _analysis_service(
        UnitOfWorkFactory(unit),
        connector,
        provider=_FailingProvider(),
    )

    with pytest.raises(AnalysisFailedError) as exc_info:
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    _assert_no_sentinels(exc_info.value.message)
    _assert_no_sentinels(log_events)
    assert unit.analyses == {}
    assert unit.workflow_action_store == {}


def test_reauth_persist_failure_omits_database_details(log_events: list[dict]) -> None:
    unit = InMemoryUnitOfWork()
    account = _seed(unit)
    failing = InMemoryUnitOfWork(
        identities=unit.identities,
        connector_accounts=unit.connector_account_store,
        fail_on_enter=PersistenceError(SECRET_PROVIDER_PAYLOAD_SENTINEL),
    )
    connector = _RecordingConnector(FakeCommunicationConnector())
    service = _listing_service(
        UnitOfWorkFactory(unit, unit, failing),
        connector,
        factory=_ReauthFactory(connector),
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.list_messages(
            _principal(),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    assert exc_info.value.message == "Persistence is currently unavailable."
    _assert_no_sentinels(exc_info.value.message)
    _assert_no_sentinels(log_events)
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE
