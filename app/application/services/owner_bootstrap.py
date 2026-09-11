"""Controlled first-owner bootstrap for Phase 19D.

Promotes an existing ECI user from ``application_role=user`` to ``owner``.
Does not create users. Does not accept email, JWT roles, or mailbox identity.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from uuid import UUID

from app.application.exceptions import (
    OwnerAlreadyExistsError,
    OwnerBootstrapConflictError,
    OwnerBootstrapExternalIdentityRequiredError,
    OwnerBootstrapTargetNotFoundError,
)
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import ApplicationRole
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_OPERATION = "promote_first_owner"


class FirstOwnerBootstrapResult(StrEnum):
    """Outcome of a controlled first-owner bootstrap attempt."""

    PROMOTED = "promoted"
    ALREADY_OWNER = "already_owner"


class FirstOwnerBootstrapService:
    """Operator-only first-owner promotion against persisted application_role."""

    def __init__(self, unit_of_work_factory: Callable[[], PersistenceUnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def promote_first_owner(self, user_id: UUID) -> FirstOwnerBootstrapResult:
        """Promote an existing mapped user to the sole platform owner.

        Identification is by internal ``users.id`` only. The target must already
        exist, must have an External ID mapping, and must currently be ``user``
        unless this same user is already ``owner`` (idempotent success).

        Fails closed when another owner already exists.
        """
        started_at = time.perf_counter()
        try:
            result = self._promote_first_owner(user_id)
        except (
            OwnerBootstrapTargetNotFoundError,
            OwnerBootstrapExternalIdentityRequiredError,
            OwnerAlreadyExistsError,
            OwnerBootstrapConflictError,
        ) as exc:
            logger.warning(
                "owner_bootstrap_failed",
                operation=_OPERATION,
                user_id=str(user_id),
                error_class=error_class(exc),
                duration_ms=elapsed_ms(started_at),
            )
            raise
        except PersistenceError as exc:
            logger.warning(
                "owner_bootstrap_failed",
                operation=_OPERATION,
                user_id=str(user_id),
                error_class=error_class(exc),
                duration_ms=elapsed_ms(started_at),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "owner_bootstrap_succeeded",
            operation=_OPERATION,
            user_id=str(user_id),
            previous_role=(
                ApplicationRole.USER.value
                if result is FirstOwnerBootstrapResult.PROMOTED
                else ApplicationRole.OWNER.value
            ),
            new_role=ApplicationRole.OWNER.value,
            result=result.value,
            duration_ms=elapsed_ms(started_at),
        )
        return result

    def _promote_first_owner(self, user_id: UUID) -> FirstOwnerBootstrapResult:
        with self._unit_of_work_factory() as uow:
            identities = uow.identity_repository
            current_role = identities.get_application_role_for_user(user_id)
            if current_role is None:
                raise OwnerBootstrapTargetNotFoundError()
            if not identities.user_has_external_identity(user_id):
                raise OwnerBootstrapExternalIdentityRequiredError()

            owner_count = identities.count_users_with_application_role(
                ApplicationRole.OWNER.value
            )
            if current_role == ApplicationRole.OWNER.value:
                return FirstOwnerBootstrapResult.ALREADY_OWNER
            if owner_count > 0:
                raise OwnerAlreadyExistsError()
            if current_role != ApplicationRole.USER.value:
                raise OwnerBootstrapConflictError()

            updated = identities.promote_user_role_from_user_to_owner(user_id)
            if not updated:
                raise OwnerBootstrapConflictError()
            uow.commit()
            return FirstOwnerBootstrapResult.PROMOTED
