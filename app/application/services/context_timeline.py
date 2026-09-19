"""BusinessContext timeline read model.

Assembles ordered, ownership-scoped timeline entries from durable records.
Does not mutate source rows, call mailbox providers, retrieve attachments,
or invoke AI.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.exceptions import BusinessContextNotFoundError
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import BusinessContextStatus, ContextTimelineEventType
from app.domain.interfaces.analysis_repository import AnalysisRecord
from app.domain.interfaces.attachment_analysis_repository import AttachmentAnalysisRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models.business_context import BusinessContext
from app.domain.models.business_context_communication_link import (
    BusinessContextCommunicationLink,
)
from app.domain.models.workflow import WorkflowAction

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100
_SOURCE_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class ContextTimelineEntry:
    """One projected timeline item with a deterministic identity."""

    id: str
    type: ContextTimelineEventType
    occurred_at: datetime
    title: str
    summary: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    connector_account_id: UUID | None = None
    provider_message_id: str | None = None


class ContextTimelineService:
    """Assemble a read-only timeline for an owned BusinessContext."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory

    def list_timeline(
        self,
        principal: AuthenticatedPrincipal,
        context_id: UUID,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[ContextTimelineEntry]:
        """Return a bounded page of timeline entries for an owned context.

        Ordering: ``occurred_at`` descending, then ``id`` ascending.
        Unknown or cross-user contexts raise ``BusinessContextNotFoundError``.
        """
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        page_limit = max(1, min(limit, _MAX_LIST_LIMIT))
        safe_offset = max(0, offset)
        try:
            with self._unit_of_work_factory() as uow:
                context = uow.business_contexts.get_owned(context_id, user_id)
                if context is None:
                    raise BusinessContextNotFoundError()
                entries = self._assemble(uow, context, user_id)
        except BusinessContextNotFoundError:
            raise
        except PersistenceError as exc:
            logger.warning(
                "context_timeline_persistence_failed",
                operation="list_timeline",
                business_context_id=str(context_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        entries.sort(key=lambda item: (-item.occurred_at.timestamp(), item.id))
        page = entries[safe_offset : safe_offset + page_limit]
        logger.info(
            "context_timeline_listed",
            operation="list_timeline",
            business_context_id=str(context_id),
            result_count=len(page),
            duration_ms=elapsed_ms(started_at),
        )
        return page

    def _assemble(
        self,
        uow: PersistenceUnitOfWork,
        context: BusinessContext,
        user_id: UUID,
    ) -> list[ContextTimelineEntry]:
        entries: list[ContextTimelineEntry] = [
            ContextTimelineEntry(
                id=f"context_created:{context.id}",
                type=ContextTimelineEventType.CONTEXT_CREATED,
                occurred_at=context.created_at,
                title="Context created",
                summary=None,
                source_type="business_context",
                source_id=str(context.id),
            )
        ]
        if (
            context.status is BusinessContextStatus.ARCHIVED
            and context.archived_at is not None
        ):
            archived_iso = context.archived_at.isoformat()
            entries.append(
                ContextTimelineEntry(
                    id=f"context_archived:{context.id}:{archived_iso}",
                    type=ContextTimelineEventType.CONTEXT_ARCHIVED,
                    occurred_at=context.archived_at,
                    title="Context archived",
                    summary=(
                        "Current archive state. Historical archive/restore "
                        "transitions are not fully reconstructible."
                    ),
                    source_type="business_context",
                    source_id=str(context.id),
                )
            )

        links = self._load_all_links(uow, context.id, user_id)
        provenance: set[tuple[UUID, str]] = set()
        for link in links:
            provenance.add((link.connector_account_id, link.provider_message_id))
            entries.append(_association_entry(link))

        if provenance:
            for analysis in self._matching_analyses(uow, user_id, provenance):
                entries.append(_analysis_entry(analysis))
            for attachment in self._matching_attachment_analyses(
                uow, user_id, provenance
            ):
                entries.append(_attachment_analysis_entry(attachment))
            for workflow in self._matching_workflows(uow, user_id, provenance):
                entries.extend(_workflow_entries(workflow))
        return entries

    def _load_all_links(
        self,
        uow: PersistenceUnitOfWork,
        context_id: UUID,
        user_id: UUID,
    ) -> list[BusinessContextCommunicationLink]:
        links: list[BusinessContextCommunicationLink] = []
        offset = 0
        while True:
            page = uow.business_context_communication_links.list_for_context_owned(
                context_id,
                user_id,
                _SOURCE_PAGE_SIZE,
                offset,
            )
            links.extend(page)
            if len(page) < _SOURCE_PAGE_SIZE:
                break
            offset += _SOURCE_PAGE_SIZE
        return links

    def _matching_analyses(
        self,
        uow: PersistenceUnitOfWork,
        user_id: UUID,
        provenance: set[tuple[UUID, str]],
    ) -> list[AnalysisRecord]:
        matched: list[AnalysisRecord] = []
        offset = 0
        while True:
            page = uow.analysis_repository.list_for_user(
                user_id, _SOURCE_PAGE_SIZE, offset
            )
            for record in page:
                if (
                    record.connector_account_id is None
                    or record.message_id is None
                ):
                    continue
                key = (record.connector_account_id, record.message_id)
                if key in provenance:
                    matched.append(record)
            if len(page) < _SOURCE_PAGE_SIZE:
                break
            offset += _SOURCE_PAGE_SIZE
        return matched

    def _matching_attachment_analyses(
        self,
        uow: PersistenceUnitOfWork,
        user_id: UUID,
        provenance: set[tuple[UUID, str]],
    ) -> list[AttachmentAnalysisRecord]:
        matched: list[AttachmentAnalysisRecord] = []
        for connector_account_id, provider_message_id in provenance:
            offset = 0
            while True:
                page = uow.attachment_analyses.list_for_user(
                    user_id,
                    _SOURCE_PAGE_SIZE,
                    offset,
                    connector_account_id=connector_account_id,
                    provider_message_id=provider_message_id,
                )
                matched.extend(page)
                if len(page) < _SOURCE_PAGE_SIZE:
                    break
                offset += _SOURCE_PAGE_SIZE
        return matched

    def _matching_workflows(
        self,
        uow: PersistenceUnitOfWork,
        user_id: UUID,
        provenance: set[tuple[UUID, str]],
    ) -> list[WorkflowAction]:
        matched: list[WorkflowAction] = []
        offset = 0
        while True:
            page = uow.workflow_actions.list_owned(user_id, _SOURCE_PAGE_SIZE, offset)
            for action in page:
                if (
                    action.connector_account_id is None
                    or action.provider_message_id is None
                ):
                    continue
                key = (action.connector_account_id, action.provider_message_id)
                if key in provenance:
                    matched.append(action)
            if len(page) < _SOURCE_PAGE_SIZE:
                break
            offset += _SOURCE_PAGE_SIZE
        return matched

    def _require_existing_user(self, principal: AuthenticatedPrincipal) -> UUID:
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise BusinessContextNotFoundError()
        return user_id


def _association_entry(link: BusinessContextCommunicationLink) -> ContextTimelineEntry:
    return ContextTimelineEntry(
        id=f"association:{link.id}",
        type=ContextTimelineEventType.COMMUNICATION_ASSOCIATED,
        occurred_at=link.associated_at,
        title="Communication associated",
        summary=None,
        source_type="communication_link",
        source_id=str(link.id),
        connector_account_id=link.connector_account_id,
        provider_message_id=link.provider_message_id,
    )


def _analysis_entry(analysis: AnalysisRecord) -> ContextTimelineEntry:
    return ContextTimelineEntry(
        id=f"analysis:{analysis.id}",
        type=ContextTimelineEventType.ANALYSIS_COMPLETED,
        occurred_at=analysis.created_at,
        title="Analysis completed",
        summary=None,
        source_type="analysis",
        source_id=str(analysis.id),
        connector_account_id=analysis.connector_account_id,
        provider_message_id=analysis.message_id,
    )


def _attachment_analysis_entry(
    analysis: AttachmentAnalysisRecord,
) -> ContextTimelineEntry:
    filename = analysis.filename.strip() if analysis.filename else ""
    summary = f"Attachment analyzed: {filename}" if filename else "Attachment analyzed"
    return ContextTimelineEntry(
        id=f"attachment_analysis:{analysis.id}",
        type=ContextTimelineEventType.ATTACHMENT_ANALYSIS_COMPLETED,
        occurred_at=analysis.created_at,
        title="Attachment analysis completed",
        summary=summary,
        source_type="attachment_analysis",
        source_id=str(analysis.id),
        connector_account_id=analysis.connector_account_id,
        provider_message_id=analysis.provider_message_id,
    )


def _workflow_entries(action: WorkflowAction) -> list[ContextTimelineEntry]:
    """Emit one entry per reconstructible workflow transition timestamp."""
    entries: list[ContextTimelineEntry] = [
        ContextTimelineEntry(
            id=f"workflow:{action.id}:pending",
            type=ContextTimelineEventType.WORKFLOW_PROPOSED,
            occurred_at=action.created_at,
            title="Workflow proposed",
            summary=None,
            source_type="workflow_action",
            source_id=str(action.id),
            connector_account_id=action.connector_account_id,
            provider_message_id=action.provider_message_id,
        )
    ]
    if action.approved_at is not None:
        entries.append(
            ContextTimelineEntry(
                id=f"workflow:{action.id}:approved",
                type=ContextTimelineEventType.WORKFLOW_APPROVED,
                occurred_at=action.approved_at,
                title="Workflow approved",
                summary=None,
                source_type="workflow_action",
                source_id=str(action.id),
                connector_account_id=action.connector_account_id,
                provider_message_id=action.provider_message_id,
            )
        )
    if action.rejected_at is not None:
        entries.append(
            ContextTimelineEntry(
                id=f"workflow:{action.id}:rejected",
                type=ContextTimelineEventType.WORKFLOW_REJECTED,
                occurred_at=action.rejected_at,
                title="Workflow rejected",
                summary=None,
                source_type="workflow_action",
                source_id=str(action.id),
                connector_account_id=action.connector_account_id,
                provider_message_id=action.provider_message_id,
            )
        )
    if action.executed_at is not None:
        entries.append(
            ContextTimelineEntry(
                id=f"workflow:{action.id}:executed",
                type=ContextTimelineEventType.WORKFLOW_EXECUTED,
                occurred_at=action.executed_at,
                title="Workflow executed",
                summary=None,
                source_type="workflow_action",
                source_id=str(action.id),
                connector_account_id=action.connector_account_id,
                provider_message_id=action.provider_message_id,
            )
        )
    if action.failed_at is not None:
        entries.append(
            ContextTimelineEntry(
                id=f"workflow:{action.id}:failed",
                type=ContextTimelineEventType.WORKFLOW_FAILED,
                occurred_at=action.failed_at,
                title="Workflow failed",
                summary=None,
                source_type="workflow_action",
                source_id=str(action.id),
                connector_account_id=action.connector_account_id,
                provider_message_id=action.provider_message_id,
            )
        )
    return entries
