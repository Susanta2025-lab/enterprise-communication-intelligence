"""Unit tests for IdentityResolver."""

from uuid import UUID, uuid4

import pytest

from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.security import AuthenticatedPrincipal
from tests.support.in_memory_persistence import InMemoryUnitOfWork, UnitOfWorkFactory
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION, TEST_SUBJECT

_ISSUER_A = "https://issuer-a.example.invalid/"
_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_A = "subject-a"
_SUBJECT_B = "subject-b"


def _principal(
    *,
    issuer: str = _ISSUER_A,
    subject: str = _SUBJECT_A,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=issuer,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )


def test_existing_identity_returns_same_user_and_does_not_create() -> None:
    """A known issuer+subject must return the stored user without inserting."""
    user_id = uuid4()
    unit = InMemoryUnitOfWork(identities={(_ISSUER_A, _SUBJECT_A): user_id})
    resolver = IdentityResolver(UnitOfWorkFactory(unit))

    found = resolver.resolve_or_create(_principal())

    assert found == user_id
    assert unit.identity_repository.create_calls == 0
    assert unit.commit_calls == 0


def test_missing_identity_creates_user_and_commits() -> None:
    """First use must create an internal user and commit the mapping."""
    unit = InMemoryUnitOfWork()
    resolver = IdentityResolver(UnitOfWorkFactory(unit))

    user_id = resolver.resolve_or_create(_principal())

    assert isinstance(user_id, UUID)
    assert unit.identity_repository.create_calls == 1
    assert unit.commit_calls == 1
    assert unit.identities[(_ISSUER_A, _SUBJECT_A)] == user_id


def test_find_existing_missing_returns_none_without_create() -> None:
    """History lookups must not create a user."""
    unit = InMemoryUnitOfWork()
    resolver = IdentityResolver(UnitOfWorkFactory(unit))

    found = resolver.find_existing(_principal())

    assert found is None
    assert unit.identity_repository.create_calls == 0
    assert unit.commit_calls == 0


def test_same_principal_repeatedly_returns_same_user() -> None:
    """Repeated resolve_or_create calls must reuse the committed mapping."""
    store: dict[tuple[str, str], UUID] = {}
    first = InMemoryUnitOfWork(identities=store)
    second = InMemoryUnitOfWork(identities=store)
    resolver = IdentityResolver(UnitOfWorkFactory(first, second))

    first_id = resolver.resolve_or_create(_principal())
    second_id = resolver.resolve_or_create(_principal())

    assert first_id == second_id
    assert first.identity_repository.create_calls == 1
    assert second.identity_repository.create_calls == 0


def test_different_issuer_same_subject_creates_distinct_users() -> None:
    """Ownership keys include issuer; subject alone is not unique."""
    store: dict[tuple[str, str], UUID] = {}
    resolver = IdentityResolver(
        UnitOfWorkFactory(
            InMemoryUnitOfWork(identities=store),
            InMemoryUnitOfWork(identities=store),
        )
    )

    user_a = resolver.resolve_or_create(_principal(issuer=_ISSUER_A, subject=_SUBJECT_A))
    user_b = resolver.resolve_or_create(_principal(issuer=_ISSUER_B, subject=_SUBJECT_A))

    assert user_a != user_b


def test_same_issuer_different_subject_creates_distinct_users() -> None:
    """One issuer may map multiple subjects to different users."""
    store: dict[tuple[str, str], UUID] = {}
    resolver = IdentityResolver(
        UnitOfWorkFactory(
            InMemoryUnitOfWork(identities=store),
            InMemoryUnitOfWork(identities=store),
        )
    )

    user_a = resolver.resolve_or_create(_principal(issuer=_ISSUER_A, subject=_SUBJECT_A))
    user_b = resolver.resolve_or_create(_principal(issuer=_ISSUER_A, subject=_SUBJECT_B))

    assert user_a != user_b


def test_concurrent_duplicate_rereads_the_winner() -> None:
    """A unique-violation race must resolve the committed winner, not a second user."""
    winner = uuid4()

    class _ConflictThenLookup:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self) -> InMemoryUnitOfWork:
            self.calls += 1
            if self.calls == 1:

                class _ConflictRepo:
                    def get_user_id_by_external_identity(
                        self, issuer: str, subject: str
                    ) -> UUID | None:
                        return None

                    def create_user_with_external_identity(
                        self, issuer: str, subject: str
                    ) -> UUID:
                        raise PersistenceError("External identity is already registered.")

                unit = InMemoryUnitOfWork()
                unit._identity_repository = _ConflictRepo()  # type: ignore[assignment]
                return unit
            return InMemoryUnitOfWork(identities={(_ISSUER_A, _SUBJECT_A): winner})

    resolver = IdentityResolver(_ConflictThenLookup())
    found = resolver.resolve_or_create(_principal())
    assert found == winner


def test_persistence_failure_is_unavailable_without_identity_details() -> None:
    """Public errors must not include issuer or subject."""
    unit = InMemoryUnitOfWork(fail_on_enter=PersistenceError("Could not persist identity."))
    resolver = IdentityResolver(UnitOfWorkFactory(unit))
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        resolver.resolve_or_create(principal)

    assert exc_info.value.message == "Persistence is currently unavailable."
    assert TEST_ISSUER not in exc_info.value.message
    assert TEST_SUBJECT not in exc_info.value.message
    assert principal.issuer not in str(exc_info.value)
    assert principal.subject not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
