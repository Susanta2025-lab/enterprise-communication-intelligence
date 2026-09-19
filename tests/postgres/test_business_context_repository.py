"""PostgreSQL BusinessContext repository ownership and schema tests."""

from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.domain.enums import ApplicationRole, BusinessContextStatus, BusinessContextType
from app.domain.models.business_context import BusinessContext
from app.infrastructure.storage.repositories.business_context import (
    SqlAlchemyBusinessContextRepository,
)
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository

_ISSUER = "https://issuer.example.invalid/"


def _context(owner_user_id: UUID, *, title: str = "Postgres matter") -> BusinessContext:
    return BusinessContext(
        owner_user_id=owner_user_id,
        type=BusinessContextType.MATTER,
        title=title,
        reference="PG-REF-1",
    )


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "ctx-owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "ctx-owner-b")
        session.commit()
    return user_a, user_b


def test_postgres_business_contexts_schema(postgres_engine: Engine) -> None:
    """PostgreSQL business_contexts has ADR-029 columns, checks, and indexes."""
    inspector = inspect(postgres_engine)
    assert "business_contexts" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("business_contexts")}
    assert columns == {
        "id",
        "user_id",
        "type",
        "title",
        "description",
        "reference",
        "status",
        "archived_at",
        "created_at",
        "updated_at",
    }
    indexes = {index["name"] for index in inspector.get_indexes("business_contexts")}
    assert "ix_business_contexts_user_id_created_at_id" in indexes
    assert "ix_business_contexts_user_id_status_updated_at" in indexes
    check_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("business_contexts")
    }
    assert "ck_business_contexts_type" in check_names
    assert "ck_business_contexts_status" in check_names
    assert "ck_business_contexts_status_archived_at" in check_names
    fks = inspector.get_foreign_keys("business_contexts")
    assert any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        and str((fk.get("options") or {}).get("ondelete", "")).upper() == "CASCADE"
        for fk in fks
    )


def test_postgres_ownership_isolation(session_factory: sessionmaker) -> None:
    """Owned lookups never leak across users on PostgreSQL."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        created = repository.add(_context(user_a))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        assert repository.get_owned(created.id, user_a) is not None
        assert repository.get_owned(created.id, user_b) is None
        assert [item.id for item in repository.list_owned(user_a, 20, 0)] == [created.id]
        assert repository.list_owned(user_b, 20, 0) == []


def test_postgres_archive_restore_and_owner_role_non_bypass(
    session_factory: sessionmaker,
) -> None:
    """Archive/restore persist; Platform Owner role does not widen ownership."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        assert identities.promote_user_role_from_user_to_owner(user_b) is True
        repository = SqlAlchemyBusinessContextRepository(session)
        created = repository.add(_context(user_a))
        created.archive()
        archived = repository.save_owned(created)
        session.commit()
        assert archived is not None
        assert archived.status is BusinessContextStatus.ARCHIVED
        assert identities.get_application_role_for_user(user_b) == ApplicationRole.OWNER.value

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        assert repository.get_owned(created.id, user_b) is None
        loaded = repository.get_owned(created.id, user_a)
        assert loaded is not None
        loaded.restore()
        restored = repository.save_owned(loaded)
        session.commit()
        assert restored is not None
        assert restored.status is BusinessContextStatus.ACTIVE
        assert restored.archived_at is None
