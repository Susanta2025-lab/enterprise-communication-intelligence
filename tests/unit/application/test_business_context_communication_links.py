"""Application tests for BusinessContext communication provenance association."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    AnalysisNotFoundError,
    BusinessContextCommunicationLinkConflictError,
    BusinessContextCommunicationLinkNotFoundError,
    BusinessContextNotFoundError,
    ConnectorAccountNotFoundError,
)
from app.application.services.business_context_communication_links import (
    BusinessContextCommunicationLinkService,
)
from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import (
    ApplicationRole,
    AssociationSource,
    BusinessContextStatus,
    BusinessContextType,
    CommunicationCapability,
    ConnectorAccountStatus,
)
from app.domain.models.business_context import BusinessContext
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_analysis_record,
    sample_connector_account,
)

_ISSUER = "https://issuer.example.invalid/"
_SUBJECT_A = "user-a"
_SUBJECT_B = "user-b"
_SUBJECT_OWNER = "platform-owner"


def _principal(subject: str = _SUBJECT_A) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=subject,
        permissions=frozenset(
            {
                "communications:read",
                "communications:analyze",
            }
        ),
    )


def _context(owner_user_id: UUID, *, title: str = "Matter") -> BusinessContext:
    return BusinessContext(
        owner_user_id=owner_user_id,
        type=BusinessContextType.MATTER,
        title=title,
    )


def _service(
    uow: InMemoryUnitOfWork,
) -> BusinessContextCommunicationLinkService:
    factory = UnitOfWorkFactory(uow)
    return BusinessContextCommunicationLinkService(
        IdentityResolver(factory),
        factory,
    )


def _seed_users() -> tuple[UUID, UUID, UUID, InMemoryUnitOfWork]:
    user_a = uuid4()
    user_b = uuid4()
    owner = uuid4()
    uow = InMemoryUnitOfWork(
        identities={
            (_ISSUER, _SUBJECT_A): user_a,
            (_ISSUER, _SUBJECT_B): user_b,
            (_ISSUER, _SUBJECT_OWNER): owner,
        },
        application_roles={
            user_a: ApplicationRole.USER.value,
            user_b: ApplicationRole.USER.value,
            owner: ApplicationRole.OWNER.value,
        },
    )
    return user_a, user_b, owner, uow


def test_associate_creates_manual_owned_link() -> None:
    """Valid owned context + owned connector create a manual provenance link."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)

    link = service.associate(
        _principal(),
        context.id,
        connector.id,
        "gmail-msg-1",
    )

    assert link.owner_user_id == user_a
    assert link.associated_by_user_id == user_a
    assert link.association_source is AssociationSource.MANUAL
    assert link.connector_account_id == connector.id
    assert link.provider_message_id == "gmail-msg-1"
    assert link.analysis_id is None
    assert link.id in uow.business_context_communication_link_store


def test_associate_allows_disconnected_owned_connector() -> None:
    """Association requires ownership only; connector usability is not required."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(
        user_a,
        status=ConnectorAccountStatus.DISCONNECTED,
        credential_ref=None,
        granted_capabilities=None,
    )
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)

    link = service.associate(
        _principal(),
        context.id,
        connector.id,
        "msg-disconnected",
    )
    assert link.connector_account_id == connector.id


def test_associate_rejects_foreign_connector_even_with_matching_message_id() -> None:
    """User A cannot link User A context to User B connector provenance."""
    user_a, user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    foreign = sample_connector_account(user_b)
    uow.connector_account_store[foreign.id] = foreign
    service = _service(uow)

    with pytest.raises(ConnectorAccountNotFoundError):
        service.associate(_principal(), context.id, foreign.id, "shared-looking-id")


def test_associate_rejects_foreign_context() -> None:
    """User A cannot associate against User B's BusinessContext."""
    user_a, user_b, _owner, uow = _seed_users()
    foreign_context = uow.business_contexts.add(_context(user_b))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)

    with pytest.raises(BusinessContextNotFoundError):
        service.associate(_principal(), foreign_context.id, connector.id, "msg-1")


def test_platform_owner_does_not_bypass_ownership() -> None:
    """application_role=owner does not grant cross-user association rights."""
    user_a, _user_b, owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)

    with pytest.raises(BusinessContextNotFoundError):
        service.associate(
            _principal(_SUBJECT_OWNER),
            context.id,
            connector.id,
            "msg-owner-bypass",
        )
    assert owner in uow.application_roles
    assert uow.application_roles[owner] == ApplicationRole.OWNER.value


def test_duplicate_association_conflicts() -> None:
    """Duplicate context+connector+message associations raise conflict."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)
    service.associate(_principal(), context.id, connector.id, "msg-dup")

    with pytest.raises(BusinessContextCommunicationLinkConflictError):
        service.associate(_principal(), context.id, connector.id, "msg-dup")


def test_many_to_many_cardinality() -> None:
    """One message may join many contexts; one context may hold many messages."""
    user_a, _user_b, _owner, uow = _seed_users()
    first = uow.business_contexts.add(_context(user_a, title="First"))
    second = uow.business_contexts.add(_context(user_a, title="Second"))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)

    service.associate(_principal(), first.id, connector.id, "shared-msg")
    service.associate(_principal(), second.id, connector.id, "shared-msg")
    service.associate(_principal(), first.id, connector.id, "other-msg")

    listed = service.list_for_context(_principal(), first.id)
    assert {item.provider_message_id for item in listed} == {"shared-msg", "other-msg"}
    listed_second = service.list_for_context(_principal(), second.id)
    assert [item.provider_message_id for item in listed_second] == ["shared-msg"]


def test_archived_context_rejects_new_association_but_allows_remove() -> None:
    """Archived contexts forbid new links; existing links remain removable."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)
    link = service.associate(_principal(), context.id, connector.id, "msg-arch")

    context.archive()
    uow.business_contexts.save_owned(context)
    assert context.status is BusinessContextStatus.ARCHIVED

    with pytest.raises(BusinessContextCommunicationLinkConflictError):
        service.associate(_principal(), context.id, connector.id, "msg-new")

    readable = service.list_for_context(_principal(), context.id)
    assert [item.id for item in readable] == [link.id]

    service.remove(_principal(), context.id, link.id)
    assert service.list_for_context(_principal(), context.id) == []


def test_restore_allows_association_again() -> None:
    """Restored contexts accept new associations again."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)
    context.archive()
    uow.business_contexts.save_owned(context)
    context.restore()
    uow.business_contexts.save_owned(context)

    link = service.associate(_principal(), context.id, connector.id, "msg-restored")
    assert link.provider_message_id == "msg-restored"


def test_foreign_analysis_cannot_be_smuggled() -> None:
    """Optional analysis_id must be owned and match mailbox provenance."""
    user_a, user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    foreign_analysis = sample_analysis_record(
        user_b,
        extra={
            "connector_account_id": connector.id,
            "message_id": "msg-1",
        },
    )
    uow.analyses[foreign_analysis.id] = foreign_analysis
    mismatched = sample_analysis_record(
        user_a,
        extra={
            "connector_account_id": connector.id,
            "message_id": "other-msg",
        },
    )
    uow.analyses[mismatched.id] = mismatched
    matching = sample_analysis_record(
        user_a,
        extra={
            "connector_account_id": connector.id,
            "message_id": "msg-1",
        },
    )
    uow.analyses[matching.id] = matching
    service = _service(uow)

    with pytest.raises(AnalysisNotFoundError):
        service.associate(
            _principal(),
            context.id,
            connector.id,
            "msg-1",
            analysis_id=foreign_analysis.id,
        )
    with pytest.raises(AnalysisNotFoundError):
        service.associate(
            _principal(),
            context.id,
            connector.id,
            "msg-1",
            analysis_id=mismatched.id,
        )

    link = service.associate(
        _principal(),
        context.id,
        connector.id,
        "msg-1",
        analysis_id=matching.id,
    )
    assert link.analysis_id == matching.id


def test_associate_without_analysis_is_allowed() -> None:
    """Messages without AI analysis remain associable."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(
        user_a,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    uow.connector_account_store[connector.id] = connector
    service = _service(uow)
    link = service.associate(_principal(), context.id, connector.id, "no-analysis")
    assert link.analysis_id is None


def test_remove_does_not_delete_connector_or_analysis() -> None:
    """Disassociation removes only the link row."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    analysis = sample_analysis_record(
        user_a,
        extra={
            "connector_account_id": connector.id,
            "message_id": "msg-keep",
        },
    )
    uow.analyses[analysis.id] = analysis
    service = _service(uow)
    link = service.associate(
        _principal(),
        context.id,
        connector.id,
        "msg-keep",
        analysis_id=analysis.id,
    )

    service.remove(_principal(), context.id, link.id)

    assert connector.id in uow.connector_account_store
    assert analysis.id in uow.analyses
    assert link.id not in uow.business_context_communication_link_store


def test_remove_unknown_link_is_not_found() -> None:
    """Unknown or cross-context links raise not-found."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    service = _service(uow)
    with pytest.raises(BusinessContextCommunicationLinkNotFoundError):
        service.remove(_principal(), context.id, uuid4())


def test_associate_does_not_call_mailbox_or_attachment_services() -> None:
    """Association is identifier-only; no mailbox/attachment/AI side effects."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = uow.business_contexts.add(_context(user_a))
    connector = sample_connector_account(user_a)
    uow.connector_account_store[connector.id] = connector
    factory = UnitOfWorkFactory(uow)
    service = BusinessContextCommunicationLinkService(IdentityResolver(factory), factory)

    mailbox = MagicMock()
    attachment = MagicMock()
    ai = MagicMock()
    service._mailbox = mailbox  # type: ignore[attr-defined]
    service._attachment = attachment  # type: ignore[attr-defined]
    service._ai = ai  # type: ignore[attr-defined]

    service.associate(_principal(), context.id, connector.id, "msg-no-io")

    mailbox.assert_not_called()
    attachment.assert_not_called()
    ai.assert_not_called()


def test_service_module_has_no_provider_or_attachment_imports() -> None:
    """Source-level regression: associate path must not import retrieve stacks."""
    import app.application.services.business_context_communication_links as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "connected_mailbox" not in source
    assert "attachment_inspection" not in source
    assert "attachment_analysis" not in source
    assert "CommunicationConnector" not in source
    assert "retrieve_attachment" not in source
    assert "AIProvider" not in source
    assert "fastapi" not in source.lower()
