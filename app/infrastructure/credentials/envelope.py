"""Minimal versioned envelope for durable mailbox credential secrets.

The inner OAuth payload stays opaque bytes. This wrapper only adds a schema
version, a logical compare-and-set version, and the mailbox provider slug.
"""

from __future__ import annotations

import json
import secrets
from base64 import b64decode, b64encode
from typing import Final

from app.core.exceptions import (
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.infrastructure.credentials.validation import require_supported_provider

SCHEMA_VERSION: Final[int] = 1
_MAX_MATERIAL_BYTES: Final[int] = 24 * 1024
_MAX_ENVELOPE_CHARS: Final[int] = 48 * 1024


def new_logical_version() -> str:
    """Return a high-entropy opaque logical version string."""
    return secrets.token_hex(16)


def serialize_secret_envelope(
    *,
    provider: str,
    logical_version: str,
    secret_material: bytes,
) -> str:
    """Encode opaque credential bytes into a bounded JSON envelope string."""
    provider_slug = require_supported_provider(provider)
    if not isinstance(logical_version, str) or not logical_version:
        raise CommunicationCredentialUnavailableError()
    if not isinstance(secret_material, bytes) or not secret_material:
        raise CommunicationCredentialUnavailableError()
    if len(secret_material) > _MAX_MATERIAL_BYTES:
        raise CommunicationCredentialUnavailableError()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "logical_version": logical_version,
        "provider": provider_slug,
        "material": b64encode(secret_material).decode("ascii"),
    }
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    if len(serialized) > _MAX_ENVELOPE_CHARS:
        raise CommunicationCredentialUnavailableError()
    return serialized


def deserialize_secret_envelope(raw: object) -> tuple[str, str, bytes]:
    """Parse an envelope into ``(provider, logical_version, secret_material)``.

    Malformed material raises a generic unavailability error and never echoes
    the stored value.
    """
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_ENVELOPE_CHARS:
        raise CommunicationCredentialUnavailableError()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        raise CommunicationCredentialUnavailableError() from None
    if not isinstance(payload, dict):
        raise CommunicationCredentialUnavailableError()
    schema = payload.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise CommunicationCredentialUnavailableError()
    logical_version = payload.get("logical_version")
    if not isinstance(logical_version, str) or not logical_version:
        raise CommunicationCredentialUnavailableError()
    try:
        provider = require_supported_provider(payload.get("provider"))
    except UnsupportedCommunicationCredentialProviderError:
        raise CommunicationCredentialUnavailableError() from None
    material_field = payload.get("material")
    if not isinstance(material_field, str) or not material_field:
        raise CommunicationCredentialUnavailableError()
    try:
        secret_material = b64decode(material_field, validate=True)
    except (TypeError, ValueError):
        raise CommunicationCredentialUnavailableError() from None
    if not secret_material or len(secret_material) > _MAX_MATERIAL_BYTES:
        raise CommunicationCredentialUnavailableError()
    return provider, logical_version, secret_material
