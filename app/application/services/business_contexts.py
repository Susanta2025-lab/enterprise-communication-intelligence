"""BusinessContext CRUD and lifecycle use cases.

Creates and manages user-owned organizational contexts. Ownership is always
bound from the authenticated principal via ``IdentityResolver``; clients cannot
supply ``user_id``. Platform Owner role never bypasses object ownership.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from app.application.exceptions import (
    BusinessContextConflictError,
    BusinessContextNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import BusinessContextStatus, BusinessContextType
from app.domain.exceptions import (
    BusinessContextNotMutableError,
    InvalidBusinessContextTransitionError,
)
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models.business_context import BusinessContext

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100
_UNSET: object = object()


class BusinessContextService:
    """Create, retrieve, list, update, archive, and restore owned contexts."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory

    def create(
        self,
        principal: AuthenticatedPrincipal,
        *,
        type: BusinessContextType,
        title: str,
        description: str | None = None,
        reference: str | None = None,
    ) -> BusinessContext:
        """Create an active BusinessContext owned by the authenticated user.

        Uses ``resolve_or_create`` so application login alone is sufficient;
        mailbox connection is not required.
        """
        started_at = time.perf_counter()
        user_id = self._identity_resolver.resolve_or_create(principal)
        try:
            with self._unit_of_work_factory() as uow:
                context = BusinessContext(
                    owner_user_id=user_id,
                    type=type,
                    title=title,
                    description=description,
                    reference=reference,
                )
                stored = uow.business_contexts.add(context)
                uow.commit()
        except PersistenceError as exc:
            logger.warning(
                "business_context_persistence_failed",
                operation="create",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "business_context_created",
            operation="create",
            business_context_id=str(stored.id),
            context_type=stored.type.value,
            duration_ms=elapsed_ms(started_at),
        )
        return stored

    def get(
        self,
        principal: AuthenticatedPrincipal,
        context_id: UUID,
    ) -> BusinessContext:
        """Return an owned BusinessContext or raise not-found."""
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        try:
            with self._unit_of_work_factory() as uow:
                context = uow.business_contexts.get_owned(context_id, user_id)
        except PersistenceError as exc:
            logger.warning(
                "business_context_persistence_failed",
                operation="get",
                business_context_id=str(context_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        if context is None:
            raise BusinessContextNotFoundError()

        logger.info(
            "business_context_retrieved",
            operation="get",
            business_context_id=str(context.id),
            duration_ms=elapsed_ms(started_at),
        )
        return context

    def list(
        self,
        principal: AuthenticatedPrincipal,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
        *,
        status: BusinessContextStatus | None = BusinessContextStatus.ACTIVE,
        type: BusinessContextType | None = None,
        reference: str | None = None,
    ) -> list[BusinessContext]:
        """Return a bounded page of contexts owned by the caller.

        Default ``status`` is ``ACTIVE``. Pass ``None`` for status to include
        every lifecycle state. Callers without an identity mapping receive an
        empty page.
        """
        started_at = time.perf_counter()
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            return []
        page_limit = max(1, min(limit, _MAX_LIST_LIMIT))
        safe_offset = max(0, offset)
        try:
            with self._unit_of_work_factory() as uow:
                contexts = uow.business_contexts.list_owned(
                    user_id,
                    page_limit,
                    safe_offset,
                    status=status,
                    type=type,
                    reference=reference,
                )
        except PersistenceError as exc:
            logger.warning(
                "business_context_persistence_failed",
                operation="list",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "business_contexts_listed",
            operation="list",
            result_count=len(contexts),
            duration_ms=elapsed_ms(started_at),
        )
        return contexts

    def update(
        self,
        principal: AuthenticatedPrincipal,
        context_id: UUID,
        *,
        type: BusinessContextType | None = None,
        title: str | None = None,
        description: str | None | object = _UNSET,
        reference: str | None | object = _UNSET,
    ) -> BusinessContext:
        """Partially update mutable fields on an owned active context."""
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        try:
            with self._unit_of_work_factory() as uow:
                context = uow.business_contexts.get_owned(context_id, user_id)
                if context is None:
                    raise BusinessContextNotFoundError()
                try:
                    update_kwargs: dict[str, Any] = {}
                    if type is not None:
                        update_kwargs["type"] = type
                    if title is not None:
                        update_kwargs["title"] = title
                    if description is not _UNSET:
                        update_kwargs["description"] = description
                    if reference is not _UNSET:
                        update_kwargs["reference"] = reference
                    context.apply_update(**update_kwargs)
                except BusinessContextNotMutableError:
                    raise BusinessContextConflictError() from None
                except InvalidBusinessContextTransitionError:
                    raise BusinessContextConflictError() from None
                saved = uow.business_contexts.save_owned(context)
                if saved is None:
                    raise BusinessContextNotFoundError()
                uow.commit()
        except (BusinessContextNotFoundError, BusinessContextConflictError):
            raise
        except PersistenceError as exc:
            logger.warning(
                "business_context_persistence_failed",
                operation="update",
                business_context_id=str(context_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "business_context_updated",
            operation="update",
            business_context_id=str(saved.id),
            duration_ms=elapsed_ms(started_at),
        )
        return saved

    def archive(
        self,
        principal: AuthenticatedPrincipal,
        context_id: UUID,
    ) -> BusinessContext:
        """Archive an owned context. Idempotent when already archived."""
        return self._apply_lifecycle(principal, context_id, operation="archive")

    def restore(
        self,
        principal: AuthenticatedPrincipal,
        context_id: UUID,
    ) -> BusinessContext:
        """Restore an owned archived context. Idempotent when already active."""
        return self._apply_lifecycle(principal, context_id, operation="restore")

    def _apply_lifecycle(
        self,
        principal: AuthenticatedPrincipal,
        context_id: UUID,
        *,
        operation: str,
    ) -> BusinessContext:
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        try:
            with self._unit_of_work_factory() as uow:
                context = uow.business_contexts.get_owned(context_id, user_id)
                if context is None:
                    raise BusinessContextNotFoundError()
                try:
                    if operation == "archive":
                        context.archive()
                    else:
                        context.restore()
                except InvalidBusinessContextTransitionError:
                    raise BusinessContextConflictError() from None
                saved = uow.business_contexts.save_owned(context)
                if saved is None:
                    raise BusinessContextNotFoundError()
                uow.commit()
        except (BusinessContextNotFoundError, BusinessContextConflictError):
            raise
        except PersistenceError as exc:
            logger.warning(
                "business_context_persistence_failed",
                operation=operation,
                business_context_id=str(context_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "business_context_lifecycle",
            operation=operation,
            business_context_id=str(saved.id),
            status=saved.status.value,
            duration_ms=elapsed_ms(started_at),
        )
        return saved

    def _require_existing_user(self, principal: AuthenticatedPrincipal) -> UUID:
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise BusinessContextNotFoundError()
        return user_id
