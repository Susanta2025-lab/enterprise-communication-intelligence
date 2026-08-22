"""Unit tests for server-generated credential locators."""

from __future__ import annotations

import inspect
import re

import pytest

from app.core.exceptions import CommunicationCredentialUnavailableError
from app.domain.interfaces.communication_credential_store import NewCommunicationCredential
from app.infrastructure.credentials.locators import (
    create_communication_credential,
    generate_credential_locator,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.validation import CREDENTIAL_REF_PATTERN

_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,62}$")
_SECRET = b"opaque-locator-secret-AAA"


def test_generated_locator_matches_existing_credential_ref_charset() -> None:
    locator = generate_credential_locator()
    assert _PATTERN.fullmatch(locator) is not None
    assert CREDENTIAL_REF_PATTERN.fullmatch(locator) is not None
    assert locator.startswith("oauth-")
    assert locator[0].isalpha()
    assert len(locator) <= 63
    assert "_" not in locator


def test_generated_locators_are_high_entropy() -> None:
    locators = {generate_credential_locator() for _ in range(64)}
    assert len(locators) == 64


def test_injected_generator_is_used() -> None:
    store = InMemoryCommunicationCredentialStore()
    record = create_communication_credential(
        store,
        provider="gmail",
        secret_material=_SECRET,
        generate_locator=lambda: "oauth-deterministic-locator",
    )
    assert record.credential_ref == "oauth-deterministic-locator"
    found = store.get("oauth-deterministic-locator")
    assert found is not None
    assert found.secret_material == _SECRET


def test_collision_retries_with_a_new_locator() -> None:
    store = InMemoryCommunicationCredentialStore()
    store.create(NewCommunicationCredential("oauth-taken-locator-0001", "gmail", _SECRET))
    locators = iter(
        (
            "oauth-taken-locator-0001",
            "oauth-retry-locator-00002",
        )
    )
    record = create_communication_credential(
        store,
        provider="gmail",
        secret_material=b"second-secret-material",
        generate_locator=lambda: next(locators),
    )
    assert record.credential_ref == "oauth-retry-locator-00002"
    original = store.get("oauth-taken-locator-0001")
    assert original is not None
    assert original.secret_material == _SECRET
    created = store.get("oauth-retry-locator-00002")
    assert created is not None
    assert created.secret_material == b"second-secret-material"


def test_bounded_collision_exhaustion_does_not_overwrite() -> None:
    store = InMemoryCommunicationCredentialStore()
    store.create(NewCommunicationCredential("oauth-always-taken-00001", "gmail", _SECRET))
    with pytest.raises(CommunicationCredentialUnavailableError):
        create_communication_credential(
            store,
            provider="gmail",
            secret_material=b"must-not-be-written",
            generate_locator=lambda: "oauth-always-taken-00001",
            max_attempts=3,
        )
    found = store.get("oauth-always-taken-00001")
    assert found is not None
    assert found.secret_material == _SECRET


def test_invalid_generated_locator_is_rejected() -> None:
    store = InMemoryCommunicationCredentialStore()
    with pytest.raises(CommunicationCredentialUnavailableError):
        create_communication_credential(
            store,
            provider="gmail",
            secret_material=_SECRET,
            generate_locator=lambda: "1-not-valid",
        )


def test_client_supplied_locator_is_not_part_of_issuance_api() -> None:
    parameters = inspect.signature(create_communication_credential).parameters
    assert "credential_ref" not in parameters
