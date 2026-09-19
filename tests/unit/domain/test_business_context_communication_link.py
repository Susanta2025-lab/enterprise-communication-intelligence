"""Domain tests for BusinessContextCommunicationLink."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import AssociationSource
from app.domain.models.business_context_communication_link import (
    BusinessContextCommunicationLink,
)


def _link(**overrides: object) -> BusinessContextCommunicationLink:
    owner = uuid4()
    values: dict[str, object] = {
        "business_context_id": uuid4(),
        "owner_user_id": owner,
        "connector_account_id": uuid4(),
        "provider_message_id": "provider-msg-001",
        "associated_by_user_id": owner,
    }
    values.update(overrides)
    return BusinessContextCommunicationLink(**values)  # type: ignore[arg-type]


def test_manual_link_requires_non_empty_provider_message_id() -> None:
    """Opaque provider message ids must be non-empty after trim."""
    owner = uuid4()
    link = _link(owner_user_id=owner, associated_by_user_id=owner)
    assert link.association_source is AssociationSource.MANUAL
    assert link.analysis_id is None
    assert link.provider_message_id == "provider-msg-001"

    with pytest.raises(ValidationError):
        _link(provider_message_id="   ")
    with pytest.raises(ValidationError):
        _link(provider_message_id="")


def test_associated_by_must_equal_owner() -> None:
    """Phase 20 manual self-associate requires matching owner and actor."""
    with pytest.raises(ValidationError):
        _link(associated_by_user_id=uuid4())


def test_rehydrate_preserves_manual_source_and_optional_analysis() -> None:
    """Persisted links rehydrate with optional analysis provenance."""
    owner = uuid4()
    analysis_id = uuid4()
    link = BusinessContextCommunicationLink.rehydrate(
        id=uuid4(),
        business_context_id=uuid4(),
        owner_user_id=owner,
        connector_account_id=uuid4(),
        provider_message_id="msg-abc",
        associated_by_user_id=owner,
        association_source=AssociationSource.MANUAL,
        analysis_id=analysis_id,
    )
    assert link.analysis_id == analysis_id
    assert link.association_source is AssociationSource.MANUAL


def test_link_does_not_store_message_content_fields() -> None:
    """Provenance links reject message-content style fields."""
    with pytest.raises(ValidationError):
        BusinessContextCommunicationLink(
            business_context_id=uuid4(),
            owner_user_id=uuid4(),
            connector_account_id=uuid4(),
            provider_message_id="msg-1",
            associated_by_user_id=uuid4(),
            subject="Secret matter",  # type: ignore[call-arg]
        )
