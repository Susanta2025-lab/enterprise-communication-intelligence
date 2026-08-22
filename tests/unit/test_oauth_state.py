"""Unit tests for OAuth state generation and hashing."""

from app.core.oauth_state import generate_oauth_state, hash_oauth_state, is_oauth_state_hash


def test_generated_state_has_at_least_256_bits_of_entropy_shape() -> None:
    """token_urlsafe(32) yields 43 unpadded url-safe characters (256 bits)."""
    state = generate_oauth_state()
    assert len(state) >= 43
    assert " " not in state
    assert "\n" not in state


def test_generated_states_differ() -> None:
    """Independent generations must not collide in ordinary use."""
    states = {generate_oauth_state() for _ in range(32)}
    assert len(states) == 32


def test_state_hash_is_sha256_hex_and_deterministic() -> None:
    """The same raw state hashes to the same 64-character hex digest."""
    state = generate_oauth_state()
    digest = hash_oauth_state(state)
    assert digest == hash_oauth_state(state)
    assert is_oauth_state_hash(digest)
    assert digest != state
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(char in "0123456789abcdef" for char in digest)


def test_different_states_produce_different_hashes() -> None:
    """Distinct raw states do not share a digest."""
    first = generate_oauth_state()
    second = generate_oauth_state()
    assert hash_oauth_state(first) != hash_oauth_state(second)


def test_raw_state_is_not_a_hash() -> None:
    """Raw url-safe state is not persisted as a SHA-256 hex digest."""
    assert is_oauth_state_hash(generate_oauth_state()) is False
    assert is_oauth_state_hash("not-a-hash") is False
    assert is_oauth_state_hash("g" * 64) is False
