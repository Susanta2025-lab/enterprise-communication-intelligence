"""Identity repository tests using isolated SQLite."""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
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
