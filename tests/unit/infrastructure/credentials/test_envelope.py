"""Envelope serialization tests for durable credential stores."""

from __future__ import annotations

import pytest

from app.core.exceptions import CommunicationCredentialUnavailableError
from app.infrastructure.credentials.envelope import (
    deserialize_secret_envelope,
    new_logical_version,
    serialize_secret_envelope,
)

_MATERIAL = b'{"refresh":"opaque-refresh-material"}'


def test_round_trip_preserves_provider_version_and_material() -> None:
    version = new_logical_version()
    raw = serialize_secret_envelope(
        provider="gmail",
        logical_version=version,
        secret_material=_MATERIAL,
    )
    provider, logical_version, material = deserialize_secret_envelope(raw)
    assert provider == "gmail"
    assert logical_version == version
    assert material == _MATERIAL
    assert "opaque-refresh-material" not in raw


def test_malformed_envelope_is_unavailable_without_echo() -> None:
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        deserialize_secret_envelope('{"not":"an-eci-envelope","secret":"LEAK"}')
    blob = f"{exc_info.value}{exc_info.value!r}{exc_info.value.message}"
    assert "LEAK" not in blob
    assert "an-eci-envelope" not in blob


def test_empty_or_non_string_envelope_is_unavailable() -> None:
    with pytest.raises(CommunicationCredentialUnavailableError):
        deserialize_secret_envelope("")
    with pytest.raises(CommunicationCredentialUnavailableError):
        deserialize_secret_envelope(None)
    with pytest.raises(CommunicationCredentialUnavailableError):
        deserialize_secret_envelope(b"not-json")
