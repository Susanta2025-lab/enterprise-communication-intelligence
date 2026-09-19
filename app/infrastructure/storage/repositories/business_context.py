"""SQLAlchemy BusinessContextRepository implementation."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.enums import BusinessContextStatus, BusinessContextType
from app.domain.interfaces.business_context_repository import BusinessContextRepository
from app.domain.models.business_context import BusinessContext
from app.infrastructure.storage.models import BusinessContextRow, utc_now

_GENERIC_FAILURE = "Could not persist business context."
_INVALID_STORED = "Stored business context is invalid."
_MAX_LIST_LIMIT = 100


class SqlAlchemyBusinessContextRepository(BusinessContextRepository):
    """Persist business contexts with ownership enforced in SQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, context: BusinessContext) -> BusinessContext:
        """Persist ``context`` and return the stored domain object."""
        row = BusinessContextRow(
            id=context.id,
            user_id=context.owner_user_id,
            type=context.type.value,
            title=context.title,
            description=context.description,
            reference=context.reference,
            status=context.status.value,
            archived_at=context.archived_at,
            created_at=context.created_at,
            updated_at=context.updated_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise PersistenceError(_GENERIC_FAILURE) from exc
        return _to_domain(row)

    def get_owned(self, context_id: UUID, user_id: UUID) -> BusinessContext | None:
        """Return the context only when it is owned by ``user_id``."""
        statement = (
            select(BusinessContextRow)
            .where(
                BusinessContextRow.id == context_id,
                BusinessContextRow.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(statement).first()
        if row is None:
            return None
        return _to_domain(row)

    def list_owned(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
        *,
        status: BusinessContextStatus | None = BusinessContextStatus.ACTIVE,
        type: BusinessContextType | None = None,
        reference: str | None = None,
    ) -> list[BusinessContext]:
        """Return a bounded page of contexts owned by ``user_id``, newest first."""
        if limit < 1 or offset < 0:
            return []
        statement = select(BusinessContextRow).where(BusinessContextRow.user_id == user_id)
        if status is not None:
            statement = statement.where(BusinessContextRow.status == status.value)
        if type is not None:
            statement = statement.where(BusinessContextRow.type == type.value)
        if reference is not None:
            statement = statement.where(BusinessContextRow.reference == reference)
        statement = (
            statement.order_by(
                BusinessContextRow.created_at.desc(),
                BusinessContextRow.id.desc(),
            )
            .limit(min(limit, _MAX_LIST_LIMIT))
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return [_to_domain(row) for row in self._session.scalars(statement).all()]

    def save_owned(self, context: BusinessContext) -> BusinessContext | None:
        """Persist mutable and lifecycle fields for an owned context."""
        statement = (
            update(BusinessContextRow)
            .where(
                BusinessContextRow.id == context.id,
                BusinessContextRow.user_id == context.owner_user_id,
            )
            .values(
                type=context.type.value,
                title=context.title,
                description=context.description,
                reference=context.reference,
                status=context.status.value,
                archived_at=context.archived_at,
                updated_at=context.updated_at or utc_now(),
            )
            .execution_options(synchronize_session="fetch")
        )
        try:
            result = self._session.execute(statement)
        except (IntegrityError, SQLAlchemyError):
            raise PersistenceError(_GENERIC_FAILURE) from None
        if result.rowcount != 1:
            return None
        loaded = self.get_owned(context.id, context.owner_user_id)
        if loaded is None:
            raise PersistenceError(_GENERIC_FAILURE)
        return loaded


def _to_domain(row: BusinessContextRow) -> BusinessContext:
    try:
        return BusinessContext.rehydrate(
            id=row.id,
            owner_user_id=row.user_id,
            type=BusinessContextType(row.type),
            title=row.title,
            description=row.description,
            reference=row.reference,
            status=BusinessContextStatus(row.status),
            archived_at=row.archived_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    except (ValidationError, ValueError):
        raise PersistenceError(_INVALID_STORED) from None
