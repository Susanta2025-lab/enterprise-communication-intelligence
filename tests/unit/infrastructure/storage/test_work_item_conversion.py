"""Portable conversion service transaction tests, also executed on PostgreSQL."""

import pytest
from sqlalchemy import delete

from app.application.services.identity import IdentityResolver
from app.application.services.work_items import WorkItemService
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.security import AuthenticatedPrincipal
from app.domain.exceptions import WorkItemPermissionError
from app.domain.models.business_work_item import WorkItemCommand
from app.domain.models.work_item_provenance import CandidateQuery
from app.infrastructure.storage.models import AttachmentAnalysisRow, ConnectorAccount, User
from app.infrastructure.storage.repositories.business_work_item import (
    SqlAlchemyBusinessWorkItemRepository,
)
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork
from app.schemas.work_items import WorkItemFromAnalysisRequest
from tests.integration.test_work_item_conversion import seed
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION
from tests.unit.infrastructure.storage.test_business_work_item_repository import counts


def setup_conversion(session_factory):
    def factory():
        return SqlAlchemyPersistenceUnitOfWork(session_factory)
    source = seed((None, None, session_factory, factory), kind="xlsx", length=300)
    principal = AuthenticatedPrincipal(
        TEST_ISSUER, "user-a-subject", frozenset({TEST_PERMISSION, "communications:read"})
    )
    service = WorkItemService(IdentityResolver(factory), factory)
    query = CandidateQuery(source_kind=source[2], source_id=source[1])
    candidate = service.candidates(principal, query)[0].candidate
    request = WorkItemFromAnalysisRequest(
        creation_key="key",
        kind="action",
        title="Reviewed",
        due={"kind": "none"},
        confirmed=True,
        candidate=candidate.model_dump(),
    )
    return service, principal, request, source


def test_service_retention_confirmation_and_erasure(session_factory):
    service, principal, request, source = setup_conversion(session_factory)
    created = service.create_verified(principal, request).item
    assert created.creation_request_hash == request.request_hash()
    assert created.confirmed_by_user_id == source[0]
    assert created.confirmed_at == created.created_at
    service.mutate(
        principal,
        created.id,
        WorkItemCommand(operation="status", expected_version=1, status="completed"),
    )
    service.mutate(principal, created.id, WorkItemCommand(operation="archive", expected_version=2))
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.connector_accounts.disconnect_owned(source[3], source[0])
        uow.commit()
    replay = service.create_verified(principal, request)
    assert replay.replayed and replay.item.version == 3 and replay.item.status == "completed"
    with session_factory() as session:
        session.execute(delete(AttachmentAnalysisRow))
        session.execute(delete(ConnectorAccount))
        session.commit()
    assert service.create_verified(principal, request).replayed
    _, sources = service.detail(principal, created.id)
    assert sources[0].availability == "unavailable"
    analyze_only = AuthenticatedPrincipal(
        principal.issuer, principal.subject, frozenset({TEST_PERMISSION})
    )
    with pytest.raises(WorkItemPermissionError):
        service.create_verified(analyze_only, request)
    with session_factory() as session:
        assert counts(session) == (1, 1, 3)
        session.execute(delete(User))
        session.commit()
        assert counts(session) == (0, 0, 0)


@pytest.mark.parametrize("failure", ["event", "commit"])
def test_conversion_failure_atomic(session_factory, monkeypatch, failure):
    service, principal, request, _ = setup_conversion(session_factory)

    def fail(*_args):
        raise PersistenceError("secret persistence detail")

    if failure == "event":
        monkeypatch.setattr(SqlAlchemyBusinessWorkItemRepository, "_append_events", fail)
    else:
        monkeypatch.setattr(SqlAlchemyPersistenceUnitOfWork, "commit", fail)
    with pytest.raises(ServiceUnavailableError, match="Persistence is currently unavailable"):
        service.create_verified(principal, request)
    with session_factory() as session:
        assert counts(session) == (0, 0, 0)
