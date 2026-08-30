"""PostgreSQL connector account schema, ownership, unique, and cascade tests."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, inspect, select, text, update
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
_ACCOUNT = "fake-account-001"
_CREDENTIAL_REF = "cred-ref-fake-001"
_UNIQUE = "uq_connector_accounts_user_provider_external_account"


def _new_account(
    user_id: UUID,
    *,
    external_account_id: str = _ACCOUNT,
    credential_ref: str | None = _CREDENTIAL_REF,
    granted_capabilities: tuple[CommunicationCapability, ...] | None = None,
) -> NewConnectorAccount:
    return NewConnectorAccount(
        user_id=user_id,
        provider=_PROVIDER,
        external_account_id=external_account_id,
        credential_ref=credential_ref,
        granted_capabilities=granted_capabilities,
    )


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "owner-b")
        session.commit()
    return user_a, user_b


def test_connector_accounts_table_exists(postgres_engine: Engine) -> None:
    """connector_accounts is present and credential-token tables are not."""
    tables = set(inspect(postgres_engine).get_table_names())
    assert "connector_accounts" in tables
    assert "connector_credentials" not in tables
    assert "oauth_tokens" not in tables
    assert "messages" not in tables


def test_connector_account_column_types(postgres_engine: Engine) -> None:
    """UUID, timestamptz, and nullable locator columns match the intended schema."""
    types = _udt_types(postgres_engine)
    assert types[("connector_accounts", "id")] == "uuid"
    assert types[("connector_accounts", "user_id")] == "uuid"
    assert types[("connector_accounts", "created_at")] == "timestamptz"
    assert types[("connector_accounts", "updated_at")] == "timestamptz"
    assert types[("connector_accounts", "provider")] == "text"
    assert types[("connector_accounts", "external_account_id")] == "text"
    assert types[("connector_accounts", "credential_ref")] == "text"
    assert types[("connector_accounts", "status")] == "text"
    inspector = inspect(postgres_engine)
    columns = {
        column["name"]: column["nullable"]
        for column in inspector.get_columns("connector_accounts")
    }
    assert columns["credential_ref"] is True
    assert columns["provider"] is False
    assert columns["status"] is False
    assert columns["external_account_id"] is False
    assert columns["granted_capabilities"] is True
    assert columns["display_identity"] is True
    forbidden = {
        "access_token",
        "refresh_token",
        "token",
        "authorization_code",
        "client_secret",
        "jwt",
    }
    assert set(columns).isdisjoint(forbidden)


def test_foreign_key_cascades_to_users(postgres_engine: Engine) -> None:
    """connector_accounts.user_id references users.id with ON DELETE CASCADE."""
    inspector = inspect(postgres_engine)
    fks = inspector.get_foreign_keys("connector_accounts")
    assert any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        and str((fk.get("options") or {}).get("ondelete", "")).upper() == "CASCADE"
        for fk in fks
    )


def test_unique_constraint_named(postgres_engine: Engine) -> None:
    """Owner + provider + external account uniqueness uses the stable name."""
    inspector = inspect(postgres_engine)
    uniques = inspector.get_unique_constraints("connector_accounts")
    matching = [
        constraint
        for constraint in uniques
        if tuple(constraint["column_names"])
        == ("user_id", "provider", "external_account_id")
    ]
    assert matching
    assert matching[0]["name"] == _UNIQUE


def test_status_check_and_list_index(postgres_engine: Engine) -> None:
    """Status is constrained and the ownership/list index exists."""
    inspector = inspect(postgres_engine)
    checks = inspector.get_check_constraints("connector_accounts")
    named = [constraint for constraint in checks if constraint["name"] == (
        "ck_connector_accounts_status"
    )]
    assert named
    indexes = {index["name"] for index in inspector.get_indexes("connector_accounts")}
    assert "ix_connector_accounts_user_id_created_at_id" in indexes
    uniques = inspector.get_unique_constraints("connector_accounts")
    unique_indexes = [
        index for index in inspector.get_indexes("connector_accounts") if index.get("unique")
    ]
    for constraint in uniques:
        assert "credential_ref" not in constraint["column_names"]
    for index in unique_indexes:
        assert "credential_ref" not in (index.get("column_names") or [])


def test_create_lookup_ownership_and_python_uuid(session_factory: sessionmaker) -> None:
    """PostgreSQL UUID columns round-trip and ownership is enforced in SQL."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        created = repository.create(_new_account(user_a))
        session.commit()

    assert isinstance(created.id, UUID)
    assert created.created_at.tzinfo is not None

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        owned = repository.get_owned(created.id, user_a)
        assert owned is not None
        assert owned.id == created.id
        assert repository.get_owned(created.id, user_b) is None
        listed_b = repository.list_owned(user_b, limit=20, offset=0)
        assert listed_b == []


def test_duplicate_named_constraint_is_discoverable(session_factory: sessionmaker) -> None:
    """psycopg must report the named unique constraint on duplicates."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        repository.create(_new_account(user_a))
        session.commit()

    with session_factory() as session:
        row = ConnectorAccount(
            id=uuid4(),
            user_id=user_a,
            provider=_PROVIDER,
            external_account_id=_ACCOUNT,
            credential_ref=None,
            status=ConnectorAccountStatus.ACTIVE.value,
        )
        session.add(row)
        with pytest.raises(IntegrityError) as exc_info:
            session.flush()

    orig = exc_info.value.orig
    assert orig is not None
    diag = getattr(orig, "diag", None)
    assert diag is not None
    assert diag.constraint_name == _UNIQUE


def test_repository_translates_unique_violation(
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IntegrityError on the named constraint becomes PersistenceError."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        first = repository.create(_new_account(user_a))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        monkeypatch.setattr(
            repository,
            "find_by_owner_provider_external_account",
            lambda *_args: None,
        )
        with pytest.raises(PersistenceError) as exc_info:
            repository.create(_new_account(user_a))
        assert exc_info.value.message == "Connector account is already registered."

    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(ConnectorAccount))
        repository = SqlAlchemyConnectorAccountRepository(session)
        found = repository.find_by_owner_provider_external_account(
            user_a, _PROVIDER, _ACCOUNT
        )
        assert count == 1
        assert found is not None
        assert found.id == first.id


def test_unrelated_integrity_error_is_generic(session_factory: sessionmaker) -> None:
    """Foreign-key failures remain a generic persistence error."""
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        with pytest.raises(PersistenceError) as exc_info:
            repository.create(_new_account(uuid4()))
        assert exc_info.value.message == "Could not persist connector account."


def test_status_check_rejects_unknown_values(session_factory: sessionmaker) -> None:
    """The named check constraint rejects values other than active/disconnected."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        with pytest.raises(IntegrityError) as exc_info:
            session.execute(
                text(
                    "INSERT INTO connector_accounts "
                    "(id, user_id, provider, external_account_id, credential_ref, "
                    "status, created_at, updated_at) "
                    "VALUES (:id, :user_id, :provider, :external_account_id, NULL, "
                    ":status, NOW(), NOW())"
                ),
                {
                    "id": uuid4(),
                    "user_id": user_a,
                    "provider": _PROVIDER,
                    "external_account_id": _ACCOUNT,
                    "status": "revoked",
                },
            )
            session.flush()

    orig = exc_info.value.orig
    assert orig is not None
    diag = getattr(orig, "diag", None)
    if diag is not None:
        assert diag.constraint_name == "ck_connector_accounts_status"


def test_disconnect_rowcount_and_idempotent_update(session_factory: sessionmaker) -> None:
    """Disconnect updates the owned row and is indistinguishable for cross-user."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        created = repository.create(_new_account(user_a))
        session.commit()

    with session_factory() as session:
        cross_user = session.execute(
            update(ConnectorAccount)
            .where(
                ConnectorAccount.id == created.id,
                ConnectorAccount.user_id == user_b,
            )
            .values(status=ConnectorAccountStatus.DISCONNECTED.value)
        )
        assert cross_user.rowcount == 0
        owned = session.execute(
            update(ConnectorAccount)
            .where(
                ConnectorAccount.id == created.id,
                ConnectorAccount.user_id == user_a,
            )
            .values(
                status=ConnectorAccountStatus.DISCONNECTED.value,
                credential_ref=None,
            )
        )
        assert owned.rowcount == 1
        session.rollback()

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        disconnected = repository.disconnect_owned(created.id, user_a)
        session.commit()
        assert disconnected is not None
        assert disconnected.status is ConnectorAccountStatus.DISCONNECTED
        assert disconnected.credential_ref is None
        assert disconnected.granted_capabilities is None
        again = repository.disconnect_owned(created.id, user_a)
        session.commit()
        assert again is not None
        assert again.status is ConnectorAccountStatus.DISCONNECTED
        assert again.credential_ref is None
        assert again.granted_capabilities is None
        assert repository.disconnect_owned(created.id, user_b) is None


def test_mark_reauth_required_and_concurrent_reactivate(
    session_factory: sessionmaker,
) -> None:
    """REAUTH_REQUIRED preserves locator; concurrent reactivation has one winner."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        created = repository.create(
            _new_account(
                user_a,
                granted_capabilities=(
                    CommunicationCapability.MAIL_READ,
                    CommunicationCapability.MAIL_SEND,
                ),
            )
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        marked = repository.mark_reauth_required_owned(created.id, user_a)
        session.commit()
        assert marked is not None
        assert marked.status is ConnectorAccountStatus.REAUTH_REQUIRED
        assert marked.credential_ref == _CREDENTIAL_REF
        assert marked.granted_capabilities == (
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        )
        assert repository.mark_reauth_required_owned(created.id, user_b) is None
        winner = repository.reactivate_owned(
            created.id,
            user_a,
            "oauth-winner-locator-01",
            granted_capabilities=(CommunicationCapability.MAIL_READ,),
            replace_granted_capabilities=True,
        )
        session.commit()
        loser = repository.reactivate_owned(
            created.id,
            user_a,
            "oauth-loser-locator-02",
            granted_capabilities=(
                CommunicationCapability.MAIL_READ,
                CommunicationCapability.MAIL_SEND,
            ),
            replace_granted_capabilities=True,
        )
        assert winner is not None
        assert winner.status is ConnectorAccountStatus.ACTIVE
        assert winner.credential_ref == "oauth-winner-locator-01"
        assert loser is None


def test_deleting_user_cascades_connector_accounts(session_factory: sessionmaker) -> None:
    """PostgreSQL ON DELETE CASCADE must remove connector account rows."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        created = repository.create(_new_account(user_a))
        session.commit()
        session.execute(delete(User).where(User.id == user_a))
        session.commit()
        remaining = session.scalars(
            select(ConnectorAccount).where(ConnectorAccount.id == created.id)
        ).all()
        assert remaining == []


def test_uow_commit_and_rollback(session_factory: sessionmaker) -> None:
    """Connector account writes follow the same unit-of-work commit rules."""
    user_a, _user_b = _create_users(session_factory)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        created = uow.connector_accounts.create(_new_account(user_a))
        uow.commit()

    with session_factory() as session:
        repository = SqlAlchemyConnectorAccountRepository(session)
        assert repository.get_owned(created.id, user_a) is not None

    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.connector_accounts.create(
            _new_account(user_a, external_account_id="fake-account-002")
        )

    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(ConnectorAccount))
        assert count == 1


def _udt_types(engine: Engine) -> dict[tuple[str, str], str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT table_name, column_name, udt_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'connector_accounts'
                """
            )
        ).all()
    return {(row.table_name, row.column_name): row.udt_name for row in rows}
