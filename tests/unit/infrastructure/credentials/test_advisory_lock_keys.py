"""Deterministic advisory-lock key derivation tests. No database access."""

from __future__ import annotations

import ast
import struct
from hashlib import sha256
from pathlib import Path

from app.infrastructure.credentials.locators import generate_credential_locator
from app.infrastructure.credentials.mutation import advisory_lock_keys

_MODULE = Path("app/infrastructure/credentials/mutation.py")
_NAMESPACE = "eci:mailbox-credential-mutation:"


def _expected_keys(credential_ref: str) -> tuple[int, int]:
    digest = sha256(f"{_NAMESPACE}{credential_ref}".encode()).digest()
    return struct.unpack(">ii", digest[:8])


def test_advisory_lock_keys_are_deterministic() -> None:
    locator = generate_credential_locator()
    first = advisory_lock_keys(locator)
    second = advisory_lock_keys(locator)
    assert first == second
    assert first == _expected_keys(locator)
    assert all(isinstance(part, int) for part in first)
    assert all(-2_147_483_648 <= part <= 2_147_483_647 for part in first)


def test_same_locator_maps_to_same_keys() -> None:
    locator = "oauth-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert advisory_lock_keys(locator) == advisory_lock_keys(locator)


def test_different_locators_map_to_different_tested_keys() -> None:
    left = advisory_lock_keys("oauth-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    right = advisory_lock_keys("oauth-cccccccccccccccccccccccccccccccc")
    assert left != right


def test_builtin_hash_is_not_used() -> None:
    source = _MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "hash"
    assert "hashlib.sha256" in source
