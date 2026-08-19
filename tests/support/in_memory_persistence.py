"""In-memory persistence doubles for Phase 9B application tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

from app.core.exceptions import PersistenceError
from app.domain.interfaces.analysis_repository import AnalysisRecord, NewAnalysis
from app.domain.interfaces.identity_repository import IdentityRepository
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

_DUPLICATE_IDENTITY = "External identity is already registered."


class InMemoryIdentityRepository(IdentityRepository):
    """Dict-backed identity mapping used by unit tests."""

    def __init__(self, identities: dict[tuple[str, str], UUID]) -> None:
        self._identities = identities
        self.create_calls = 0

    def get_user_id_by_external_identity(self, issuer: str, subject: str) -> UUID | None:
        return self._identities.get((issuer, subject))

    def create_user_with_external_identity(self, issuer: str, subject: str) -> UUID:
        self.create_calls += 1
        key = (issuer, subject)
        if key in self._identities:
            raise PersistenceError(_DUPLICATE_IDENTITY)
        user_id = uuid4()
        self._identities[key] = user_id
        return user_id


class InMemoryAnalysisRepository:
    """Dict-backed analysis store used by unit tests."""

    def __init__(self, analyses: dict[UUID, AnalysisRecord]) -> None:
        self._analyses = analyses
        self.save_calls = 0

    def save(self, analysis: NewAnalysis) -> AnalysisRecord:
        self.save_calls += 1
        now = datetime.now(UTC)
        record = AnalysisRecord(
            id=analysis.analysis_id or uuid4(),
            user_id=analysis.user_id,
            created_at=now,
            updated_at=now,
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
        )
        self._analyses[record.id] = record
        return record

    def get_by_id_for_user(self, analysis_id: UUID, user_id: UUID) -> AnalysisRecord | None:
        record = self._analyses.get(analysis_id)
        if record is None or record.user_id != user_id:
            return None
        return record

    def list_for_user(self, user_id: UUID, limit: int, offset: int) -> list[AnalysisRecord]:
        owned = [item for item in self._analyses.values() if item.user_id == user_id]
        owned.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        if limit < 1 or offset < 0:
            return []
        return owned[offset : offset + min(limit, 100)]

    def delete_for_user(self, analysis_id: UUID, user_id: UUID) -> bool:
        record = self._analyses.get(analysis_id)
        if record is None or record.user_id != user_id:
            return False
        del self._analyses[analysis_id]
        return True


class InMemoryUnitOfWork(PersistenceUnitOfWork):
    """Minimal unit of work that records commit/rollback/close."""

    def __init__(
        self,
        *,
        identities: dict[tuple[str, str], UUID] | None = None,
        analyses: dict[UUID, AnalysisRecord] | None = None,
        fail_commit: bool = False,
        fail_on_enter: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.identities = identities if identities is not None else {}
        self.analyses = analyses if analyses is not None else {}
        self._identity_repository = InMemoryIdentityRepository(self.identities)
        self._analysis_repository = InMemoryAnalysisRepository(self.analyses)
        self.fail_commit = fail_commit
        self.fail_on_enter = fail_on_enter
        self.commit_error = commit_error
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False
        self.entered = False

    @property
    def identity_repository(self) -> InMemoryIdentityRepository:
        return self._identity_repository

    @property
    def analysis_repository(self) -> InMemoryAnalysisRepository:
        return self._analysis_repository

    def commit(self) -> None:
        self.commit_calls += 1
        if self.fail_commit:
            raise PersistenceError("Could not commit persistence changes.")
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.rollback_calls += 1

    def __enter__(self) -> InMemoryUnitOfWork:
        if self.fail_on_enter is not None:
            raise self.fail_on_enter
        self.entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        self.closed = True

    def close(self) -> None:
        self.closed = True


class UnitOfWorkFactory:
    """Return the same in-memory unit of work, or a sequence of them."""

    def __init__(self, *units: InMemoryUnitOfWork) -> None:
        self._units = list(units) or [InMemoryUnitOfWork()]
        self.calls = 0

    def __call__(self) -> InMemoryUnitOfWork:
        index = min(self.calls, len(self._units) - 1)
        self.calls += 1
        return self._units[index]


def sample_analysis_record(
    user_id: UUID,
    *,
    analysis_id: UUID | None = None,
    summary_text: str = "Status summary",
    extra: dict[str, Any] | None = None,
) -> AnalysisRecord:
    """Build a synthetic analysis record for history tests."""
    now = datetime.now(UTC)
    payload = extra or {}
    return AnalysisRecord(
        id=analysis_id or uuid4(),
        user_id=user_id,
        created_at=now,
        updated_at=now,
        request_id=payload.get("request_id"),
        provider=payload.get("provider", "mock"),
        priority=payload.get("priority", "medium"),
        category=payload.get("category", "general"),
        source_type=payload.get("source_type", "email"),
        message_id=payload.get("message_id", "msg-001"),
        summary_text=summary_text,
        summary_confidence=payload.get("summary_confidence", 1.0),
        action_items=list(payload.get("action_items", [])),
        draft_reply=payload.get("draft_reply"),
    )
