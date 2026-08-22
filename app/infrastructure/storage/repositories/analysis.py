"""SQLAlchemy AnalysisRepository implementation."""

from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.interfaces.analysis_repository import (
    AnalysisRecord,
    AnalysisRepository,
    NewAnalysis,
)
from app.infrastructure.storage.models import Analysis

_MAX_LIST_LIMIT = 100


class SqlAlchemyAnalysisRepository(AnalysisRepository):
    """Persist analyses with ownership enforced in SQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, analysis: NewAnalysis) -> AnalysisRecord:
        """Persist an analysis for ``analysis.user_id`` and return the stored record."""
        row = Analysis(
            id=analysis.analysis_id or uuid4(),
            user_id=analysis.user_id,
            request_id=analysis.request_id,
            provider=analysis.provider,
            priority=analysis.priority,
            category=analysis.category,
            source_type=analysis.source_type,
            message_id=analysis.message_id,
            summary_text=analysis.summary_text,
            summary_confidence=analysis.summary_confidence,
            action_items=list(analysis.action_items),
            draft_reply=None if analysis.draft_reply is None else dict(analysis.draft_reply),
            connector_account_id=analysis.connector_account_id,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise PersistenceError("Could not persist analysis.") from exc
        return _to_record(row)

    def get_by_id_for_user(self, analysis_id: UUID, user_id: UUID) -> AnalysisRecord | None:
        """Return the analysis only when it is owned by ``user_id``."""
        statement = select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == user_id,
        )
        row = self._session.scalars(statement).first()
        if row is None:
            return None
        return _to_record(row)

    def list_for_user(self, user_id: UUID, limit: int, offset: int) -> list[AnalysisRecord]:
        """Return a bounded page of analyses owned by ``user_id``, newest first.

        Non-positive ``limit`` or negative ``offset`` yield an empty page so
        those values are never passed to SQL.
        """
        if limit < 1 or offset < 0:
            return []
        statement = (
            select(Analysis)
            .where(Analysis.user_id == user_id)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(min(limit, _MAX_LIST_LIMIT))
            .offset(offset)
        )
        return [_to_record(row) for row in self._session.scalars(statement).all()]

    def delete_for_user(self, analysis_id: UUID, user_id: UUID) -> bool:
        """Delete the analysis only when owned by ``user_id``."""
        statement = delete(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == user_id,
        )
        result = self._session.execute(statement)
        return result.rowcount == 1


def _to_record(row: Analysis) -> AnalysisRecord:
    action_items = cast(list[dict[str, Any]], row.action_items)
    draft_reply = cast(dict[str, Any] | None, row.draft_reply)
    return AnalysisRecord(
        id=row.id,
        user_id=row.user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        request_id=row.request_id,
        provider=row.provider,
        priority=row.priority,
        category=row.category,
        source_type=row.source_type,
        message_id=row.message_id,
        summary_text=row.summary_text,
        summary_confidence=row.summary_confidence,
        action_items=list(action_items),
        draft_reply=None if draft_reply is None else dict(draft_reply),
        connector_account_id=row.connector_account_id,
    )
