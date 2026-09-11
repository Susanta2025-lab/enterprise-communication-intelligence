"""Identity repository tests using isolated SQLite."""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
from app.domain.enums import ApplicationRole
from app.infrastructure.storage.models import ExternalIdentity, User
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository

_ISSUER_A = "https://issuer-a.example.invalid/"
_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_A = "user-a-subject"
_SUBJECT_B = "user-b-subject"


def test_create_and_lookup_returns_same_user_id(session_factory: sessionmaker) -> None:
    """Creating a mapping should make the same UUID retrievable."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        session.commit()

    assert isinstance(user_id, UUID)

    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        found = repository.get_user_id_by_external_identity(_ISSUER_A, _SUBJECT_A)
        assert found == user_id


def test_duplicate_issuer_subject_cannot_create_second_mapping(
    session_factory: sessionmaker,
) -> None:
    """The same issuer + subject must not create a second user."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        first = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        with pytest.raises(PersistenceError):
            repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        session.rollback()
        assert repository.get_user_id_by_external_identity(_ISSUER_A, _SUBJECT_A) == first


def test_same_subject_under_different_issuer_is_valid(
    session_factory: sessionmaker,
) -> None:
    """Subject uniqueness is per issuer, not global."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_a = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        user_b = repository.create_user_with_external_identity(_ISSUER_B, _SUBJECT_A)
        session.commit()

    assert user_a != user_b


def test_different_subject_under_same_issuer_is_valid(
    session_factory: sessionmaker,
) -> None:
    """One issuer may map multiple subjects to different users."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_a = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        user_b = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_B)
        session.commit()

    assert user_a != user_b


def test_create_persists_application_role_user(
    session_factory: sessionmaker,
) -> None:
    """Normal identity create must always persist application_role=user."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        session.commit()
        user = session.get(User, user_id)
        assert user is not None
        assert user.application_role == ApplicationRole.USER.value
        assert user.application_role != ApplicationRole.OWNER.value
        assert repository.get_application_role_for_user(user_id) == ApplicationRole.USER.value


def test_get_application_role_for_unknown_user_returns_none(
    session_factory: sessionmaker,
) -> None:
    """Role lookup must be scoped to an existing ECI user id."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        assert repository.get_application_role_for_user(
            UUID("00000000-0000-4000-8000-000000000001")
        ) is None


def test_create_ignores_email_like_subject_for_role(
    session_factory: sessionmaker,
) -> None:
    """Email-shaped subjects must not influence application_role."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(
            _ISSUER_A,
            "owner@example.invalid",
        )
        session.commit()
        user = session.get(User, user_id)
        assert user is not None
        assert user.application_role == ApplicationRole.USER.value


def test_database_rejects_unsupported_application_role(
    session_factory: sessionmaker,
) -> None:
    """Check constraint must reject values outside user|owner."""
    with session_factory() as session:
        session.add(
            User(
                id=UUID("00000000-0000-4000-8000-000000000099"),
                application_role="admin",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_resolve_create_path_has_no_generic_role_write_api() -> None:
    """Request-path identity APIs must not expose unrestricted role writes."""
    assert not hasattr(SqlAlchemyIdentityRepository, "set_application_role")
    assert not hasattr(SqlAlchemyIdentityRepository, "create_owner")
    assert hasattr(SqlAlchemyIdentityRepository, "promote_user_role_from_user_to_owner")


def test_promote_user_role_from_user_to_owner(session_factory: sessionmaker) -> None:
    """Conditional promote updates only user→owner for the target row."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        session.commit()
        assert repository.promote_user_role_from_user_to_owner(user_id) is True
        session.commit()
        assert repository.get_application_role_for_user(user_id) == ApplicationRole.OWNER.value
        assert repository.promote_user_role_from_user_to_owner(user_id) is False
        assert repository.count_users_with_application_role(ApplicationRole.OWNER.value) == 1
        assert repository.user_has_external_identity(user_id) is True


def test_promote_unknown_user_returns_false(session_factory: sessionmaker) -> None:
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        assert (
            repository.promote_user_role_from_user_to_owner(
                UUID("00000000-0000-4000-8000-000000000001")
            )
            is False
        )


def test_sqlalchemy_first_owner_bootstrap_persists_owner(
    session_factory: sessionmaker,
) -> None:
    """End-to-end bootstrap through SqlAlchemy UoW persists owner."""
    from app.application.services.owner_bootstrap import (
        FirstOwnerBootstrapResult,
        FirstOwnerBootstrapService,
    )
    from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

    def _factory() -> SqlAlchemyPersistenceUnitOfWork:
        return SqlAlchemyPersistenceUnitOfWork(session_factory)

    with _factory() as uow:
        user_id = uow.identity_repository.create_user_with_external_identity(
            _ISSUER_A,
            _SUBJECT_A,
        )
        uow.commit()

    result = FirstOwnerBootstrapService(_factory).promote_first_owner(user_id)
    assert result is FirstOwnerBootstrapResult.PROMOTED

    with _factory() as uow:
        assert (
            uow.identity_repository.get_application_role_for_user(user_id)
            == ApplicationRole.OWNER.value
        )

    assert (
        FirstOwnerBootstrapService(_factory).promote_first_owner(user_id)
        is FirstOwnerBootstrapResult.ALREADY_OWNER
    )


def test_user_has_no_email_or_name_columns(session_factory: sessionmaker) -> None:
    """Persisted users must not carry email or display-name attributes."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        session.commit()
        user = session.get(User, user_id)
        assert user is not None
        assert not hasattr(user, "email")
        assert not hasattr(user, "name")
        assert not hasattr(user, "display_name")


def test_unknown_identity_returns_none(session_factory: sessionmaker) -> None:
    """Lookup of an unregistered pair should return None."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        assert repository.get_user_id_by_external_identity(_ISSUER_A, _SUBJECT_A) is None


def test_deleting_user_cascades_external_identity(session_factory: sessionmaker) -> None:
    """SQLite FK enforcement should remove identity rows when the user is deleted."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_A)
        session.commit()

        user = session.get(User, user_id)
        assert user is not None
        session.delete(user)
        session.commit()

        remaining = session.scalars(
            select(ExternalIdentity).where(ExternalIdentity.user_id == user_id)
        ).all()
        assert remaining == []
        assert repository.get_user_id_by_external_identity(_ISSUER_A, _SUBJECT_A) is None
