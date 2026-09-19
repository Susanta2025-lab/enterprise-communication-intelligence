"""Unit tests for BusinessContext application service."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    BusinessContextConflictError,
    BusinessContextNotFoundError,
)
from app.application.services.business_contexts import BusinessContextService
from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import (
    ApplicationRole,
    BusinessContextStatus,
    BusinessContextType,
)
from tests.support.in_memory_persistence import InMemoryUnitOfWork, UnitOfWorkFactory

_ISSUER = "https://issuer.example.invalid/"
_SUBJECT_A = "user-a"
_SUBJECT_B = "user-b"
_SUBJECT_OWNER = "platform-owner"


def _principal(subject: str = _SUBJECT_A) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=subject,
        permissions=frozenset({"communications:analyze"}),
    )


def _service(uow: InMemoryUnitOfWork) -> BusinessContextService:
    factory = UnitOfWorkFactory(uow)
    return BusinessContextService(IdentityResolver(factory), factory)


def _seed_users() -> tuple[UUID, UUID, UUID, InMemoryUnitOfWork]:
    user_a = uuid4()
    user_b = uuid4()
    owner = uuid4()
    uow = InMemoryUnitOfWork(
        identities={
            (_ISSUER, _SUBJECT_A): user_a,
            (_ISSUER, _SUBJECT_B): user_b,
            (_ISSUER, _SUBJECT_OWNER): owner,
        },
        application_roles={
            user_a: ApplicationRole.USER.value,
            user_b: ApplicationRole.USER.value,
            owner: ApplicationRole.OWNER.value,
        },
    )
    return user_a, user_b, owner, uow


def test_create_binds_ownership_from_principal() -> None:
    """Create resolves identity and stores server-authoritative ownership."""
    user_a, _user_b, _owner, uow = _seed_users()
    service = _service(uow)

    created = service.create(
        _principal(),
        type=BusinessContextType.MATTER,
        title="Acme Matter",
        description="Notes",
        reference="MAT-1",
    )

    assert created.owner_user_id == user_a
    assert created.status is BusinessContextStatus.ACTIVE
    assert created.archived_at is None
    assert created.id in uow.business_context_store


def test_create_without_prior_identity_uses_resolve_or_create() -> None:
    """Context create does not require mailbox connection or prior user rows."""
    uow = InMemoryUnitOfWork()
    service = _service(uow)

    created = service.create(
        _principal("new-user"),
        type=BusinessContextType.PROJECT,
        title="New Project",
    )

    assert created.owner_user_id is not None
    assert created.title == "New Project"
    assert uow.identity_repository.create_calls == 1


def test_list_defaults_to_active_and_isolates_users() -> None:
    """List returns only the caller's active contexts by default."""
    user_a, user_b, _owner, uow = _seed_users()
    service = _service(uow)
    a_active = service.create(_principal(), type=BusinessContextType.CASE, title="A")
    a_archived = service.create(
        _principal(), type=BusinessContextType.CASE, title="A-Archived"
    )
    service.archive(_principal(), a_archived.id)
    service.create(
        _principal(_SUBJECT_B),
        type=BusinessContextType.CASE,
        title="B",
    )

    listed = service.list(_principal())
    assert [item.id for item in listed] == [a_active.id]
    assert all(item.owner_user_id == user_a for item in listed)

    archived = service.list(
        _principal(),
        status=BusinessContextStatus.ARCHIVED,
    )
    assert [item.id for item in archived] == [a_archived.id]

    all_statuses = service.list(_principal(), status=None)
    assert {item.id for item in all_statuses} == {a_active.id, a_archived.id}
    assert service.list(_principal(_SUBJECT_B))[0].owner_user_id == user_b


def test_get_update_archive_restore_cross_user_are_not_found() -> None:
    """Cross-user context ids are indistinguishable from unknown ids."""
    _user_a, _user_b, owner, uow = _seed_users()
    service = _service(uow)
    created = service.create(
        _principal(),
        type=BusinessContextType.CLIENT,
        title="Owned",
    )

    with pytest.raises(BusinessContextNotFoundError):
        service.get(_principal(_SUBJECT_B), created.id)
    with pytest.raises(BusinessContextNotFoundError):
        service.update(_principal(_SUBJECT_B), created.id, title="Hijack")
    with pytest.raises(BusinessContextNotFoundError):
        service.archive(_principal(_SUBJECT_B), created.id)
    with pytest.raises(BusinessContextNotFoundError):
        service.restore(_principal(_SUBJECT_B), created.id)

    with pytest.raises(BusinessContextNotFoundError):
        service.get(_principal(_SUBJECT_OWNER), created.id)
    assert owner is not None


def test_update_rejects_archived_context() -> None:
    """Updates are forbidden while archived."""
    _user_a, _user_b, _owner, uow = _seed_users()
    service = _service(uow)
    created = service.create(
        _principal(),
        type=BusinessContextType.OTHER,
        title="Before",
    )
    service.archive(_principal(), created.id)

    with pytest.raises(BusinessContextConflictError):
        service.update(_principal(), created.id, title="After")


def test_archive_and_restore_are_idempotent() -> None:
    """Archive/restore retries leave the context in the target state."""
    _user_a, _user_b, _owner, uow = _seed_users()
    service = _service(uow)
    created = service.create(
        _principal(),
        type=BusinessContextType.TRANSACTION,
        title="Deal",
    )

    archived = service.archive(_principal(), created.id)
    assert archived.status is BusinessContextStatus.ARCHIVED
    assert archived.archived_at is not None
    again = service.archive(_principal(), created.id)
    assert again.status is BusinessContextStatus.ARCHIVED
    assert again.archived_at == archived.archived_at

    restored = service.restore(_principal(), created.id)
    assert restored.status is BusinessContextStatus.ACTIVE
    assert restored.archived_at is None
    again_active = service.restore(_principal(), created.id)
    assert again_active.status is BusinessContextStatus.ACTIVE


def test_list_type_and_reference_filters() -> None:
    """Optional type and reference filters use exact match."""
    _user_a, _user_b, _owner, uow = _seed_users()
    service = _service(uow)
    matter = service.create(
        _principal(),
        type=BusinessContextType.MATTER,
        title="Matter",
        reference="REF-1",
    )
    service.create(
        _principal(),
        type=BusinessContextType.PROJECT,
        title="Project",
        reference="REF-2",
    )

    by_type = service.list(_principal(), type=BusinessContextType.MATTER)
    assert [item.id for item in by_type] == [matter.id]
    by_ref = service.list(_principal(), reference="REF-1")
    assert [item.id for item in by_ref] == [matter.id]
