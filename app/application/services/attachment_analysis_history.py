"""User-owned attachment-analysis history use cases."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID

from app.application.exceptions import (
    AttachmentAnalysisNotFoundError,
    ConnectorAccountNotFoundError,
)
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.telemetry import bound_request_id_as_uuid, elapsed_ms, error_class
from app.domain.interfaces.attachment_analysis_repository import (
    AttachmentAnalysisRecord,
    NewAttachmentAnalysis,
)
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models import AttachmentAnalysis

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."


class AttachmentAnalysisHistoryService:
    """Persist and retrieve attachment analyses for an internal user UUID."""

    def __init__(self, unit_of_work_factory: Callable[[], PersistenceUnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def save(
        self,
        user_id: UUID,
        connector_account_id: UUID,
        result: AttachmentAnalysis,
        *,
        reported_size: int | None = None,
    ) -> AttachmentAnalysisRecord:
        """Store a successful structured attachment analysis. Never stores content."""
        started_at = time.perf_counter()
        record = NewAttachmentAnalysis(
            user_id=user_id,
            connector_account_id=connector_account_id,
            provider_message_id=result.source_message_id,
            provider_attachment_id=result.source_attachment_id,
            filename=result.filename,
            media_type=result.media_type,
            kind=result.kind.value,
            extracted_content_status=result.extracted_content_status.value,
            truncated=result.truncated,
            warnings=list(result.warnings),
            reported_size=reported_size,
            page_count=result.page_count,
            character_count=result.character_count,
            summary_text=result.analysis.summary.text,
            summary_confidence=result.analysis.summary.confidence,
            priority=result.analysis.priority.level.value,
            category=result.analysis.category.value,
            action_items=[
                item.model_dump(mode="json") for item in result.analysis.action_items
            ],
            provider=result.provider or "unknown",
            request_id=bound_request_id_as_uuid(),
        )
        try:
            with self._unit_of_work_factory() as uow:
                owned_account = uow.connector_accounts.get_owned(
                    connector_account_id,
                    user_id,
                )
                if owned_account is None:
                    raise ConnectorAccountNotFoundError()
                saved = uow.attachment_analyses.save(record)
                uow.commit()
        except ConnectorAccountNotFoundError:
            raise
        except PersistenceError as exc:
            logger.warning(
                "attachment_analysis_persistence_failed",
                operation="save",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "attachment_analysis_persisted",
            operation="save",
            attachment_analysis_id=str(saved.id),
            duration_ms=elapsed_ms(started_at),
        )
        return saved

    def list_for_user(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
        *,
        connector_account_id: UUID | None = None,
        provider_message_id: str | None = None,
    ) -> list[AttachmentAnalysisRecord]:
        """Return a bounded page of attachment analyses owned by ``user_id``."""
        started_at = time.perf_counter()
        try:
            with self._unit_of_work_factory() as uow:
                items = uow.attachment_analyses.list_for_user(
                    user_id,
                    limit,
                    offset,
                    connector_account_id=connector_account_id,
                    provider_message_id=provider_message_id,
                )
        except PersistenceError as exc:
            logger.warning(
                "persistence_unavailable",
                operation="list_attachment_analyses",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "attachment_analysis_history_listed",
            operation="list",
            result_count=len(items),
            duration_ms=elapsed_ms(started_at),
        )
        return items

    def get_for_user(
        self,
        attachment_analysis_id: UUID,
        user_id: UUID,
    ) -> AttachmentAnalysisRecord:
        """Return an owned attachment analysis or raise not-found."""
        started_at = time.perf_counter()
        try:
            with self._unit_of_work_factory() as uow:
                record = uow.attachment_analyses.get_by_id_for_user(
                    attachment_analysis_id,
                    user_id,
                )
        except PersistenceError as exc:
            logger.warning(
                "persistence_unavailable",
                operation="get_attachment_analysis",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        if record is None:
            raise AttachmentAnalysisNotFoundError()

        logger.info(
            "attachment_analysis_retrieved",
            operation="get",
            attachment_analysis_id=str(record.id),
            duration_ms=elapsed_ms(started_at),
        )
        return record
