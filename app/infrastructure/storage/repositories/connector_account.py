"""SQLAlchemy ConnectorAccountRepository implementation."""

from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.enums import ConnectorAccountStatus
from app.domain.interfaces.connector_account_repository import (
    ConnectorAccountRecord,
    ConnectorAccountRepository,
    NewConnectorAccount,
)
from app.infrastructure.storage.models import ConnectorAccount, utc_now

_CONNECTOR_ACCOUNT_UNIQUE = "uq_connector_accounts_user_provider_external_account"
_DUPLICATE = "Connector account is already registered."
_GENERIC_FAILURE = "Could not persist connector account."
_MAX_LIST_LIMIT = 100


class SqlAlchemyConnectorAccountRepository(ConnectorAccountRepository):
    """Persist connector accounts with ownership enforced in SQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, account: NewConnectorAccount) -> ConnectorAccountRecord:
        """Insert an active connector account for ``account.user_id``."""
        row = ConnectorAccount(
            id=uuid4(),
            user_id=account.user_id,
            provider=account.provider,
            external_account_id=account.external_account_id,
            credential_ref=account.credential_ref,
            status=ConnectorAccountStatus.ACTIVE.value,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            if _is_connector_account_unique_violation(exc):
                raise PersistenceError(_DUPLICATE) from exc
            raise PersistenceError(_GENERIC_FAILURE) from exc
        return _to_record(row)

    def find_by_owner_provider_external_account(
        self,
        user_id: UUID,
        provider: str,
        external_account_id: str,
    ) -> ConnectorAccountRecord | None:
        """Return the account for the owner and provider-native identity, if any."""
        statement = select(ConnectorAccount).where(
            ConnectorAccount.user_id == user_id,
            ConnectorAccount.provider == provider,
            ConnectorAccount.external_account_id == external_account_id,
        )
        row = self._session.scalars(statement).first()
        if row is None:
            return None
        return _to_record(row)

    def get_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
    ) -> ConnectorAccountRecord | None:
        """Return the account only when it is owned by ``user_id``."""
        statement = select(ConnectorAccount).where(
            ConnectorAccount.id == connector_account_id,
            ConnectorAccount.user_id == user_id,
        )
        row = self._session.scalars(statement).first()
        if row is None:
            return None
        return _to_record(row)

    def list_owned(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ConnectorAccountRecord]:
        """Return a bounded page of accounts owned by ``user_id``, newest first.

        Non-positive ``limit`` or negative ``offset`` yield an empty page so
        those values are never passed to SQL.
        """
        if limit < 1 or offset < 0:
            return []
        statement = (
            select(ConnectorAccount)
            .where(ConnectorAccount.user_id == user_id)
            .order_by(ConnectorAccount.created_at.desc(), ConnectorAccount.id.desc())
            .limit(min(limit, _MAX_LIST_LIMIT))
            .offset(offset)
        )
        return [_to_record(row) for row in self._session.scalars(statement).all()]

    def disconnect_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
    ) -> ConnectorAccountRecord | None:
        """Mark the owned account disconnected and clear ``credential_ref``.

        The owned UPDATE always assigns ``updated_at``, including when the row
        is already disconnected, so repeated disconnect stays idempotent for
        status and locator while remaining explicit about the write.
        """
        statement = (
            update(ConnectorAccount)
            .where(
                ConnectorAccount.id == connector_account_id,
                ConnectorAccount.user_id == user_id,
            )
            .values(
                status=ConnectorAccountStatus.DISCONNECTED.value,
                credential_ref=None,
                updated_at=utc_now(),
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            return None
        return self.get_owned(connector_account_id, user_id)

    def reactivate_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
        credential_ref: str | None,
    ) -> ConnectorAccountRecord | None:
        """Reactivate an owned disconnected account and replace ``credential_ref``."""
        statement = (
            update(ConnectorAccount)
            .where(
                ConnectorAccount.id == connector_account_id,
                ConnectorAccount.user_id == user_id,
            )
            .values(
                status=ConnectorAccountStatus.ACTIVE.value,
                credential_ref=credential_ref,
                updated_at=utc_now(),
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            return None
        return self.get_owned(connector_account_id, user_id)


def _to_record(row: ConnectorAccount) -> ConnectorAccountRecord:
    return ConnectorAccountRecord(
        id=row.id,
        user_id=row.user_id,
        provider=row.provider,
        external_account_id=row.external_account_id,
        credential_ref=row.credential_ref,
        status=ConnectorAccountStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _constraint_name(exc: IntegrityError) -> str | None:
    """Return a driver constraint name when one is available (psycopg ``diag``)."""
    orig = exc.orig
    if orig is None:
        return None
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if isinstance(name, str) and name:
        return name
    return None


def _is_connector_account_unique_violation(exc: IntegrityError) -> bool:
    """Return True only for the owner+provider+external-account uniqueness constraint.

    PostgreSQL/psycopg exposes ``diag.constraint_name``. SQLite reports
    ``UNIQUE constraint failed`` with the three column names. Unrelated
    integrity failures must not be classified as duplicates.
    """
    if _constraint_name(exc) == _CONNECTOR_ACCOUNT_UNIQUE:
        return True
    orig = exc.orig
    diagnostic = str(orig) if orig is not None else ""
    if _CONNECTOR_ACCOUNT_UNIQUE in diagnostic:
        return True
    lowered = diagnostic.lower()
    return (
        "unique constraint failed" in lowered
        and "connector_accounts.user_id" in lowered
        and "connector_accounts.provider" in lowered
        and "connector_accounts.external_account_id" in lowered
    )
