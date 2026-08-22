"""Unit tests for RFC 7636 S256 PKCE utilities."""

import pytest

from app.application.services.mailbox_authorization_sessions import (
    MailboxAuthorizationStartResult,
)
from app.core.pkce import PkceS256

# RFC 7636 Appendix B
_RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
_RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_pkce_method_is_s256_only() -> None:
    """Phase 13A supports S256 only."""
    assert PkceS256.method == "S256"
    assert not hasattr(PkceS256, "PLAIN")
    assert not hasattr(PkceS256, "plain")


def test_generated_verifier_matches_rfc_length_and_charset() -> None:
    """Generated verifiers are 43–128 unreserved characters."""
    verifier = PkceS256.generate_code_verifier()
    assert PkceS256.is_valid_code_verifier(verifier)
    assert 43 <= len(verifier) <= 128


def test_rfc_7636_appendix_b_challenge_vector() -> None:
    """Known verifier produces the RFC S256 challenge without padding."""
    challenge = PkceS256.code_challenge(_RFC_VERIFIER)
    assert challenge == _RFC_CHALLENGE
    assert "=" not in challenge
    assert "+" not in challenge
    assert "/" not in challenge


def test_challenge_is_deterministic_for_the_same_verifier() -> None:
    """The same verifier always yields the same S256 challenge."""
    verifier = PkceS256.generate_code_verifier()
    assert PkceS256.code_challenge(verifier) == PkceS256.code_challenge(verifier)


def test_invalid_verifier_is_rejected() -> None:
    """Short, long, and illegal charset verifiers are not hashed."""
    with pytest.raises(ValueError, match="code_verifier"):
        PkceS256.code_challenge("short")
    with pytest.raises(ValueError, match="code_verifier"):
        PkceS256.code_challenge("a" * 129)
    with pytest.raises(ValueError, match="code_verifier"):
        PkceS256.code_challenge("*" * 43)


def test_pkce_start_result_contract_omits_verifier() -> None:
    """The public start result type must not expose the PKCE verifier."""
    fields = set(MailboxAuthorizationStartResult.__dataclass_fields__)
    assert "pkce_verifier" not in fields
    assert "code_verifier" not in fields
    assert "state" in fields
    assert "code_challenge" in fields
    assert "code_challenge_method" in fields
    assert "user_id" not in fields
    assert "credential_ref" not in fields
