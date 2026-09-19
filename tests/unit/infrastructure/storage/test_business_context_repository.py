"""BusinessContext repository tests using isolated SQLite."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
from app.domain.enums import ApplicationRole, BusinessContextStatus, BusinessContextType
from app.domain.models.business_context import BusinessContext
from app.infrastructure.storage.models import BusinessContextRow, User
from app.infrastructure.storage.repositories.business_context import (
    SqlAlchemyBusinessContextRepository,
)
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

_ISSUER = "https://issuer.example.invalid/"
_TITLE = "Northwind renewal"


def _context(
    owner_user_id: UUID,
    *,
    title: str = _TITLE,
    context_type: BusinessContextType = BusinessContextType.MATTER,
    description: str | None = None,
    reference: str | None = None,
) -> BusinessContext:
    return BusinessContext(
        owner_user_id=owner_user_id,
        type=context_type,
        title=title,
        description=description,
        reference=reference,
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


def test_add_and_get_owned_round_trips(session_factory: sessionmaker) -> None:
    """Creating a context makes the same UUID retrievable for the owner."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        created = repository.add(
            _context(
                user_a,
                description="Diligence notes",
                reference="MAT-1",
                context_type=BusinessContextType.PROJECT,
            )
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        found = repository.get_owned(created.id, user_a)
        assert found is not None
        assert found.id == created.id
        assert found.owner_user_id == user_a
        assert found.type is BusinessContextType.PROJECT
        assert found.title == _TITLE
        assert found.description == "Diligence notes"
        assert found.reference == "MAT-1"
        assert found.status is BusinessContextStatus.ACTIVE
        assert found.archived_at is None
        assert _aware(found.created_at) == _aware(created.created_at)


def test_get_owned_requires_matching_user_id(session_factory: sessionmaker) -> None:
    """get_owned must not return another user's context."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        owned = repository.add(_context(user_a))
        session.commit()
        context_id = owned.id

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        assert repository.get_owned(context_id, user_a) is not None
        assert repository.get_owned(context_id, user_b) is None
        assert repository.get_owned(uuid4(), user_a) is None


def test_list_owned_excludes_other_users_and_defaults_to_active(
    session_factory: sessionmaker,
) -> None:
    """Each user sees only their active contexts by default, newest first."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        first = repository.add(_context(user_a, title="First"))
        session.commit()
        second = repository.add(_context(user_a, title="Second"))
        session.commit()
        other = repository.add(_context(user_b, title="Other"))
        session.commit()
        archived = repository.add(_context(user_a, title="Archived"))
        archived.archive()
        repository.save_owned(archived)
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        owned_a = repository.list_owned(user_a, limit=20, offset=0)
        owned_b = repository.list_owned(user_b, limit=20, offset=0)
        all_a = repository.list_owned(user_a, limit=20, offset=0, status=None)
        archived_only = repository.list_owned(
            user_a,
            limit=20,
            offset=0,
            status=BusinessContextStatus.ARCHIVED,
        )
        empty = repository.list_owned(user_a, limit=0, offset=0)

    assert [item.id for item in owned_a] == [second.id, first.id]
    assert [item.id for item in owned_b] == [other.id]
    assert {item.id for item in all_a} == {first.id, second.id, archived.id}
    assert [item.id for item in archived_only] == [archived.id]
    assert empty == []


def test_reference_is_not_unique(session_factory: sessionmaker) -> None:
    """Identical references may exist for the same or different users."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        first = repository.add(_context(user_a, reference="SHARED"))
        second = repository.add(_context(user_a, title="Second", reference="SHARED"))
        third = repository.add(_context(user_b, reference="SHARED"))
        session.commit()

    assert first.reference == second.reference == third.reference == "SHARED"
    assert first.id != second.id != third.id


def test_archive_and_restore_persist(session_factory: sessionmaker) -> None:
    """Archive and restore lifecycle fields survive round-trips."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        created = repository.add(_context(user_a))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        loaded = repository.get_owned(created.id, user_a)
        assert loaded is not None
        loaded.archive()
        saved = repository.save_owned(loaded)
        session.commit()
        assert saved is not None
        assert saved.status is BusinessContextStatus.ARCHIVED
        assert saved.archived_at is not None

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        archived = repository.get_owned(created.id, user_a)
        assert archived is not None
        archived.restore()
        restored = repository.save_owned(archived)
        session.commit()
        assert restored is not None
        assert restored.status is BusinessContextStatus.ACTIVE
        assert restored.archived_at is None


def test_save_owned_not_found_for_cross_user(session_factory: sessionmaker) -> None:
    """save_owned refuses writes when owner_user_id does not match the row."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        created = repository.add(_context(user_a))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        foreign = BusinessContext.rehydrate(
            id=created.id,
            owner_user_id=user_b,
            type=BusinessContextType.MATTER,
            title="Hijack attempt",
            status=BusinessContextStatus.ACTIVE,
            archived_at=None,
            created_at=created.created_at,
            updated_at=datetime.now(UTC),
        )
        assert repository.save_owned(foreign) is None
        original = repository.get_owned(created.id, user_a)
        assert original is not None
        assert original.title == _TITLE


def test_platform_owner_role_does_not_bypass_ownership(
    session_factory: sessionmaker,
) -> None:
    """application_role=owner does not widen get_owned or list_owned."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        assert identities.promote_user_role_from_user_to_owner(user_b) is True
        repository = SqlAlchemyBusinessContextRepository(session)
        owned = repository.add(_context(user_a))
        session.commit()
        role = identities.get_application_role_for_user(user_b)
        assert role == ApplicationRole.OWNER.value

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        assert repository.get_owned(owned.id, user_b) is None
        assert repository.list_owned(user_b, limit=20, offset=0) == []
        assert repository.get_owned(owned.id, user_a) is not None


def test_deleting_user_cascades_contexts(session_factory: sessionmaker) -> None:
    """User deletion removes owned contexts via ON DELETE CASCADE."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        created = repository.add(_context(user_a))
        session.commit()
        context_id = created.id

    with session_factory() as session:
        user = session.get(User, user_a)
        assert user is not None
        session.delete(user)
        session.commit()

    with session_factory() as session:
        remaining = session.get(BusinessContextRow, context_id)
        assert remaining is None


def test_check_constraints_reject_invalid_status_pairing(
    session_factory: sessionmaker,
) -> None:
    """Database rejects active+archived_at and archived without archived_at."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO business_contexts ("
                    "id, user_id, type, title, status, archived_at, created_at, updated_at"
                    ") VALUES ("
                    ":id, :user_id, 'matter', 'Bad active', 'active', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": str(uuid4()), "user_id": str(user_a)},
            )
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO business_contexts ("
                    "id, user_id, type, title, status, archived_at, created_at, updated_at"
                    ") VALUES ("
                    ":id, :user_id, 'matter', 'Bad archived', 'archived', NULL, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": str(uuid4()), "user_id": str(user_a)},
            )
            session.commit()


def test_schema_has_expected_indexes(sqlite_engine: Engine) -> None:
    """business_contexts indexes and checks exist on the ORM schema."""
    inspector = inspect(sqlite_engine)
    assert "business_contexts" in inspector.get_table_names()
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


def test_unit_of_work_exposes_business_contexts(session_factory: sessionmaker) -> None:
    """UoW binds the BusinessContext repository to the shared session."""
    user_a, _user_b = _create_users(session_factory)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        created = uow.business_contexts.add(_context(user_a))
        uow.commit()
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        found = uow.business_contexts.get_owned(created.id, user_a)
        assert found is not None
        assert found.id == created.id


def test_orphan_user_id_rejected(session_factory: sessionmaker) -> None:
    """FK integrity prevents contexts without a real users.id owner."""
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextRepository(session)
        with pytest.raises(PersistenceError):
            repository.add(_context(uuid4()))
