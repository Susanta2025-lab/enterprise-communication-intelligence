"""PostgreSQL identity repository, constraint, cascade, and UUID tests."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
from app.infrastructure.storage.models import ExternalIdentity, User
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository

_ISSUER_A = "https://issuer-a.example.invalid/"
_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_X = "user-a-subject"
_SUBJECT_Y = "user-b-subject"


def test_create_and_lookup_returns_python_uuid(session_factory: sessionmaker) -> None:
    """PostgreSQL UUID columns must round-trip as uuid.UUID."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_X)
        session.commit()

    assert isinstance(user_id, UUID)

    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        found = repository.get_user_id_by_external_identity(_ISSUER_A, _SUBJECT_X)
        assert found == user_id
        assert isinstance(found, UUID)
        user = session.get(User, user_id)
        assert user is not None
        assert isinstance(user.id, UUID)
        identity = session.scalars(
            select(ExternalIdentity).where(ExternalIdentity.user_id == user_id)
        ).one()
        assert isinstance(identity.id, UUID)
        assert isinstance(identity.user_id, UUID)
        assert identity.created_at.tzinfo is not None


def test_duplicate_issuer_subject_named_constraint(session_factory: sessionmaker) -> None:
    """psycopg must report uq_external_identities_issuer_subject on duplicates."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_X)
        session.commit()

    with session_factory() as session:
        user = User(id=uuid4())
        identity = ExternalIdentity(
            id=uuid4(),
            user_id=user.id,
            issuer=_ISSUER_A,
            subject=_SUBJECT_X,
        )
        session.add(user)
        session.add(identity)
        with pytest.raises(IntegrityError) as exc_info:
            session.flush()

    orig = exc_info.value.orig
    assert orig is not None
    diag = getattr(orig, "diag", None)
    assert diag is not None
    assert diag.constraint_name == "uq_external_identities_issuer_subject"


def test_repository_translates_unique_violation_without_orphan(
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IntegrityError on the named constraint becomes PersistenceError and rolls back."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        first = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_X)
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        monkeypatch.setattr(repository, "get_user_id_by_external_identity", lambda *_args: None)
        with pytest.raises(PersistenceError) as exc_info:
            repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_X)
        assert exc_info.value.message == "External identity is already registered."

    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(User))
        identities = session.scalar(select(func.count()).select_from(ExternalIdentity))
        repository = SqlAlchemyIdentityRepository(session)
        assert count == 1
        assert identities == 1
        assert repository.get_user_id_by_external_identity(_ISSUER_A, _SUBJECT_X) == first


def test_same_subject_under_different_issuer_is_valid(session_factory: sessionmaker) -> None:
    """issuer A + subject X and issuer B + subject X are distinct mappings."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_a = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_X)
        user_b = repository.create_user_with_external_identity(_ISSUER_B, _SUBJECT_X)
        session.commit()

    assert user_a != user_b


def test_different_subject_under_same_issuer_is_valid(session_factory: sessionmaker) -> None:
    """issuer A + subject X and issuer A + subject Y are distinct mappings."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_a = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_X)
        user_b = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_Y)
        session.commit()

    assert user_a != user_b


def test_deleting_user_cascades_external_identity(session_factory: sessionmaker) -> None:
    """PostgreSQL ON DELETE CASCADE must remove identity rows."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_X)
        session.commit()

        session.execute(delete(User).where(User.id == user_id))
        session.commit()

        remaining = session.scalars(
            select(ExternalIdentity).where(ExternalIdentity.user_id == user_id)
        ).all()
        assert remaining == []
        assert repository.get_user_id_by_external_identity(_ISSUER_A, _SUBJECT_X) is None


def test_user_has_no_email_or_name_columns(session_factory: sessionmaker) -> None:
    """Persisted users must not carry email or display-name attributes."""
    with session_factory() as session:
        repository = SqlAlchemyIdentityRepository(session)
        user_id = repository.create_user_with_external_identity(_ISSUER_A, _SUBJECT_X)
        session.commit()
        user = session.get(User, user_id)
        assert user is not None
        assert not hasattr(user, "email")
        assert not hasattr(user, "name")
        assert not hasattr(user, "display_name")
