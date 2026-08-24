"""PostgreSQL provenance for connected-mailbox listing."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ConnectorAccountNotFoundError
from app.application.services.connected_mailbox_listing import (
    ConnectedMailboxMessageListingService,
)
from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import CommunicationCapability
from app.domain.interfaces.connector_account_repository import NewConnectorAccount
from app.infrastructure.connectors.fake.connector import FakeCommunicationConnector
from app.infrastructure.storage.models import Analysis, WorkflowAction
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork
from app.schemas.mailbox import ConnectorAccountMessageListQuery
from tests.support.connector_factory import StaticCommunicationConnectorFactory

_ISSUER = "https://issuer.example.invalid/"
_OWNER_SUBJECT = "mailbox-list-owner"
_OTHER_SUBJECT = "mailbox-list-other"


def _principal(subject: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=subject,
        permissions=frozenset({"communications:read"}),
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
                external_account_id="gmail-mailbox-list-pg-001",
                credential_ref="cred-gmail-list-pg-001",
                granted_capabilities=(CommunicationCapability.MAIL_READ,),
            )
        )
        uow.commit()
    return user_id, account


def _build_service(
    session_factory: sessionmaker,
    connector: FakeCommunicationConnector,
) -> tuple[ConnectedMailboxMessageListingService, StaticCommunicationConnectorFactory]:
    uow_factory = _uow_factory(session_factory)
    factory = StaticCommunicationConnectorFactory(connector)
    service = ConnectedMailboxMessageListingService(
        IdentityResolver(uow_factory),
        uow_factory,
        factory,
    )
    return service, factory


def test_mailbox_listing_does_not_persist_messages(
    session_factory: sessionmaker,
) -> None:
    """Owned mailbox listing returns metadata without creating analysis rows."""
    _user_id, account = _seed_owner_with_gmail_account(session_factory)
    connector = FakeCommunicationConnector()
    raw = connector.fetch_message("fake-msg-001")
    service, factory = _build_service(session_factory, connector)

    response = service.list_messages(
        _principal(_OWNER_SUBJECT),
        account.id,
        ConnectorAccountMessageListQuery(page_size=1),
    )

    assert factory.calls == 1
    assert response.items[0].provider_message_id == "fake-msg-001"
    assert raw.body not in repr(response.model_dump())
    with session_factory() as session:
        analysis_count = session.scalar(select(func.count()).select_from(Analysis))
        action_count = session.scalar(select(func.count()).select_from(WorkflowAction))
    assert analysis_count == 0
    assert action_count == 0


def test_cross_user_mailbox_list_does_not_persist(
    session_factory: sessionmaker,
) -> None:
    """Another user's account id must not create analysis or workflow rows."""
    _, account = _seed_owner_with_gmail_account(session_factory)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.identity_repository.create_user_with_external_identity(
            _ISSUER,
            _OTHER_SUBJECT,
        )
        uow.commit()
    connector = FakeCommunicationConnector()
    service, factory = _build_service(session_factory, connector)

    with pytest.raises(ConnectorAccountNotFoundError):
        service.list_messages(
            _principal(_OTHER_SUBJECT),
            account.id,
            ConnectorAccountMessageListQuery(),
        )
    assert factory.calls == 0
    with session_factory() as session:
        analysis_count = session.scalar(select(func.count()).select_from(Analysis))
        action_count = session.scalar(select(func.count()).select_from(WorkflowAction))
    assert analysis_count == 0
    assert action_count == 0
