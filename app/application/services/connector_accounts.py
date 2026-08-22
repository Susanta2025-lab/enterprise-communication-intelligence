"""User-owned connector account management.

OAuth token exchange, secret-store resolution, and vendor mailbox access are
intentionally outside this service. Future authorization happens before a short
connector-account unit of work, never inside a long database transaction.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.exceptions import (
    ConnectorAccountInvalidRequestError,
    ConnectorAccountNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.connector_account_repository import (
    ConnectorAccountRecord,
    NewConnectorAccount,
)
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_DUPLICATE = "Connector account is already registered."
_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100
_PROVIDER_SLUG = re.compile(r"[a-z][a-z0-9_]{0,62}")


@dataclass(frozen=True, slots=True)
class ConnectorAccountResult:
    """Application-facing connector account. Omits ownership and credential locators."""

    id: UUID
    provider: str
    external_account_id: str
    status: ConnectorAccountStatus
    granted_capabilities: tuple[CommunicationCapability, ...] | None
    created_at: datetime
    updated_at: datetime


class ConnectorAccountService:
    """Register, list, retrieve, and disconnect user-owned connector accounts."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory

    def register(
        self,
        principal: AuthenticatedPrincipal,
        provider: str,
        external_account_id: str,
        credential_ref: str | None = None,
    ) -> ConnectorAccountResult:
        """Create, reuse, or reactivate the logical connector account.

        Identity resolution commits separately. The connector-account unit of
        work only writes ``connector_accounts``.

        An already-active row is returned as-is. ``credential_ref`` is not
        replaced. Disconnect then register is the 10B path for a new locator.
        ``credential_ref=None`` cannot be distinguished from an omitted
        argument; both mean no locator.
        """
        started_at = time.perf_counter()
        provider_slug = _normalize_provider(provider)
        account_key = _normalize_external_account_id(external_account_id)
        locator = _normalize_credential_ref(credential_ref)
        user_id = self._identity_resolver.resolve_or_create(principal)
        try:
            record, outcome = self._register_or_reuse(user_id, provider_slug, account_key, locator)
        except PersistenceError as exc:
            logger.warning(
                "connector_account_persistence_failed",
                operation="register",
                provider=provider_slug,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        event = {
            "registered": "connector_account_registered",
            "reused": "connector_account_reused",
            "reactivated": "connector_account_reactivated",
        }[outcome]
        logger.info(
            event,
            operation="register",
            provider=provider_slug,
            connector_id=str(record.id),
            created_account=outcome == "registered",
            reactivated=outcome == "reactivated",
            duration_ms=elapsed_ms(started_at),
        )
        return _to_result(record)

    def list_owned(
        self,
        principal: AuthenticatedPrincipal,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[ConnectorAccountResult]:
        """Return a bounded page of accounts owned by the principal."""
        started_at = time.perf_counter()
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            logger.info(
                "connector_accounts_listed",
                operation="list",
                result_count=0,
                duration_ms=elapsed_ms(started_at),
            )
            return []
        page_limit = min(limit, _MAX_LIST_LIMIT) if limit >= 1 else limit
        try:
            with self._unit_of_work_factory() as uow:
                records = uow.connector_accounts.list_owned(user_id, page_limit, offset)
        except PersistenceError as exc:
            logger.warning(
                "connector_account_persistence_failed",
                operation="list",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "connector_accounts_listed",
            operation="list",
            result_count=len(records),
            duration_ms=elapsed_ms(started_at),
        )
        return [_to_result(record) for record in records]

    def get_owned(
        self,
        principal: AuthenticatedPrincipal,
        connector_account_id: UUID,
    ) -> ConnectorAccountResult:
        """Return an owned account or raise not-found."""
        started_at = time.perf_counter()
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise ConnectorAccountNotFoundError()
        try:
            with self._unit_of_work_factory() as uow:
                record = uow.connector_accounts.get_owned(connector_account_id, user_id)
        except PersistenceError as exc:
            logger.warning(
                "connector_account_persistence_failed",
                operation="get",
                connector_id=str(connector_account_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        if record is None:
            raise ConnectorAccountNotFoundError()

        logger.info(
            "connector_account_retrieved",
            operation="get",
            provider=record.provider,
            connector_id=str(record.id),
            duration_ms=elapsed_ms(started_at),
        )
        return _to_result(record)

    def disconnect_owned(
        self,
        principal: AuthenticatedPrincipal,
        connector_account_id: UUID,
    ) -> ConnectorAccountResult:
        """Disconnect an owned account. Idempotent for already-disconnected rows."""
        started_at = time.perf_counter()
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise ConnectorAccountNotFoundError()
        try:
            with self._unit_of_work_factory() as uow:
                record = uow.connector_accounts.disconnect_owned(connector_account_id, user_id)
                if record is not None:
                    uow.commit()
        except PersistenceError as exc:
            logger.warning(
                "connector_account_persistence_failed",
                operation="disconnect",
                connector_id=str(connector_account_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        if record is None:
            raise ConnectorAccountNotFoundError()

        logger.info(
            "connector_account_disconnected",
            operation="disconnect",
            provider=record.provider,
            connector_id=str(record.id),
            duration_ms=elapsed_ms(started_at),
        )
        return _to_result(record)

    def _register_or_reuse(
        self,
        user_id: UUID,
        provider: str,
        external_account_id: str,
        credential_ref: str | None,
    ) -> tuple[ConnectorAccountRecord, str]:
        with self._unit_of_work_factory() as uow:
            existing = uow.connector_accounts.find_by_owner_provider_external_account(
                user_id,
                provider,
                external_account_id,
            )
            if existing is None:
                try:
                    created = uow.connector_accounts.create(
                        NewConnectorAccount(
                            user_id=user_id,
                            provider=provider,
                            external_account_id=external_account_id,
                            credential_ref=credential_ref,
                        )
                    )
                    uow.commit()
                    return created, "registered"
                except PersistenceError as exc:
                    if exc.message != _DUPLICATE:
                        raise
                    uow.rollback()
            elif existing.status in {
                ConnectorAccountStatus.DISCONNECTED,
                ConnectorAccountStatus.REAUTH_REQUIRED,
            }:
                reactivated = uow.connector_accounts.reactivate_owned(
                    existing.id,
                    user_id,
                    credential_ref,
                )
                if reactivated is None:
                    raise PersistenceError("Could not persist connector account.")
                uow.commit()
                return reactivated, "reactivated"
            else:
                return existing, "reused"

        winner = self._lookup(user_id, provider, external_account_id)
        if winner is not None:
            return winner, "reused"
        raise PersistenceError("Could not persist connector account.")

    def _lookup(
        self,
        user_id: UUID,
        provider: str,
        external_account_id: str,
    ) -> ConnectorAccountRecord | None:
        with self._unit_of_work_factory() as uow:
            return uow.connector_accounts.find_by_owner_provider_external_account(
                user_id,
                provider,
                external_account_id,
            )


def _to_result(record: ConnectorAccountRecord) -> ConnectorAccountResult:
    return ConnectorAccountResult(
        id=record.id,
        provider=record.provider,
        external_account_id=record.external_account_id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        granted_capabilities=record.granted_capabilities,
    )


def _normalize_provider(provider: str) -> str:
    slug = provider.strip()
    if _PROVIDER_SLUG.fullmatch(slug) is None:
        raise ConnectorAccountInvalidRequestError()
    return slug


def _normalize_external_account_id(external_account_id: str) -> str:
    value = external_account_id.strip()
    if not value:
        raise ConnectorAccountInvalidRequestError()
    return value


def _normalize_credential_ref(credential_ref: str | None) -> str | None:
    if credential_ref is None:
        return None
    value = credential_ref.strip()
    if not value:
        return None
    return value
