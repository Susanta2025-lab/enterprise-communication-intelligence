"""User-owned analysis history use cases."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID

from app.application.exceptions import AnalysisNotFoundError
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.telemetry import bound_request_id_as_uuid, elapsed_ms, error_class
from app.domain.interfaces.analysis_repository import AnalysisRecord, NewAnalysis
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."


class AnalysisHistoryService:
    """Persist and retrieve analyses for an internal user UUID."""

    def __init__(self, unit_of_work_factory: Callable[[], PersistenceUnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def save(
        self,
        user_id: UUID,
        request: CommunicationRequest,
        result: CommunicationAnalysisResult,
    ) -> AnalysisRecord:
        """Store a successful analysis result. Does not persist the raw message body."""
        started_at = time.perf_counter()
        record = NewAnalysis(
            user_id=user_id,
            provider=result.provider or "unknown",
            priority=result.analysis.priority.level.value,
            category=result.analysis.category.value,
            source_type=request.message.metadata.source_type.value,
            summary_text=result.analysis.summary.text,
            action_items=[
                item.model_dump(mode="json") for item in result.analysis.action_items
            ],
            request_id=bound_request_id_as_uuid(),
            message_id=request.message.message_id or result.analysis.message_id,
            summary_confidence=result.analysis.summary.confidence,
            draft_reply=(
                result.analysis.draft_reply.model_dump(mode="json")
                if result.analysis.draft_reply is not None
                else None
            ),
        )
        try:
            with self._unit_of_work_factory() as uow:
                saved = uow.analysis_repository.save(record)
                uow.commit()
        except PersistenceError as exc:
            logger.warning(
                "analysis_persistence_failed",
                operation="save",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "analysis_persisted",
            operation="save",
            analysis_id=str(saved.id),
            duration_ms=elapsed_ms(started_at),
        )
        return saved

    def list_for_user(self, user_id: UUID, limit: int, offset: int) -> list[AnalysisRecord]:
        """Return a bounded page of analyses owned by ``user_id``."""
        started_at = time.perf_counter()
        try:
            with self._unit_of_work_factory() as uow:
                items = uow.analysis_repository.list_for_user(user_id, limit, offset)
        except PersistenceError as exc:
            logger.warning(
                "persistence_unavailable",
                operation="list",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "analysis_history_listed",
            operation="list",
            result_count=len(items),
            duration_ms=elapsed_ms(started_at),
        )
        return items

    def get_for_user(self, analysis_id: UUID, user_id: UUID) -> AnalysisRecord:
        """Return an owned analysis or raise not-found."""
        started_at = time.perf_counter()
        try:
            with self._unit_of_work_factory() as uow:
                record = uow.analysis_repository.get_by_id_for_user(analysis_id, user_id)
        except PersistenceError as exc:
            logger.warning(
                "persistence_unavailable",
                operation="get",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        if record is None:
            raise AnalysisNotFoundError()

        logger.info(
            "analysis_retrieved",
            operation="get",
            analysis_id=str(record.id),
            duration_ms=elapsed_ms(started_at),
        )
        return record

    def delete_for_user(self, analysis_id: UUID, user_id: UUID) -> None:
        """Hard-delete an owned analysis or raise not-found."""
        started_at = time.perf_counter()
        try:
            with self._unit_of_work_factory() as uow:
                deleted = uow.analysis_repository.delete_for_user(analysis_id, user_id)
                if deleted:
                    uow.commit()
        except PersistenceError as exc:
            logger.warning(
                "persistence_unavailable",
                operation="delete",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        if not deleted:
            raise AnalysisNotFoundError()

        logger.info(
            "analysis_deleted",
            operation="delete",
            analysis_id=str(analysis_id),
            duration_ms=elapsed_ms(started_at),
        )
