"""Unit tests for controlled first-owner bootstrap."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.exceptions import (
    OwnerAlreadyExistsError,
    OwnerBootstrapConflictError,
    OwnerBootstrapExternalIdentityRequiredError,
    OwnerBootstrapTargetNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.application.services.owner_bootstrap import (
    FirstOwnerBootstrapResult,
    FirstOwnerBootstrapService,
)
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import ApplicationRole
from tests.support.in_memory_persistence import InMemoryUnitOfWork, UnitOfWorkFactory
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION

_SUBJECT_A = "bootstrap-subject-a"
_SUBJECT_B = "bootstrap-subject-b"


def _principal(subject: str = _SUBJECT_A) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _seed_user(unit: InMemoryUnitOfWork, *, subject: str = _SUBJECT_A):
    return IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(_principal(subject))


def test_promote_existing_user_to_owner() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))

    result = service.promote_first_owner(user_id)

    assert result is FirstOwnerBootstrapResult.PROMOTED
    assert unit.application_roles[user_id] == ApplicationRole.OWNER.value
    assert unit.commit_calls >= 1


def test_promoted_role_persists_and_is_idempotent() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))
    assert service.promote_first_owner(user_id) is FirstOwnerBootstrapResult.PROMOTED
    assert service.promote_first_owner(user_id) is FirstOwnerBootstrapResult.ALREADY_OWNER
    assert unit.application_roles[user_id] == ApplicationRole.OWNER.value


def test_nonexistent_user_fails_closed() -> None:
    unit = InMemoryUnitOfWork()
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))
    with pytest.raises(OwnerBootstrapTargetNotFoundError):
        service.promote_first_owner(uuid4())
    assert unit.application_roles == {}
    assert unit.commit_calls == 0


def test_bootstrap_never_creates_a_user() -> None:
    unit = InMemoryUnitOfWork()
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))
    with pytest.raises(OwnerBootstrapTargetNotFoundError):
        service.promote_first_owner(uuid4())
    assert unit.identity_repository.create_calls == 0
    assert unit.identities == {}


def test_resolve_or_create_still_creates_only_user() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    assert unit.application_roles[user_id] == ApplicationRole.USER.value
    assert unit.identity_repository.promote_calls == 0


def test_user_without_external_identity_fails_closed() -> None:
    unit = InMemoryUnitOfWork()
    orphan = uuid4()
    unit.application_roles[orphan] = ApplicationRole.USER.value
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))
    with pytest.raises(OwnerBootstrapExternalIdentityRequiredError):
        service.promote_first_owner(orphan)
    assert unit.application_roles[orphan] == ApplicationRole.USER.value


def test_email_like_subject_is_not_a_bootstrap_selector() -> None:
    """Bootstrap accepts only users.id; email-shaped subjects are not selectors."""
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit, subject="owner@example.invalid")
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))
    with pytest.raises(OwnerBootstrapTargetNotFoundError):
        service.promote_first_owner(uuid4())
    assert unit.application_roles[user_id] == ApplicationRole.USER.value


def test_second_owner_bootstrap_rejected() -> None:
    unit = InMemoryUnitOfWork()
    first = _seed_user(unit, subject=_SUBJECT_A)
    second = _seed_user(unit, subject=_SUBJECT_B)
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))
    service.promote_first_owner(first)
    with pytest.raises(OwnerAlreadyExistsError):
        service.promote_first_owner(second)
    assert unit.application_roles[first] == ApplicationRole.OWNER.value
    assert unit.application_roles[second] == ApplicationRole.USER.value


def test_commit_failure_raises_unavailable() -> None:
    store = InMemoryUnitOfWork()
    user_id = _seed_user(store)
    failing = InMemoryUnitOfWork(
        identities=dict(store.identities),
        application_roles=dict(store.application_roles),
        fail_commit=True,
    )
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(failing))
    with pytest.raises(ServiceUnavailableError):
        service.promote_first_owner(user_id)
    assert failing.rollback_calls >= 1


def test_persistence_failure_before_mutation_leaves_state_unchanged() -> None:
    unit = InMemoryUnitOfWork(fail_on_enter=PersistenceError("unavailable"))
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))
    with pytest.raises(ServiceUnavailableError):
        service.promote_first_owner(uuid4())
    assert unit.application_roles == {}


def test_corrupt_role_fails_closed() -> None:
    unit = InMemoryUnitOfWork()
    user_id = _seed_user(unit)
    unit.application_roles[user_id] = "admin"
    service = FirstOwnerBootstrapService(UnitOfWorkFactory(unit))
    with pytest.raises(OwnerBootstrapConflictError):
        service.promote_first_owner(user_id)
    assert unit.application_roles[user_id] == "admin"


def test_identity_resolver_has_no_promotion_path() -> None:
    assert not hasattr(IdentityResolver, "promote_first_owner")
    assert not hasattr(IdentityResolver, "promote_user_role_from_user_to_owner")
