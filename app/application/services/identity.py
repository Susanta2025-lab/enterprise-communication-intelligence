"""Resolve verified OIDC issuer+subject to an internal user UUID."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID

from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_DUPLICATE_IDENTITY = "External identity is already registered."


class IdentityResolver:
    """Map an authenticated principal to an internal user without using email."""

    def __init__(self, unit_of_work_factory: Callable[[], PersistenceUnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def resolve_or_create(self, principal: AuthenticatedPrincipal) -> UUID:
        """Return the internal user id for the principal, creating it on first use."""
        started_at = time.perf_counter()
        try:
            user_id, created = self._resolve_or_create(principal)
        except PersistenceError as exc:
            logger.warning(
                "identity_resolution_failed",
                operation="resolve_or_create",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "identity_resolved",
            operation="resolve_or_create",
            created_identity=created,
            duration_ms=elapsed_ms(started_at),
        )
        return user_id

    def find_existing(self, principal: AuthenticatedPrincipal) -> UUID | None:
        """Return the internal user id when a mapping already exists.

        Read-only: does not create a user.
        """
        started_at = time.perf_counter()
        try:
            with self._unit_of_work_factory() as uow:
                user_id = uow.identity_repository.get_user_id_by_external_identity(
                    principal.issuer,
                    principal.subject,
                )
        except PersistenceError as exc:
            logger.warning(
                "identity_resolution_failed",
                operation="find_existing",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "identity_resolved",
            operation="find_existing",
            created_identity=False,
            duration_ms=elapsed_ms(started_at),
        )
        return user_id

    def _resolve_or_create(self, principal: AuthenticatedPrincipal) -> tuple[UUID, bool]:
        with self._unit_of_work_factory() as uow:
            existing = uow.identity_repository.get_user_id_by_external_identity(
                principal.issuer,
                principal.subject,
            )
            if existing is not None:
                return existing, False

            try:
                user_id = uow.identity_repository.create_user_with_external_identity(
                    principal.issuer,
                    principal.subject,
                )
                uow.commit()
                return user_id, True
            except PersistenceError as exc:
                if exc.message != _DUPLICATE_IDENTITY:
                    raise
                uow.rollback()

        winner = self._lookup(principal)
        if winner is not None:
            return winner, False
        raise PersistenceError("Could not persist identity.")

    def _lookup(self, principal: AuthenticatedPrincipal) -> UUID | None:
        with self._unit_of_work_factory() as uow:
            return uow.identity_repository.get_user_id_by_external_identity(
                principal.issuer,
                principal.subject,
            )
