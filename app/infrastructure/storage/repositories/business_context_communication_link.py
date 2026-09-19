"""SQLAlchemy BusinessContextCommunicationLinkRepository implementation."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.enums import AssociationSource
from app.domain.interfaces.business_context_communication_link_repository import (
    BusinessContextCommunicationLinkRepository,
)
from app.domain.models.business_context_communication_link import (
    BusinessContextCommunicationLink,
)
from app.infrastructure.storage.models import BusinessContextCommunicationLinkRow

_GENERIC_FAILURE = "Could not persist business context communication link."
_DUPLICATE_FAILURE = "Duplicate communication link."
_INVALID_STORED = "Stored business context communication link is invalid."
_MAX_LIST_LIMIT = 100
_LINK_UNIQUE = "uq_bcc_links_context_connector_message"


class SqlAlchemyBusinessContextCommunicationLinkRepository(
    BusinessContextCommunicationLinkRepository
):
    """Persist provenance links with ownership enforced in SQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self, link: BusinessContextCommunicationLink
    ) -> BusinessContextCommunicationLink:
        """Persist ``link`` and return the stored domain object."""
        row = BusinessContextCommunicationLinkRow(
            id=link.id,
            business_context_id=link.business_context_id,
            user_id=link.owner_user_id,
            connector_account_id=link.connector_account_id,
            provider_message_id=link.provider_message_id,
            analysis_id=link.analysis_id,
            associated_by_user_id=link.associated_by_user_id,
            associated_at=link.associated_at,
            association_source=link.association_source.value,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            if _is_link_unique_violation(exc):
                raise PersistenceError(_DUPLICATE_FAILURE) from exc
            raise PersistenceError(_GENERIC_FAILURE) from exc
        return _to_domain(row)

    def get_owned(
        self, link_id: UUID, user_id: UUID
    ) -> BusinessContextCommunicationLink | None:
        """Return the link only when it is owned by ``user_id``."""
        statement = (
            select(BusinessContextCommunicationLinkRow)
            .where(
                BusinessContextCommunicationLinkRow.id == link_id,
                BusinessContextCommunicationLinkRow.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(statement).first()
        if row is None:
            return None
        return _to_domain(row)

    def get_by_provenance_owned(
        self,
        business_context_id: UUID,
        connector_account_id: UUID,
        provider_message_id: str,
        user_id: UUID,
    ) -> BusinessContextCommunicationLink | None:
        """Return the owned link for the unique provenance triple, if any."""
        statement = (
            select(BusinessContextCommunicationLinkRow)
            .where(
                BusinessContextCommunicationLinkRow.business_context_id
                == business_context_id,
                BusinessContextCommunicationLinkRow.connector_account_id
                == connector_account_id,
                BusinessContextCommunicationLinkRow.provider_message_id
                == provider_message_id,
                BusinessContextCommunicationLinkRow.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(statement).first()
        if row is None:
            return None
        return _to_domain(row)

    def list_for_context_owned(
        self,
        business_context_id: UUID,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> list[BusinessContextCommunicationLink]:
        """Return a bounded page of links for an owned context, newest first."""
        if limit < 1 or offset < 0:
            return []
        statement = (
            select(BusinessContextCommunicationLinkRow)
            .where(
                BusinessContextCommunicationLinkRow.business_context_id
                == business_context_id,
                BusinessContextCommunicationLinkRow.user_id == user_id,
            )
            .order_by(
                BusinessContextCommunicationLinkRow.associated_at.desc(),
                BusinessContextCommunicationLinkRow.id.desc(),
            )
            .limit(min(limit, _MAX_LIST_LIMIT))
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return [_to_domain(row) for row in self._session.scalars(statement).all()]

    def remove_owned(self, link_id: UUID, user_id: UUID) -> bool:
        """Delete the association row only when owned by ``user_id``."""
        statement = delete(BusinessContextCommunicationLinkRow).where(
            BusinessContextCommunicationLinkRow.id == link_id,
            BusinessContextCommunicationLinkRow.user_id == user_id,
        )
        try:
            result = self._session.execute(statement)
        except SQLAlchemyError:
            raise PersistenceError(_GENERIC_FAILURE) from None
        return result.rowcount == 1


def _to_domain(row: BusinessContextCommunicationLinkRow) -> BusinessContextCommunicationLink:
    try:
        return BusinessContextCommunicationLink.rehydrate(
            id=row.id,
            business_context_id=row.business_context_id,
            owner_user_id=row.user_id,
            connector_account_id=row.connector_account_id,
            provider_message_id=row.provider_message_id,
            analysis_id=row.analysis_id,
            associated_by_user_id=row.associated_by_user_id,
            associated_at=row.associated_at,
            association_source=AssociationSource(row.association_source),
        )
    except (ValidationError, ValueError):
        raise PersistenceError(_INVALID_STORED) from None


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = exc.orig
    if orig is None:
        return None
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if isinstance(name, str) and name:
        return name
    return None


def _is_link_unique_violation(exc: IntegrityError) -> bool:
    if _constraint_name(exc) == _LINK_UNIQUE:
        return True
    orig = exc.orig
    diagnostic = str(orig) if orig is not None else ""
    if _LINK_UNIQUE in diagnostic:
        return True
    lowered = diagnostic.lower()
    return (
        "unique constraint failed" in lowered
        and "business_context_communication_links.business_context_id" in lowered
        and "business_context_communication_links.connector_account_id" in lowered
        and "business_context_communication_links.provider_message_id" in lowered
    )
