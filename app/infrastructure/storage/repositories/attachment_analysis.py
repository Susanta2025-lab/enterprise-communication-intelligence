"""SQLAlchemy AttachmentAnalysisRepository implementation."""

from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.interfaces.attachment_analysis_repository import (
    AttachmentAnalysisRecord,
    AttachmentAnalysisRepository,
    NewAttachmentAnalysis,
)
from app.infrastructure.storage.models import AttachmentAnalysisRow

_MAX_LIST_LIMIT = 100


class SqlAlchemyAttachmentAnalysisRepository(AttachmentAnalysisRepository):
    """Persist attachment analyses with ownership enforced in SQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, analysis: NewAttachmentAnalysis) -> AttachmentAnalysisRecord:
        """Persist an attachment analysis for ``analysis.user_id``."""
        row = AttachmentAnalysisRow(
            id=analysis.attachment_analysis_id or uuid4(),
            user_id=analysis.user_id,
            connector_account_id=analysis.connector_account_id,
            provider_message_id=analysis.provider_message_id,
            provider_attachment_id=analysis.provider_attachment_id,
            filename=analysis.filename,
            media_type=analysis.media_type,
            kind=analysis.kind,
            extracted_content_status=analysis.extracted_content_status,
            truncated=analysis.truncated,
            warnings=list(analysis.warnings),
            reported_size=analysis.reported_size,
            page_count=analysis.page_count,
            character_count=analysis.character_count,
            summary_text=analysis.summary_text,
            summary_confidence=analysis.summary_confidence,
            priority=analysis.priority,
            category=analysis.category,
            action_items=list(analysis.action_items),
            provider=analysis.provider,
            request_id=analysis.request_id,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise PersistenceError("Could not persist attachment analysis.") from exc
        return _to_record(row)

    def get_by_id_for_user(
        self,
        attachment_analysis_id: UUID,
        user_id: UUID,
    ) -> AttachmentAnalysisRecord | None:
        """Return the row only when it is owned by ``user_id``."""
        statement = select(AttachmentAnalysisRow).where(
            AttachmentAnalysisRow.id == attachment_analysis_id,
            AttachmentAnalysisRow.user_id == user_id,
        )
        row = self._session.scalars(statement).first()
        if row is None:
            return None
        return _to_record(row)

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
        if limit < 1 or offset < 0:
            return []
        statement = select(AttachmentAnalysisRow).where(
            AttachmentAnalysisRow.user_id == user_id
        )
        if connector_account_id is not None:
            statement = statement.where(
                AttachmentAnalysisRow.connector_account_id == connector_account_id
            )
        if provider_message_id is not None:
            statement = statement.where(
                AttachmentAnalysisRow.provider_message_id == provider_message_id
            )
        statement = (
            statement.order_by(
                AttachmentAnalysisRow.created_at.desc(),
                AttachmentAnalysisRow.id.desc(),
            )
            .limit(min(limit, _MAX_LIST_LIMIT))
            .offset(offset)
        )
        return [_to_record(row) for row in self._session.scalars(statement).all()]


def _to_record(row: AttachmentAnalysisRow) -> AttachmentAnalysisRecord:
    warnings = cast(list[str], row.warnings)
    action_items = cast(list[dict[str, Any]], row.action_items)
    return AttachmentAnalysisRecord(
        id=row.id,
        user_id=row.user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        connector_account_id=row.connector_account_id,
        provider_message_id=row.provider_message_id,
        provider_attachment_id=row.provider_attachment_id,
        filename=row.filename,
        media_type=row.media_type,
        kind=row.kind,
        extracted_content_status=row.extracted_content_status,
        truncated=row.truncated,
        warnings=list(warnings),
        reported_size=row.reported_size,
        page_count=row.page_count,
        character_count=row.character_count,
        summary_text=row.summary_text,
        summary_confidence=row.summary_confidence,
        priority=row.priority,
        category=row.category,
        action_items=list(action_items),
        provider=row.provider,
        request_id=row.request_id,
    )
