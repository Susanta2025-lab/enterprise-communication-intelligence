"""PostgreSQL provenance for connected-mailbox analysis."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ConnectorAccountNotFoundError
from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.connected_mailbox_analysis import (
    ConnectedMailboxAnalysisService,
)
from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import CommunicationCapability
from app.domain.interfaces.connector_account_repository import NewConnectorAccount
from app.infrastructure.connectors.fake.connector import FakeCommunicationConnector
from app.infrastructure.storage.models import Analysis, WorkflowAction
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork
from app.providers.mock.provider import MockAIProvider
from tests.support.connector_factory import StaticCommunicationConnectorFactory

_ISSUER = "https://issuer.example.invalid/"
_OWNER_SUBJECT = "mailbox-analyze-owner"
_OTHER_SUBJECT = "mailbox-analyze-other"
_PROVIDER_MESSAGE_ID = "fake-msg-001"


def _principal(subject: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=subject,
        permissions=frozenset({"communications:read", "communications:analyze"}),
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
                external_account_id="gmail-mailbox-pg-001",
                credential_ref="cred-gmail-pg-001",
                granted_capabilities=(CommunicationCapability.MAIL_READ,),
            )
        )
        uow.commit()
    return user_id, account


def _build_service(
    session_factory: sessionmaker,
    connector: FakeCommunicationConnector,
) -> tuple[ConnectedMailboxAnalysisService, StaticCommunicationConnectorFactory]:
    uow_factory = _uow_factory(session_factory)
    identity = IdentityResolver(uow_factory)
    history = AnalysisHistoryService(uow_factory)
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(MockAIProvider()),
        principal=_principal(_OWNER_SUBJECT),
        identity_resolver=identity,
        history_service=history,
    )
    factory = StaticCommunicationConnectorFactory(connector)
    service = ConnectedMailboxAnalysisService(
        identity,
        uow_factory,
        factory,
        workflow,
    )
    return service, factory


def test_mailbox_analysis_persists_owned_provenance(
    session_factory: sessionmaker,
) -> None:
    """Owned mailbox analyze stores message id and connector account id, not raw body."""
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    connector = FakeCommunicationConnector()
    raw_message = connector.fetch_message(_PROVIDER_MESSAGE_ID)
    service, factory = _build_service(session_factory, connector)

    outcome = service.analyze(
        _principal(_OWNER_SUBJECT),
        account.id,
        _PROVIDER_MESSAGE_ID,
    )

    assert factory.calls == 1
    assert outcome.analysis_id is not None
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        stored = uow.analysis_repository.get_by_id_for_user(
            outcome.analysis_id,
            user_id,
        )
        uow.commit()
    assert stored is not None
    assert stored.user_id == user_id
    assert stored.message_id == _PROVIDER_MESSAGE_ID
    assert stored.connector_account_id == account.id
    assert stored.summary_text
    assert stored.summary_text != raw_message.body
    assert raw_message.body not in stored.summary_text
    assert "body" not in Analysis.__table__.columns
    with session_factory() as session:
        action_count = session.scalar(select(func.count()).select_from(WorkflowAction))
    assert action_count == 0


def test_cross_user_mailbox_analyze_does_not_persist(
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
        service.analyze(
            _principal(_OTHER_SUBJECT),
            account.id,
            _PROVIDER_MESSAGE_ID,
        )
    assert factory.calls == 0
    with session_factory() as session:
        analysis_count = session.scalar(select(func.count()).select_from(Analysis))
        action_count = session.scalar(select(func.count()).select_from(WorkflowAction))
    assert analysis_count == 0
    assert action_count == 0
