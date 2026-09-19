"""Unit tests for the BusinessContext domain aggregate and lifecycle."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import BusinessContextStatus, BusinessContextType
from app.domain.exceptions import BusinessContextNotMutableError
from app.domain.models.business_context import (
    DESCRIPTION_MAX_LENGTH,
    REFERENCE_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    BusinessContext,
)

_TITLE = "Acme acquisition diligence"


def _active(**overrides: object) -> BusinessContext:
    payload: dict[str, object] = {
        "owner_user_id": uuid4(),
        "type": BusinessContextType.MATTER,
        "title": _TITLE,
    }
    payload.update(overrides)
    return BusinessContext.model_validate(payload)


def _rehydrate(**overrides: object) -> BusinessContext:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": uuid4(),
        "owner_user_id": uuid4(),
        "type": BusinessContextType.PROJECT,
        "title": _TITLE,
        "description": None,
        "reference": None,
        "status": BusinessContextStatus.ACTIVE,
        "archived_at": None,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return BusinessContext.rehydrate(**payload)


def test_valid_creation_defaults_to_active_with_uuid() -> None:
    """A well-formed context starts active with application-generated UUID."""
    owner = uuid4()
    context = BusinessContext(
        owner_user_id=owner,
        type=BusinessContextType.CASE,
        title=_TITLE,
    )
    assert isinstance(context.id, UUID)
    assert context.owner_user_id == owner
    assert context.type is BusinessContextType.CASE
    assert context.title == _TITLE
    assert context.description is None
    assert context.reference is None
    assert context.status is BusinessContextStatus.ACTIVE
    assert context.archived_at is None
    assert context.created_at.tzinfo is not None
    assert context.updated_at.tzinfo is not None


@pytest.mark.parametrize("context_type", list(BusinessContextType))
def test_all_locked_types_are_accepted(context_type: BusinessContextType) -> None:
    """Every ADR-029 type value constructs successfully."""
    context = _active(type=context_type)
    assert context.type is context_type


def test_invalid_type_is_rejected() -> None:
    """Free-form type strings are rejected."""
    with pytest.raises(ValidationError):
        BusinessContext(
            owner_user_id=uuid4(),
            type="lawsuit",  # type: ignore[arg-type]
            title=_TITLE,
        )


def test_title_is_trimmed_and_required() -> None:
    """Title rejects blank/whitespace and trims surrounding whitespace."""
    context = _active(title=f"  {_TITLE}  ")
    assert context.title == _TITLE
    with pytest.raises(ValidationError):
        _active(title="")
    with pytest.raises(ValidationError):
        _active(title="   ")


def test_title_max_boundary_and_over_limit() -> None:
    """Title accepts exactly 200 characters and rejects 201."""
    exact = "a" * TITLE_MAX_LENGTH
    assert _active(title=exact).title == exact
    with pytest.raises(ValidationError):
        _active(title="a" * (TITLE_MAX_LENGTH + 1))


def test_optional_description_and_reference_limits() -> None:
    """Optional fields trim, clear blanks, and enforce ADR length bounds."""
    context = _active(
        description=f"  Notes for {_TITLE}  ",
        reference="  MAT-2026-013  ",
    )
    assert context.description == f"Notes for {_TITLE}"
    assert context.reference == "MAT-2026-013"
    assert _active(description="   ").description is None
    assert _active(reference="").reference is None
    assert _active(description="d" * DESCRIPTION_MAX_LENGTH).description is not None
    assert _active(reference="r" * REFERENCE_MAX_LENGTH).reference is not None
    with pytest.raises(ValidationError):
        _active(description="d" * (DESCRIPTION_MAX_LENGTH + 1))
    with pytest.raises(ValidationError):
        _active(reference="r" * (REFERENCE_MAX_LENGTH + 1))


def test_public_construction_rejects_non_active_status() -> None:
    """New contexts cannot be constructed as archived."""
    with pytest.raises(ValidationError):
        BusinessContext(
            owner_user_id=uuid4(),
            type=BusinessContextType.MATTER,
            title=_TITLE,
            status=BusinessContextStatus.ARCHIVED,
            archived_at=datetime.now(UTC),
        )


def test_rehydrate_rejects_inconsistent_archived_at() -> None:
    """Status and archived_at must stay paired."""
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        _rehydrate(status=BusinessContextStatus.ACTIVE, archived_at=now)
    with pytest.raises(ValidationError):
        _rehydrate(status=BusinessContextStatus.ARCHIVED, archived_at=None)


def test_archive_sets_timestamp_and_is_idempotent() -> None:
    """Archive moves active→archived and is a no-op when already archived."""
    context = _active()
    before = context.updated_at
    context.archive()
    assert context.status is BusinessContextStatus.ARCHIVED
    assert context.archived_at is not None
    assert context.archived_at.tzinfo is not None
    assert context.updated_at >= before
    first_archived_at = context.archived_at
    context.archive()
    assert context.status is BusinessContextStatus.ARCHIVED
    assert context.archived_at == first_archived_at


def test_restore_clears_archived_at_and_is_idempotent() -> None:
    """Restore moves archived→active and clears archived_at."""
    context = _active()
    context.archive()
    context.restore()
    assert context.status is BusinessContextStatus.ACTIVE
    assert context.archived_at is None
    context.restore()
    assert context.status is BusinessContextStatus.ACTIVE
    assert context.archived_at is None


def test_apply_update_only_when_active() -> None:
    """Editable fields mutate only while active."""
    context = _active()
    context.apply_update(
        type=BusinessContextType.CLIENT,
        title="Renamed matter",
        description="Updated notes",
        reference="REF-1",
    )
    assert context.type is BusinessContextType.CLIENT
    assert context.title == "Renamed matter"
    assert context.description == "Updated notes"
    assert context.reference == "REF-1"
    context.apply_update(description=None, reference=None)
    assert context.description is None
    assert context.reference is None
    context.archive()
    with pytest.raises(BusinessContextNotMutableError):
        context.apply_update(title="Should fail")


def test_reference_is_not_required_to_be_unique_in_domain() -> None:
    """Domain allows identical reference values across contexts."""
    first = _active(reference="SHARED-REF")
    second = _active(reference="SHARED-REF")
    assert first.reference == second.reference == "SHARED-REF"
    assert first.id != second.id
