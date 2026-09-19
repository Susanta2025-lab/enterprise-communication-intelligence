"""Unit tests for ContextTimelineService read model."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.exceptions import BusinessContextNotFoundError
from app.application.services.business_contexts import BusinessContextService
from app.application.services.context_timeline import ContextTimelineService
from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import (
    ApplicationRole,
    AssociationSource,
    BusinessContextStatus,
    BusinessContextType,
    ContextTimelineEventType,
    WorkflowActionStatus,
    WorkflowActionType,
)
from app.domain.interfaces.attachment_analysis_repository import AttachmentAnalysisRecord
from app.domain.models.business_context_communication_link import (
    BusinessContextCommunicationLink,
)
from app.domain.models.workflow import WorkflowAction
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_analysis_record,
)

_ISSUER = "https://issuer.example.invalid/"
_SUBJECT_A = "user-a"
_SUBJECT_B = "user-b"
_SUBJECT_OWNER = "platform-owner"


def _principal(subject: str = _SUBJECT_A) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=subject,
        permissions=frozenset({"communications:analyze"}),
    )


def _timeline_service(uow: InMemoryUnitOfWork) -> ContextTimelineService:
    factory = UnitOfWorkFactory(uow)
    return ContextTimelineService(IdentityResolver(factory), factory)


def _context_service(uow: InMemoryUnitOfWork) -> BusinessContextService:
    factory = UnitOfWorkFactory(uow)
    return BusinessContextService(IdentityResolver(factory), factory)


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


def _add_link(
    uow: InMemoryUnitOfWork,
    *,
    user_id: UUID,
    context_id: UUID,
    connector_account_id: UUID,
    provider_message_id: str,
    associated_at: datetime,
    link_id: UUID | None = None,
) -> BusinessContextCommunicationLink:
    link = BusinessContextCommunicationLink(
        id=link_id or uuid4(),
        business_context_id=context_id,
        owner_user_id=user_id,
        connector_account_id=connector_account_id,
        provider_message_id=provider_message_id,
        associated_by_user_id=user_id,
        associated_at=associated_at,
        association_source=AssociationSource.MANUAL,
    )
    uow.business_context_communication_link_store[link.id] = link
    return link


def test_owned_context_empty_timeline_includes_created_only() -> None:
    """Owned context with no links yields only the context_created event."""
    _user_a, _user_b, _owner, uow = _seed_users()
    context = _context_service(uow).create(
        _principal(),
        type=BusinessContextType.PROJECT,
        title="Empty",
    )
    service = _timeline_service(uow)

    entries = service.list_timeline(_principal(), context.id)

    assert len(entries) == 1
    assert entries[0].type is ContextTimelineEventType.CONTEXT_CREATED
    assert entries[0].id == f"context_created:{context.id}"


def test_foreign_context_is_not_found() -> None:
    """Cross-user timeline access is indistinguishable from missing."""
    _user_a, _user_b, _owner, uow = _seed_users()
    context = _context_service(uow).create(
        _principal(),
        type=BusinessContextType.CASE,
        title="A only",
    )
    service = _timeline_service(uow)

    with pytest.raises(BusinessContextNotFoundError):
        service.list_timeline(_principal(_SUBJECT_B), context.id)


def test_platform_owner_does_not_bypass_ownership() -> None:
    """Platform Owner role never widens timeline ownership."""
    _user_a, _user_b, _owner, uow = _seed_users()
    context = _context_service(uow).create(
        _principal(),
        type=BusinessContextType.MATTER,
        title="Owned by A",
    )
    service = _timeline_service(uow)

    with pytest.raises(BusinessContextNotFoundError):
        service.list_timeline(_principal(_SUBJECT_OWNER), context.id)


def test_association_and_analysis_projection() -> None:
    """Communication links and mailbox analyses project into the timeline."""
    user_a, user_b, _owner, uow = _seed_users()
    context = _context_service(uow).create(
        _principal(),
        type=BusinessContextType.CLIENT,
        title="Client",
    )
    connector_id = uuid4()
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    link = _add_link(
        uow,
        user_id=user_a,
        context_id=context.id,
        connector_account_id=connector_id,
        provider_message_id="msg-1",
        associated_at=t0 + timedelta(hours=1),
    )
    analysis = replace(
        sample_analysis_record(
            user_a,
            analysis_id=uuid4(),
            extra={
                "connector_account_id": connector_id,
                "message_id": "msg-1",
            },
        ),
        created_at=t0 + timedelta(hours=2),
    )
    uow.analyses[analysis.id] = analysis
    orphan = sample_analysis_record(
        user_a,
        extra={"connector_account_id": None, "message_id": None},
    )
    uow.analyses[orphan.id] = orphan
    foreign = sample_analysis_record(
        user_b,
        extra={"connector_account_id": connector_id, "message_id": "msg-1"},
    )
    uow.analyses[foreign.id] = foreign

    entries = _timeline_service(uow).list_timeline(_principal(), context.id)
    types = [item.type for item in entries]
    ids = [item.id for item in entries]

    assert ContextTimelineEventType.COMMUNICATION_ASSOCIATED in types
    assert ContextTimelineEventType.ANALYSIS_COMPLETED in types
    assert f"association:{link.id}" in ids
    assert f"analysis:{analysis.id}" in ids
    assert f"analysis:{orphan.id}" not in ids
    assert f"analysis:{foreign.id}" not in ids


def test_attachment_analysis_and_workflow_projection() -> None:
    """Attachment analyses and workflow transitions project when provenance matches."""
    user_a, user_b, _owner, uow = _seed_users()
    context = _context_service(uow).create(
        _principal(),
        type=BusinessContextType.TRANSACTION,
        title="Txn",
    )
    connector_id = uuid4()
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)
    _add_link(
        uow,
        user_id=user_a,
        context_id=context.id,
        connector_account_id=connector_id,
        provider_message_id="msg-w",
        associated_at=t0,
    )
    attachment = AttachmentAnalysisRecord(
        id=uuid4(),
        user_id=user_a,
        created_at=t0 + timedelta(minutes=30),
        updated_at=t0 + timedelta(minutes=30),
        connector_account_id=connector_id,
        provider_message_id="msg-w",
        provider_attachment_id="att-1",
        filename="brief.pdf",
        media_type="application/pdf",
        kind="document",
        extracted_content_status="extracted",
        truncated=False,
        warnings=[],
        reported_size=10,
        page_count=1,
        character_count=100,
        summary_text="Summary",
        summary_confidence=0.9,
        priority="medium",
        category="general",
        action_items=[],
        provider="mock",
        request_id=None,
    )
    uow.attachment_analysis_store[attachment.id] = attachment
    foreign_attachment = replace(attachment, id=uuid4(), user_id=user_b)
    uow.attachment_analysis_store[foreign_attachment.id] = foreign_attachment

    workflow = WorkflowAction.rehydrate(
        id=uuid4(),
        action_type=WorkflowActionType.REPLY,
        analysis_id=uuid4(),
        owner_user_id=user_a,
        proposed_reply_body="Hello",
        status=WorkflowActionStatus.EXECUTED,
        created_at=t0 + timedelta(hours=1),
        approved_at=t0 + timedelta(hours=2),
        approved_reply_body="Hello",
        executed_at=t0 + timedelta(hours=3),
        connector_account_id=connector_id,
        provider_message_id="msg-w",
    )
    uow.workflow_action_store[workflow.id] = workflow
    bare = WorkflowAction(
        action_type=WorkflowActionType.REPLY,
        analysis_id=uuid4(),
        owner_user_id=user_a,
        proposed_reply_body="Bare",
        status=WorkflowActionStatus.PENDING,
    )
    uow.workflow_action_store[bare.id] = bare

    entries = _timeline_service(uow).list_timeline(_principal(), context.id)
    ids = {item.id for item in entries}
    types = {item.type for item in entries}

    assert ContextTimelineEventType.ATTACHMENT_ANALYSIS_COMPLETED in types
    assert f"attachment_analysis:{attachment.id}" in ids
    assert f"attachment_analysis:{foreign_attachment.id}" not in ids
    assert f"workflow:{workflow.id}:pending" in ids
    assert f"workflow:{workflow.id}:approved" in ids
    assert f"workflow:{workflow.id}:executed" in ids
    assert f"workflow:{bare.id}:pending" not in ids


def test_ordering_stable_ids_and_pagination() -> None:
    """Timeline orders by occurred_at DESC then id ASC with stable ids and pages."""
    user_a, _user_b, _owner, uow = _seed_users()
    context = _context_service(uow).create(
        _principal(),
        type=BusinessContextType.OTHER,
        title="Order",
    )
    # Force created_at older than association events so associations sort first.
    stored = uow.business_context_store[context.id]
    stored.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    uow.business_context_store[context.id] = stored

    connector_id = uuid4()
    shared = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    link_a = _add_link(
        uow,
        user_id=user_a,
        context_id=context.id,
        connector_account_id=connector_id,
        provider_message_id="m-a",
        associated_at=shared,
        link_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )
    link_b = _add_link(
        uow,
        user_id=user_a,
        context_id=context.id,
        connector_account_id=connector_id,
        provider_message_id="m-b",
        associated_at=shared,
        link_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )
    service = _timeline_service(uow)

    first = service.list_timeline(_principal(), context.id, limit=2, offset=0)
    second = service.list_timeline(_principal(), context.id, limit=2, offset=2)
    again = service.list_timeline(_principal(), context.id, limit=2, offset=0)

    assert [item.id for item in first] == [item.id for item in again]
    assert first[0].id == f"association:{link_a.id}"
    assert first[1].id == f"association:{link_b.id}"
    assert len(first) == 2
    assert len(second) == 1
    assert second[0].type is ContextTimelineEventType.CONTEXT_CREATED


def test_archived_context_emits_current_archive_event_only() -> None:
    """Archived contexts expose current archive state; restore is not fabricated."""
    _user_a, _user_b, _owner, uow = _seed_users()
    contexts = _context_service(uow)
    context = contexts.create(
        _principal(),
        type=BusinessContextType.ACCOUNT,
        title="Lifecycle",
    )
    archived = contexts.archive(_principal(), context.id)
    assert archived.status is BusinessContextStatus.ARCHIVED
    assert archived.archived_at is not None

    entries = _timeline_service(uow).list_timeline(_principal(), context.id)
    types = [item.type for item in entries]
    assert ContextTimelineEventType.CONTEXT_CREATED in types
    assert ContextTimelineEventType.CONTEXT_ARCHIVED in types
    assert types.count(ContextTimelineEventType.CONTEXT_ARCHIVED) == 1

    restored = contexts.restore(_principal(), context.id)
    entries_after = _timeline_service(uow).list_timeline(_principal(), restored.id)
    assert ContextTimelineEventType.CONTEXT_ARCHIVED not in [
        item.type for item in entries_after
    ]


def test_unmapped_identity_is_not_found() -> None:
    """Callers without an identity mapping cannot read a timeline."""
    _user_a, _user_b, _owner, uow = _seed_users()
    context = _context_service(uow).create(
        _principal(),
        type=BusinessContextType.PROJECT,
        title="Mapped",
    )
    with pytest.raises(BusinessContextNotFoundError):
        _timeline_service(uow).list_timeline(_principal("unknown"), context.id)
