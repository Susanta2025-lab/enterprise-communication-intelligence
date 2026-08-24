"""Lifecycle hardening for connected-mailbox list and analyze."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.application.exceptions import (
    ConnectedMailboxNotAvailableError,
    ConnectorAccountNotFoundError,
)
from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.connected_mailbox_access import (
    persist_mailbox_reauthorization_required,
)
from app.application.services.connected_mailbox_analysis import (
    ConnectedMailboxAnalysisService,
)
from app.application.services.connected_mailbox_listing import (
    ConnectedMailboxMessageListingService,
)
from app.application.services.identity import IdentityResolver
from app.application.services.mailbox_oauth_reauthorization import (
    persist_reauthorized_connector_account,
)
from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ConnectorAuthenticationError,
    ConnectorPermissionError,
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

_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_B = "subject-b"
_PROVIDER_MESSAGE_ID = "fake-msg-001"
_GRANTS = (
    CommunicationCapability.MAIL_READ,
    CommunicationCapability.MAIL_SEND,
)
_LOCATOR = "mailbox-locator-001"
_EXTERNAL_ID = "mailbox-001"


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


class _RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self._inner = MockAIProvider()

    def analyze(self, request: object) -> object:
        self.calls.append(request)
        return self._inner.analyze(request)


class _ReauthFactory(StaticCommunicationConnectorFactory):
    def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
        super().create_for_account(account)
        raise CommunicationCredentialReauthorizationRequiredError()


class _DisconnectThenReauthFactory(StaticCommunicationConnectorFactory):
    def __init__(
        self,
        connector: CommunicationConnector,
        unit: InMemoryUnitOfWork,
        account_id: UUID,
        user_id: UUID,
    ) -> None:
        super().__init__(connector)
        self._unit = unit
        self._account_id = account_id
        self._user_id = user_id

    def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
        super().create_for_account(account)
        self._unit.connector_accounts.disconnect_owned(self._account_id, self._user_id)
        raise CommunicationCredentialReauthorizationRequiredError()


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


def _seed_user(
    unit: InMemoryUnitOfWork,
    principal: AuthenticatedPrincipal | None = None,
) -> UUID:
    return IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(
        principal or _principal()
    )


def _seed_account(
    unit: InMemoryUnitOfWork,
    user_id: UUID,
    *,
    status: ConnectorAccountStatus = ConnectorAccountStatus.ACTIVE,
    granted_capabilities: tuple[CommunicationCapability, ...] | None = _GRANTS,
    credential_ref: str | None = _LOCATOR,
    external_account_id: str = _EXTERNAL_ID,
) -> ConnectorAccountRecord:
    account = sample_connector_account(
        user_id,
        provider="gmail",
        status=status,
        granted_capabilities=granted_capabilities,
        credential_ref=credential_ref,
        external_account_id=external_account_id,
    )
    unit.connector_account_store[account.id] = account
    return account


def _listing_service(
    uow_factory: UnitOfWorkFactory,
    connector: CommunicationConnector,
    *,
    factory: StaticCommunicationConnectorFactory | None = None,
) -> tuple[ConnectedMailboxMessageListingService, StaticCommunicationConnectorFactory]:
    identity = IdentityResolver(uow_factory)
    connector_factory = factory or StaticCommunicationConnectorFactory(connector)
    service = ConnectedMailboxMessageListingService(
        identity,
        uow_factory,
        connector_factory,
    )
    return service, connector_factory


def _analysis_service(
    uow_factory: UnitOfWorkFactory,
    connector: CommunicationConnector,
    *,
    factory: StaticCommunicationConnectorFactory | None = None,
) -> tuple[
    ConnectedMailboxAnalysisService,
    StaticCommunicationConnectorFactory,
    _RecordingProvider,
]:
    identity = IdentityResolver(uow_factory)
    provider = _RecordingProvider()
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(provider),  # type: ignore[arg-type]
        principal=_principal(),
        identity_resolver=identity,
        history_service=AnalysisHistoryService(uow_factory),
    )
    connector_factory = factory or StaticCommunicationConnectorFactory(connector)
    service = ConnectedMailboxAnalysisService(
        identity,
        uow_factory,
        connector_factory,
        workflow,
    )
    return service, connector_factory, provider


def _list(service: ConnectedMailboxMessageListingService, account_id: UUID) -> object:
    return service.list_messages(
        _principal(),
        account_id,
        ConnectorAccountMessageListQuery(page_size=10),
    )


def _assert_preserved_reauth(
    stored: ConnectorAccountRecord,
    original: ConnectorAccountRecord,
) -> None:
    assert stored.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert stored.credential_ref == original.credential_ref
    assert stored.granted_capabilities == original.granted_capabilities
    assert stored.external_account_id == original.external_account_id
    assert stored.provider == original.provider
    assert stored.id == original.id
    assert stored.user_id == original.user_id


def test_listing_permanent_refresh_marks_exact_owned_account() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory = _listing_service(
        UnitOfWorkFactory(unit),
        connector,
        factory=_ReauthFactory(connector),
    )

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(service, account.id)

    assert factory.calls == 1
    assert connector.list_queries == []
    _assert_preserved_reauth(unit.connector_account_store[account.id], account)


def test_analyze_permanent_refresh_marks_exact_owned_account_without_ai() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory, provider = _analysis_service(
        UnitOfWorkFactory(unit),
        connector,
        factory=_ReauthFactory(connector),
    )

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert factory.calls == 1
    assert connector.fetch_ids == []
    assert provider.calls == []
    assert unit.analyses == {}
    assert unit.workflow_action_store == {}
    _assert_preserved_reauth(unit.connector_account_store[account.id], account)


def test_reauth_required_at_start_fails_before_factory() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id, status=ConnectorAccountStatus.REAUTH_REQUIRED)
    connector = _RecordingConnector(FakeCommunicationConnector())
    listing, listing_factory = _listing_service(UnitOfWorkFactory(unit), connector)
    analysis, analysis_factory, provider = _analysis_service(
        UnitOfWorkFactory(unit),
        connector,
    )

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(listing, account.id)
    with pytest.raises(ConnectedMailboxNotAvailableError):
        analysis.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    assert listing_factory.calls == 0
    assert analysis_factory.calls == 0
    assert connector.list_queries == []
    assert connector.fetch_ids == []
    assert provider.calls == []
    stored = unit.connector_account_store[account.id]
    assert stored.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert stored.credential_ref == _LOCATOR


def test_subsequent_request_after_reauth_skips_provider_io() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    factory = _ReauthFactory(connector)
    service, _ = _listing_service(UnitOfWorkFactory(unit), connector, factory=factory)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(service, account.id)
    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(service, account.id)

    assert factory.calls == 1
    assert connector.list_queries == []
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.REAUTH_REQUIRED


@pytest.mark.parametrize(
    "error",
    [
        CommunicationCredentialUnavailableError(),
        ConnectorAuthenticationError(),
        ConnectorPermissionError(),
    ],
)
def test_transient_and_mailbox_http_auth_failures_keep_active(error: Exception) -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector(), error=error)
    listing, _ = _listing_service(UnitOfWorkFactory(unit), connector)
    analysis, _, provider = _analysis_service(UnitOfWorkFactory(unit), connector)

    with pytest.raises(ServiceUnavailableError):
        _list(listing, account.id)
    with pytest.raises(ServiceUnavailableError):
        analysis.analyze(_principal(), account.id, _PROVIDER_MESSAGE_ID)

    stored = unit.connector_account_store[account.id]
    assert stored.status is ConnectorAccountStatus.ACTIVE
    assert stored.credential_ref == _LOCATOR
    assert stored.granted_capabilities == _GRANTS
    assert provider.calls == []
    assert unit.analyses == {}
    assert unit.workflow_action_store == {}


def test_persist_failure_after_permanent_refresh_returns_503_and_stays_active() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)
    failing = InMemoryUnitOfWork(
        identities=unit.identities,
        connector_accounts=unit.connector_account_store,
        fail_on_enter=PersistenceError("Could not persist connector account."),
    )
    uow_factory = UnitOfWorkFactory(unit, unit, failing)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory = _listing_service(
        uow_factory,
        connector,
        factory=_ReauthFactory(connector),
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        _list(service, account.id)

    assert exc_info.value.message == "Persistence is currently unavailable."
    assert "Could not persist" not in exc_info.value.message
    assert factory.calls == 1
    assert connector.list_queries == []
    stored = unit.connector_account_store[account.id]
    assert stored.status is ConnectorAccountStatus.ACTIVE
    assert stored.credential_ref == _LOCATOR
    assert stored.granted_capabilities == _GRANTS


def test_disconnect_before_reauth_mutation_is_not_resurrected() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    factory = _DisconnectThenReauthFactory(connector, unit, account.id, user_id)
    service, _ = _listing_service(UnitOfWorkFactory(unit), connector, factory=factory)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(service, account.id)

    stored = unit.connector_account_store[account.id]
    assert stored.status is ConnectorAccountStatus.DISCONNECTED
    assert stored.credential_ref is None
    assert stored.granted_capabilities is None
    assert stored.external_account_id == _EXTERNAL_ID


def test_concurrent_permanent_refresh_persists_are_idempotent() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)

    persist_mailbox_reauthorization_required(
        UnitOfWorkFactory(unit),
        account,
        operation="list",
        started_at=0.0,
    )
    persist_mailbox_reauthorization_required(
        UnitOfWorkFactory(unit),
        account,
        operation="analyze",
        started_at=0.0,
    )

    stored = unit.connector_account_store[account.id]
    _assert_preserved_reauth(stored, account)


def test_cross_user_request_does_not_mutate_owner_account() -> None:
    unit = InMemoryUnitOfWork()
    owner_id = _seed_user(unit)
    other = _principal(issuer=_ISSUER_B, subject=_SUBJECT_B)
    _seed_user(unit, other)
    account = _seed_account(unit, owner_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, factory = _listing_service(UnitOfWorkFactory(unit), connector)

    with pytest.raises(ConnectorAccountNotFoundError):
        service.list_messages(
            other,
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    assert factory.calls == 0
    stored = unit.connector_account_store[account.id]
    assert stored.status is ConnectorAccountStatus.ACTIVE
    assert stored.credential_ref == _LOCATOR
    assert stored.granted_capabilities == _GRANTS


def test_disconnect_clears_locator_and_grants_unlike_refresh_failure() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=CommunicationCredentialReauthorizationRequiredError(),
    )
    listing, _ = _listing_service(UnitOfWorkFactory(unit), connector)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(listing, account.id)
    refreshed = unit.connector_account_store[account.id]
    _assert_preserved_reauth(refreshed, account)

    disconnected = unit.connector_accounts.disconnect_owned(account.id, user_id)
    assert disconnected is not None
    assert disconnected.status is ConnectorAccountStatus.DISCONNECTED
    assert disconnected.credential_ref is None
    assert disconnected.granted_capabilities is None
    assert disconnected.external_account_id == account.external_account_id


def test_reauthorization_recovers_same_mailbox_identity() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    account = _seed_account(unit, user_id)
    connector = _RecordingConnector(FakeCommunicationConnector())
    listing, factory = _listing_service(
        UnitOfWorkFactory(unit),
        connector,
        factory=_ReauthFactory(connector),
    )

    with pytest.raises(ConnectedMailboxNotAvailableError):
        _list(listing, account.id)

    recovered = persist_reauthorized_connector_account(
        UnitOfWorkFactory(unit),
        user_id=user_id,
        connector_account_id=account.id,
        provider=account.provider,
        external_account_id=account.external_account_id,
        credential_ref="mailbox-locator-002",
        granted_capabilities=_GRANTS,
        unavailable_message="Persistence is currently unavailable.",
    )

    assert recovered.id == account.id
    assert recovered.status is ConnectorAccountStatus.ACTIVE
    assert recovered.credential_ref == "mailbox-locator-002"
    assert recovered.granted_capabilities == _GRANTS
    assert recovered.external_account_id == account.external_account_id

    recovered_connector = _RecordingConnector(FakeCommunicationConnector())
    recovered_listing, recovered_factory = _listing_service(
        UnitOfWorkFactory(unit),
        recovered_connector,
    )
    response = _list(recovered_listing, account.id)
    assert recovered_factory.calls == 1
    assert recovered_connector.list_queries
    assert response.items
    assert factory.calls == 1
