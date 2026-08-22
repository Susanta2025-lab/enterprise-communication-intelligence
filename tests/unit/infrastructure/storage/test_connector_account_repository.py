"""Connector account repository tests using isolated SQLite."""

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.connector_account_repository import NewConnectorAccount
from app.infrastructure.storage.models import ConnectorAccount, User
from app.infrastructure.storage.repositories.connector_account import (
    SqlAlchemyConnectorAccountRepository,
)
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

_ISSUER = "https://issuer.example.invalid/"
_PROVIDER = "fake"
_ACCOUNT_A = "fake-account-001"
_ACCOUNT_B = "fake-account-002"
_CREDENTIAL_REF = "cred-ref-fake-001"
_REPO_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "app"
    / "infrastructure"
    / "storage"
    / "repositories"
    / "connector_account.py"
)


def _new_account(
    user_id: UUID,
    *,
    provider: str = _PROVIDER,
    external_account_id: str = _ACCOUNT_A,
    credential_ref: str | None = _CREDENTIAL_REF,
    granted_capabilities: tuple[CommunicationCapability, ...] | None = None,
) -> NewConnectorAccount:
    return NewConnectorAccount(
        user_id=user_id,
        provider=provider,
        external_account_id=external_account_id,
        credential_ref=credential_ref,
        granted_capabilities=granted_capabilities,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "owner-b")
        session.commit()
    return user_a, user_b


def test_create_and_get_owned_returns_same_account(session_factory: sessionmaker) -> None:
    """Creating an account should make the same UUID retrievable for the owner."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        created = repository.create(_new_account(user_a))
        session.commit()
        account_id = created.id

    assert isinstance(account_id, UUID)

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        found = repository.get_owned(account_id, user_a)
        assert found is not None
        assert found.id == account_id
        assert found.provider == _PROVIDER
        assert found.external_account_id == _ACCOUNT_A
        assert found.credential_ref == _CREDENTIAL_REF
        assert found.status is ConnectorAccountStatus.ACTIVE
        assert found.granted_capabilities is None


def test_get_requires_matching_user_id(session_factory: sessionmaker) -> None:
    """get_owned must not return another user's connector account."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        owned = repository.create(_new_account(user_a))
        session.commit()
        account_id = owned.id

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        assert repository.get_owned(account_id, user_a) is not None
        assert repository.get_owned(account_id, user_b) is None
        assert repository.get_owned(uuid4(), user_a) is None


def test_list_owned_excludes_other_users(session_factory: sessionmaker) -> None:
    """Each user should see only their own connector accounts."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        first = repository.create(_new_account(user_a, external_account_id=_ACCOUNT_A))
        session.commit()
        second = repository.create(_new_account(user_a, external_account_id=_ACCOUNT_B))
        session.commit()
        other = repository.create(_new_account(user_b, external_account_id=_ACCOUNT_A))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        owned_a = repository.list_owned(user_a, limit=20, offset=0)
        owned_b = repository.list_owned(user_b, limit=20, offset=0)

    assert [record.id for record in owned_a] == [second.id, first.id]
    assert [record.id for record in owned_b] == [other.id]


def test_list_is_bounded_and_offset(session_factory: sessionmaker) -> None:
    """List must honor limit and offset."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        first = repository.create(_new_account(user_a, external_account_id=_ACCOUNT_A))
        session.commit()
        second = repository.create(_new_account(user_a, external_account_id=_ACCOUNT_B))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        page = repository.list_owned(user_a, limit=1, offset=0)
        rest = repository.list_owned(user_a, limit=1, offset=1)
        assert [record.id for record in page] == [second.id]
        assert [record.id for record in rest] == [first.id]
        assert repository.list_owned(user_a, limit=0, offset=0) == []
        assert repository.list_owned(user_a, limit=20, offset=-1) == []


def test_duplicate_logical_account_is_unique_violation(
    session_factory: sessionmaker,
) -> None:
    """The same owner + provider + external account must not create a second row."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        first = repository.create(_new_account(user_a))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        with pytest.raises(PersistenceError) as exc_info:
            repository.create(_new_account(user_a))
        assert exc_info.value.message == "Connector account is already registered."
        session.rollback()
        found = repository.find_by_owner_provider_external_account(
            user_a, _PROVIDER, _ACCOUNT_A
        )
        assert found is not None
        assert found.id == first.id


def test_unrelated_integrity_error_is_generic(session_factory: sessionmaker) -> None:
    """Foreign-key failures must not be classified as duplicate accounts."""
    missing_user = uuid4()
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        with pytest.raises(PersistenceError) as exc_info:
            repository.create(_new_account(missing_user))
        assert exc_info.value.message == "Could not persist connector account."
        assert exc_info.value.message != "Connector account is already registered."


def test_disconnect_clears_credential_ref_and_is_idempotent(
    session_factory: sessionmaker,
) -> None:
    """Disconnect retains the row, sets disconnected, and nulls locator plus grants."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        owned = repository.create(
            _new_account(
                user_a,
                granted_capabilities=(
                    CommunicationCapability.MAIL_READ,
                    CommunicationCapability.MAIL_SEND,
                ),
            )
        )
        session.commit()
        account_id = owned.id

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        disconnected = repository.disconnect_owned(account_id, user_a)
        session.commit()

    assert disconnected is not None
    assert disconnected.status is ConnectorAccountStatus.DISCONNECTED
    assert disconnected.credential_ref is None
    assert disconnected.granted_capabilities is None
    assert disconnected.id == account_id
    assert disconnected.user_id == user_a
    assert disconnected.provider == _PROVIDER
    assert disconnected.external_account_id == _ACCOUNT_A
    assert _aware(disconnected.created_at) == _aware(owned.created_at)
    assert _aware(disconnected.updated_at) >= _aware(owned.updated_at)

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        again = repository.disconnect_owned(account_id, user_a)
        session.commit()
        assert again is not None
        assert again.status is ConnectorAccountStatus.DISCONNECTED
        assert again.credential_ref is None
        assert again.granted_capabilities is None
        assert _aware(again.created_at) == _aware(owned.created_at)
        assert _aware(again.updated_at) >= _aware(disconnected.updated_at)
        assert repository.disconnect_owned(account_id, user_b) is None
        assert repository.disconnect_owned(uuid4(), user_a) is None


def test_reactivate_replaces_credential_ref(session_factory: sessionmaker) -> None:
    """Reactivation restores active status and replaces the opaque locator."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        owned = repository.create(_new_account(user_a))
        session.commit()
        repository.disconnect_owned(owned.id, user_a)
        session.commit()
        restored = repository.reactivate_owned(owned.id, user_a, "cred-ref-fake-002")
        session.commit()

    assert restored is not None
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.credential_ref == "cred-ref-fake-002"
    assert restored.id == owned.id
    assert _aware(restored.created_at) == _aware(owned.created_at)
    assert _aware(restored.updated_at) >= _aware(owned.updated_at)


def test_uow_commit_and_rollback(session_factory: sessionmaker) -> None:
    """Connector account writes are visible only after an explicit commit."""
    user_a, _user_b = _create_users(session_factory)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        created = uow.connector_accounts.create(_new_account(user_a))
        uow.commit()

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        assert repository.get_owned(created.id, user_a) is not None

    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.connector_accounts.create(
            _new_account(user_a, external_account_id=_ACCOUNT_B)
        )

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        assert repository.find_by_owner_provider_external_account(
            user_a, _PROVIDER, _ACCOUNT_B
        ) is None


def test_deleting_user_cascades_connector_accounts(session_factory: sessionmaker) -> None:
    """SQLite FK enforcement should remove connector accounts when the user is deleted."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        saved = repository.create(_new_account(user_a))
        session.commit()
        account_id = saved.id

        user = session.get(User, user_a)
        assert user is not None
        session.delete(user)
        session.commit()

        remaining = session.scalars(
            select(ConnectorAccount).where(ConnectorAccount.id == account_id)
        ).all()
        assert remaining == []
        assert repository.get_owned(account_id, user_a) is None


def test_status_check_rejects_unknown_values(session_factory: sessionmaker) -> None:
    """Only active, disconnected, and reauth_required are valid status values."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO connector_accounts "
                    "(id, user_id, provider, external_account_id, credential_ref, "
                    "status, created_at, updated_at) "
                    "VALUES (:id, :user_id, :provider, :external_account_id, NULL, "
                    ":status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "user_id": str(user_a),
                    "provider": _PROVIDER,
                    "external_account_id": _ACCOUNT_A,
                    "status": "revoked",
                },
            )
            session.commit()


def test_reauth_required_status_and_null_capabilities_round_trip(
    session_factory: sessionmaker,
) -> None:
    """REAUTH_REQUIRED persists and legacy granted_capabilities remain NULL."""
    from sqlalchemy import update

    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        created = repository.create(_new_account(user_a))
        session.commit()
        session.execute(
            update(ConnectorAccount)
            .where(ConnectorAccount.id == created.id)
            .values(status=ConnectorAccountStatus.REAUTH_REQUIRED.value)
        )
        session.commit()
        found = repository.get_owned(created.id, user_a)
        restored = repository.reactivate_owned(created.id, user_a, "cred-ref-fake-003")
        session.commit()

    assert found is not None
    assert found.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert found.granted_capabilities is None
    assert restored is not None
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.granted_capabilities is None


def test_ownership_is_enforced_in_sql() -> None:
    """Get, list, and disconnect must filter user_id in SQL, not after fetch."""
    source = _REPO_SOURCE.read_text(encoding="utf-8")
    assert "session.get(" not in source
    assert "ConnectorAccount.user_id == user_id" in source
    assert "row.user_id !=" not in source
    assert "record.user_id !=" not in source


def test_credential_ref_is_the_only_credential_field(sqlite_engine: Engine) -> None:
    """ORM mapped columns must not include token or secret names."""
    inspector = inspect(sqlite_engine)
    columns = {column["name"] for column in inspector.get_columns("connector_accounts")}
    assert "credential_ref" in columns
    for name in (
        "access_token",
        "refresh_token",
        "token",
        "authorization_code",
        "client_secret",
        "jwt",
    ):
        assert name not in columns


def test_record_includes_internal_fields_not_required_by_result(
    session_factory: sessionmaker,
) -> None:
    """Repository records may contain user_id and credential_ref internally."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        created = repository.create(_new_account(user_a))
        session.commit()

    payload = asdict(created)
    assert "user_id" in payload
    assert "credential_ref" in payload
    assert payload["credential_ref"] == _CREDENTIAL_REF
