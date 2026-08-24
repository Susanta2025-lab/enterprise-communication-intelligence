"""PostgreSQL advisory-lock coordinator for cloud credential mutations.

Uses transaction-scoped ``pg_advisory_xact_lock`` so the lock is released on
commit, rollback, exception, or connection loss. The credential mutation
transaction deliberately holds one database connection while the infrequent
cloud control-plane write runs. No OAuth secret or token material is stored
in PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import CommunicationCredentialUnavailableError
from app.core.logging import get_logger
from app.core.telemetry import error_class
from app.infrastructure.credentials.mutation import (
    CredentialMutationCoordinator,
    advisory_lock_keys,
)

logger = get_logger(__name__)

_LOCK_SQL = text("SELECT pg_advisory_xact_lock(:key1, :key2)")


class PostgresCredentialMutationCoordinator(CredentialMutationCoordinator):
    """Serialize mutations per opaque locator using PostgreSQL advisory locks."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def lock(self, credential_ref: str) -> Iterator[None]:
        key1, key2 = advisory_lock_keys(credential_ref)
        session = self._session_factory()
        try:
            try:
                session.execute(_LOCK_SQL, {"key1": key1, "key2": key2})
            except SQLAlchemyError as exc:
                logger.warning(
                    "credential_mutation_lock_failed",
                    component="credential_mutation_coordinator",
                    error_class=error_class(exc),
                )
                raise CommunicationCredentialUnavailableError() from None
            try:
                yield
                session.commit()
            except Exception:
                session.rollback()
                raise
        finally:
            session.close()
