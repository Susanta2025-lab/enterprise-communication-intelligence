"""BusinessContext communication provenance association use cases.

Associates provider-backed mailbox messages with user-owned BusinessContexts
using owned ``(connector_account_id, provider_message_id)`` provenance. Does
not retrieve mailbox content, attachment bytes, or invoke AI providers.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID

from app.application.exceptions import (
    AnalysisNotFoundError,
    BusinessContextCommunicationLinkConflictError,
    BusinessContextCommunicationLinkNotFoundError,
    BusinessContextNotFoundError,
    ConnectorAccountNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import AssociationSource, BusinessContextStatus
from app.domain.interfaces.analysis_repository import AnalysisRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models.business_context_communication_link import (
    BusinessContextCommunicationLink,
)

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100
_LINK_UNIQUE = "uq_bcc_links_context_connector_message"


class BusinessContextCommunicationLinkService:
    """Create, list, and remove authoritative BusinessContext provenance links.

    Ownership of the context and connector account is enforced on every mutate.
    Connector usability (ACTIVE / mail.read / credential) is intentionally not
    required for association: the link records already-known opaque provenance.
    Platform Owner role never bypasses object ownership.
    """

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory

    def associate(
        self,
        principal: AuthenticatedPrincipal,
        business_context_id: UUID,
        connector_account_id: UUID,
        provider_message_id: str,
        *,
        analysis_id: UUID | None = None,
    ) -> BusinessContextCommunicationLink:
        """Create a manual authoritative provenance link for an owned context.

        Does not call mailbox providers, attachment retrieve/scan/parse, or AI.
        """
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        try:
            with self._unit_of_work_factory() as uow:
                context = uow.business_contexts.get_owned(business_context_id, user_id)
                if context is None:
                    raise BusinessContextNotFoundError()
                if context.status is not BusinessContextStatus.ACTIVE:
                    raise BusinessContextCommunicationLinkConflictError()

                connector = uow.connector_accounts.get_owned(
                    connector_account_id, user_id
                )
                if connector is None:
                    raise ConnectorAccountNotFoundError()

                if analysis_id is not None:
                    analysis = uow.analysis_repository.get_by_id_for_user(
                        analysis_id, user_id
                    )
                    if analysis is None:
                        raise AnalysisNotFoundError()
                    _require_analysis_provenance_match(
                        analysis,
                        connector_account_id=connector_account_id,
                        provider_message_id=provider_message_id,
                    )

                existing = (
                    uow.business_context_communication_links.get_by_provenance_owned(
                        business_context_id,
                        connector_account_id,
                        provider_message_id,
                        user_id,
                    )
                )
                if existing is not None:
                    raise BusinessContextCommunicationLinkConflictError()

                link = BusinessContextCommunicationLink(
                    business_context_id=business_context_id,
                    owner_user_id=user_id,
                    connector_account_id=connector_account_id,
                    provider_message_id=provider_message_id,
                    associated_by_user_id=user_id,
                    association_source=AssociationSource.MANUAL,
                    analysis_id=analysis_id,
                )
                try:
                    stored = uow.business_context_communication_links.add(link)
                except PersistenceError as exc:
                    if _is_duplicate_link_failure(exc):
                        raise BusinessContextCommunicationLinkConflictError() from None
                    raise
                uow.commit()
        except (
            BusinessContextNotFoundError,
            BusinessContextCommunicationLinkConflictError,
            ConnectorAccountNotFoundError,
            AnalysisNotFoundError,
        ):
            raise
        except PersistenceError as exc:
            logger.warning(
                "business_context_link_persistence_failed",
                operation="associate",
                business_context_id=str(business_context_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "business_context_communication_link_created",
            operation="associate",
            link_id=str(stored.id),
            business_context_id=str(business_context_id),
            has_analysis_id=analysis_id is not None,
            duration_ms=elapsed_ms(started_at),
        )
        return stored

    def list_for_context(
        self,
        principal: AuthenticatedPrincipal,
        business_context_id: UUID,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[BusinessContextCommunicationLink]:
        """List provenance links for an owned context (including archived)."""
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        bounded = max(1, min(limit, _MAX_LIST_LIMIT))
        safe_offset = max(0, offset)
        try:
            with self._unit_of_work_factory() as uow:
                context = uow.business_contexts.get_owned(business_context_id, user_id)
                if context is None:
                    raise BusinessContextNotFoundError()
                links = uow.business_context_communication_links.list_for_context_owned(
                    business_context_id,
                    user_id,
                    bounded,
                    safe_offset,
                )
        except BusinessContextNotFoundError:
            raise
        except PersistenceError as exc:
            logger.warning(
                "business_context_link_persistence_failed",
                operation="list_for_context",
                business_context_id=str(business_context_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "business_context_communication_links_listed",
            operation="list_for_context",
            business_context_id=str(business_context_id),
            result_count=len(links),
            duration_ms=elapsed_ms(started_at),
        )
        return links

    def remove(
        self,
        principal: AuthenticatedPrincipal,
        business_context_id: UUID,
        link_id: UUID,
    ) -> None:
        """Remove only the association row for an owned context/link.

        Allowed for archived contexts. Does not delete analyses, workflows,
        connectors, credentials, or provider mail.
        """
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        try:
            with self._unit_of_work_factory() as uow:
                context = uow.business_contexts.get_owned(business_context_id, user_id)
                if context is None:
                    raise BusinessContextNotFoundError()
                link = uow.business_context_communication_links.get_owned(
                    link_id, user_id
                )
                if link is None or link.business_context_id != business_context_id:
                    raise BusinessContextCommunicationLinkNotFoundError()
                deleted = uow.business_context_communication_links.remove_owned(
                    link_id, user_id
                )
                if not deleted:
                    raise BusinessContextCommunicationLinkNotFoundError()
                uow.commit()
        except (
            BusinessContextNotFoundError,
            BusinessContextCommunicationLinkNotFoundError,
        ):
            raise
        except PersistenceError as exc:
            logger.warning(
                "business_context_link_persistence_failed",
                operation="remove",
                business_context_id=str(business_context_id),
                link_id=str(link_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "business_context_communication_link_removed",
            operation="remove",
            link_id=str(link_id),
            business_context_id=str(business_context_id),
            duration_ms=elapsed_ms(started_at),
        )

    def _require_existing_user(self, principal: AuthenticatedPrincipal) -> UUID:
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise BusinessContextNotFoundError()
        return user_id


def _require_analysis_provenance_match(
    analysis: AnalysisRecord,
    *,
    connector_account_id: UUID,
    provider_message_id: str,
) -> None:
    """Reject optional analysis_id when mailbox provenance does not match."""
    if (
        analysis.connector_account_id != connector_account_id
        or analysis.message_id != provider_message_id
    ):
        raise AnalysisNotFoundError()


def _is_duplicate_link_failure(exc: PersistenceError) -> bool:
    detail = str(exc).lower()
    message = getattr(exc, "message", "")
    combined = f"{detail} {message}".lower()
    return _LINK_UNIQUE in combined or "duplicate communication link" in combined
