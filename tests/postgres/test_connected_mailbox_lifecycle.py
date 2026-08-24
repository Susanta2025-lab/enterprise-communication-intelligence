"""PostgreSQL lifecycle mutation for connected-mailbox list and analyze."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import sessionmaker

from app.application.exceptions import (
    ConnectedMailboxNotAvailableError,
    ConnectorAccountNotFoundError,
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
    ServiceUnavailableError,
)
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces import CommunicationConnector, ConnectorMessageQuery, MessagePage
from app.domain.interfaces.connector_account_repository import (
    ConnectorAccountRecord,
    NewConnectorAccount,
)
from app.domain.models import CommunicationMessage
from app.infrastructure.connectors.fake.connector import FakeCommunicationConnector
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork
from app.providers.mock.provider import MockAIProvider
from app.schemas.mailbox import ConnectorAccountMessageListQuery
from tests.support.connector_factory import StaticCommunicationConnectorFactory

_ISSUER = "https://issuer.example.invalid/"
_OWNER_SUBJECT = "mailbox-lifecycle-owner"
_OTHER_SUBJECT = "mailbox-lifecycle-other"
_PROVIDER_MESSAGE_ID = "fake-msg-001"
_GRANTS = (
    CommunicationCapability.MAIL_READ,
    CommunicationCapability.MAIL_SEND,
)
_LOCATOR = "cred-gmail-lifecycle-pg-001"
_EXTERNAL_ID = "gmail-mailbox-lifecycle-pg-001"


class _ReauthFactory(StaticCommunicationConnectorFactory):
    def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
        super().create_for_account(account)
        raise CommunicationCredentialReauthorizationRequiredError()


class _AuthFailingConnector(FakeCommunicationConnector):
    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        raise ConnectorAuthenticationError()

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        raise ConnectorAuthenticationError()


class _TransientRefreshConnector(FakeCommunicationConnector):
    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        raise CommunicationCredentialUnavailableError()

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        raise CommunicationCredentialUnavailableError()


class _DisconnectThenReauthConnector(FakeCommunicationConnector):
    def __init__(self, session_factory: sessionmaker, account_id, user_id) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._account_id = account_id
        self._user_id = user_id

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        with SqlAlchemyPersistenceUnitOfWork(self._session_factory) as uow:
            disconnected = uow.connector_accounts.disconnect_owned(
                self._account_id,
                self._user_id,
            )
            assert disconnected is not None
            uow.commit()
        raise CommunicationCredentialReauthorizationRequiredError()


def _principal(subject: str, *permissions: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=subject,
        permissions=frozenset(permissions or ("communications:read",)),
    )


def _uow_factory(
    session_factory: sessionmaker,
) -> Callable[[], SqlAlchemyPersistenceUnitOfWork]:
    return lambda: SqlAlchemyPersistenceUnitOfWork(session_factory)


def _seed_owner_with_gmail_account(session_factory: sessionmaker):
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        user_id = uow.identity_repository.create_user_with_external_identity(
            _ISSUER,
            _OWNER_SUBJECT,
        )
        account = uow.connector_accounts.create(
            NewConnectorAccount(
                user_id=user_id,
                provider="gmail",
                external_account_id=_EXTERNAL_ID,
                credential_ref=_LOCATOR,
                granted_capabilities=_GRANTS,
            )
        )
        uow.commit()
    return user_id, account


def _reload(session_factory: sessionmaker, account_id, user_id) -> ConnectorAccountRecord:
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        stored = uow.connector_accounts.get_owned(account_id, user_id)
        assert stored is not None
        return stored


def _listing_service(
    session_factory: sessionmaker,
    factory: StaticCommunicationConnectorFactory,
) -> ConnectedMailboxMessageListingService:
    uow_factory = _uow_factory(session_factory)
    return ConnectedMailboxMessageListingService(
        IdentityResolver(uow_factory),
        uow_factory,
        factory,
    )


def _analysis_service(
    session_factory: sessionmaker,
    factory: StaticCommunicationConnectorFactory,
) -> ConnectedMailboxAnalysisService:
    uow_factory = _uow_factory(session_factory)
    identity = IdentityResolver(uow_factory)
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(MockAIProvider()),
        principal=_principal(_OWNER_SUBJECT, "communications:read", "communications:analyze"),
        identity_resolver=identity,
        history_service=AnalysisHistoryService(uow_factory),
    )
    return ConnectedMailboxAnalysisService(
        identity,
        uow_factory,
        factory,
        workflow,
    )


def test_permanent_refresh_during_list_marks_reauth_required(
    session_factory: sessionmaker,
) -> None:
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    factory = _ReauthFactory(FakeCommunicationConnector())
    service = _listing_service(session_factory, factory)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.list_messages(
            _principal(_OWNER_SUBJECT, "communications:read"),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    stored = _reload(session_factory, account.id, user_id)
    assert stored.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert stored.credential_ref == _LOCATOR
    assert stored.granted_capabilities == _GRANTS
    assert stored.external_account_id == _EXTERNAL_ID
    assert factory.calls == 1


def test_permanent_refresh_during_analyze_marks_reauth_required(
    session_factory: sessionmaker,
) -> None:
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    factory = _ReauthFactory(FakeCommunicationConnector())
    service = _analysis_service(session_factory, factory)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.analyze(
            _principal(_OWNER_SUBJECT, "communications:read", "communications:analyze"),
            account.id,
            _PROVIDER_MESSAGE_ID,
        )

    stored = _reload(session_factory, account.id, user_id)
    assert stored.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert stored.credential_ref == _LOCATOR
    assert stored.granted_capabilities == _GRANTS
    assert stored.external_account_id == _EXTERNAL_ID
    assert factory.calls == 1


def test_transient_refresh_keeps_active(session_factory: sessionmaker) -> None:
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    factory = StaticCommunicationConnectorFactory(_TransientRefreshConnector())
    service = _listing_service(session_factory, factory)

    with pytest.raises(ServiceUnavailableError):
        service.list_messages(
            _principal(_OWNER_SUBJECT, "communications:read"),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    stored = _reload(session_factory, account.id, user_id)
    assert stored.status is ConnectorAccountStatus.ACTIVE
    assert stored.credential_ref == _LOCATOR
    assert stored.granted_capabilities == _GRANTS


def test_mailbox_http_401_keeps_active(session_factory: sessionmaker) -> None:
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    factory = StaticCommunicationConnectorFactory(_AuthFailingConnector())
    listing = _listing_service(session_factory, factory)
    analysis = _analysis_service(session_factory, factory)

    with pytest.raises(ServiceUnavailableError):
        listing.list_messages(
            _principal(_OWNER_SUBJECT, "communications:read"),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )
    with pytest.raises(ServiceUnavailableError):
        analysis.analyze(
            _principal(_OWNER_SUBJECT, "communications:read", "communications:analyze"),
            account.id,
            _PROVIDER_MESSAGE_ID,
        )

    stored = _reload(session_factory, account.id, user_id)
    assert stored.status is ConnectorAccountStatus.ACTIVE
    assert stored.credential_ref == _LOCATOR


def test_cross_user_does_not_mutate(session_factory: sessionmaker) -> None:
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.identity_repository.create_user_with_external_identity(_ISSUER, _OTHER_SUBJECT)
        uow.commit()
    factory = _ReauthFactory(FakeCommunicationConnector())
    service = _listing_service(session_factory, factory)

    with pytest.raises(ConnectorAccountNotFoundError):
        service.list_messages(
            _principal(_OTHER_SUBJECT, "communications:read"),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    assert factory.calls == 0
    stored = _reload(session_factory, account.id, user_id)
    assert stored.status is ConnectorAccountStatus.ACTIVE
    assert stored.credential_ref == _LOCATOR
    assert stored.granted_capabilities == _GRANTS


def test_reauth_required_account_fails_before_factory(
    session_factory: sessionmaker,
) -> None:
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        marked = uow.connector_accounts.mark_reauth_required_owned(account.id, user_id)
        assert marked is not None
        uow.commit()
    factory = StaticCommunicationConnectorFactory(FakeCommunicationConnector())
    service = _listing_service(session_factory, factory)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.list_messages(
            _principal(_OWNER_SUBJECT, "communications:read"),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    assert factory.calls == 0
    stored = _reload(session_factory, account.id, user_id)
    assert stored.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert stored.credential_ref == _LOCATOR
    assert stored.granted_capabilities == _GRANTS


def test_disconnect_before_reauth_mutation_is_not_resurrected(
    session_factory: sessionmaker,
) -> None:
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    connector = _DisconnectThenReauthConnector(session_factory, account.id, user_id)
    factory = StaticCommunicationConnectorFactory(connector)
    service = _listing_service(session_factory, factory)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.list_messages(
            _principal(_OWNER_SUBJECT, "communications:read"),
            account.id,
            ConnectorAccountMessageListQuery(page_size=10),
        )

    stored = _reload(session_factory, account.id, user_id)
    assert stored.status is ConnectorAccountStatus.DISCONNECTED
    assert stored.credential_ref is None
    assert stored.granted_capabilities is None
    assert stored.external_account_id == _EXTERNAL_ID
    assert factory.calls == 1
