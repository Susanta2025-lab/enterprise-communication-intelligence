"""Shared locator and mailbox-provider checks for credential infrastructure."""

from __future__ import annotations

import re

from app.core.exceptions import (
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)

CREDENTIAL_REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,62}$")
PROVIDER_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
SUPPORTED_PROVIDERS = frozenset({"gmail", "microsoft_graph"})


def require_credential_ref(credential_ref: object) -> str:
    """Return a well-formed locator or raise generic unavailability."""
    if not isinstance(credential_ref, str):
        raise CommunicationCredentialUnavailableError()
    if CREDENTIAL_REF_PATTERN.fullmatch(credential_ref) is None:
        raise CommunicationCredentialUnavailableError()
    return credential_ref


def is_valid_credential_ref(credential_ref: object) -> bool:
    """Return True when ``credential_ref`` matches the existing locator charset."""
    return (
        isinstance(credential_ref, str)
        and CREDENTIAL_REF_PATTERN.fullmatch(credential_ref) is not None
    )


def require_supported_provider(provider: object) -> str:
    """Return a canonical mailbox provider slug or raise unsupported."""
    if not isinstance(provider, str):
        raise UnsupportedCommunicationCredentialProviderError()
    slug = provider.strip().lower()
    if not slug or PROVIDER_SLUG.fullmatch(slug) is None:
        raise UnsupportedCommunicationCredentialProviderError()
    if slug not in SUPPORTED_PROVIDERS:
        raise UnsupportedCommunicationCredentialProviderError()
    return slug


def require_secret_material(secret_material: object) -> bytes:
    """Return non-empty opaque bytes or raise generic unavailability."""
    if not isinstance(secret_material, bytes) or not secret_material:
        raise CommunicationCredentialUnavailableError()
    return secret_material
