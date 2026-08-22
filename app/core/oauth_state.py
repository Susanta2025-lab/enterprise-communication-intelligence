"""Cryptographically secure OAuth state generation and hashing.

Raw state is returned only to the immediate caller. Persist SHA-256(hex) only.
Never log raw state or include it in exceptions.
"""

from __future__ import annotations

import hashlib
import secrets

_STATE_RANDOM_BYTES = 32
_HEX_DIGEST_LENGTH = 64


def generate_oauth_state() -> str:
    """Return a high-entropy OAuth state with at least 256 bits of randomness."""
    return secrets.token_urlsafe(_STATE_RANDOM_BYTES)


def hash_oauth_state(state: str) -> str:
    """Return SHA-256(hex) of raw OAuth state for persistence and lookup."""
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def is_oauth_state_hash(value: str) -> bool:
    """Return True when ``value`` looks like a SHA-256 hex digest."""
    if len(value) != _HEX_DIGEST_LENGTH:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
