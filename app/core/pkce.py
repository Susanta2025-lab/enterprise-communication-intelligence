"""RFC 7636 S256 PKCE utilities. No provider SDK dependency."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets

_CODE_CHALLENGE_METHOD = "S256"
_VERIFIER_PATTERN = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
_VERIFIER_RANDOM_BYTES = 32


class PkceS256:
    """Generate and derive S256 PKCE material.

    ``plain`` is not supported. Verifiers must never be logged.
    """

    method = _CODE_CHALLENGE_METHOD

    @staticmethod
    def generate_code_verifier() -> str:
        """Return a cryptographically random RFC 7636 code_verifier."""
        verifier = secrets.token_urlsafe(_VERIFIER_RANDOM_BYTES)
        if _VERIFIER_PATTERN.fullmatch(verifier) is None:
            raise RuntimeError("Generated PKCE verifier is invalid.")
        return verifier

    @staticmethod
    def code_challenge(code_verifier: str) -> str:
        """Return BASE64URL(SHA256(verifier)) without padding."""
        if _VERIFIER_PATTERN.fullmatch(code_verifier) is None:
            raise ValueError("PKCE code_verifier is invalid.")
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def is_valid_code_verifier(code_verifier: str) -> bool:
        """Return True when ``code_verifier`` matches RFC 7636 length and charset."""
        return _VERIFIER_PATTERN.fullmatch(code_verifier) is not None
