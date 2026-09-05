"""Offline JWT helpers for authentication tests.

Generated RSA material is test-only and is never a real identity-provider key.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, generate_private_key

from app.core.security import StaticSigningKeyResolver, TokenValidator

TEST_ISSUER = "https://example.invalid/"
TEST_AUDIENCE = "eci-api"
TEST_JWKS_URL = "https://example.invalid/.well-known/jwks.json"
TEST_KID = "eci-test-key"
TEST_PERMISSION = "communications:analyze"
TEST_SUBJECT = "eci-test-subject"
CIAM_TEST_ISSUER = (
    "https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111/v2.0"
)
CIAM_TEST_AUDIENCE = "22222222-2222-2222-2222-222222222222"
CIAM_TEST_JWKS_URL = (
    "https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111"
    "/discovery/v2.0/keys"
)
WORKFORCE_LOOKING_ISSUER = (
    "https://login.microsoftonline.com/99999999-9999-9999-9999-999999999999/v2.0"
)


def generate_test_rsa_private_key() -> RSAPrivateKey:
    """Return a throwaway 2048-bit RSA key for local JWT tests."""
    return generate_private_key(public_exponent=65537, key_size=2048)


def make_test_validator(
    private_key: RSAPrivateKey,
    *,
    kid: str = TEST_KID,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    required_permission: str = TEST_PERMISSION,
) -> TokenValidator:
    """Build a TokenValidator that never contacts a JWKS URL."""
    return TokenValidator(
        issuer=issuer,
        audience=audience,
        required_permission=required_permission,
        key_resolver=StaticSigningKeyResolver({kid: private_key.public_key()}),
    )


def encode_test_token(
    private_key: RSAPrivateKey,
    *,
    subject: str = TEST_SUBJECT,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    expires_delta: timedelta = timedelta(minutes=5),
    kid: str = TEST_KID,
    extra_claims: dict[str, Any] | None = None,
    algorithm: str = "RS256",
) -> str:
    """Create a signed test JWT. Do not use real tenant values."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "exp": now + expires_delta,
        "iat": now,
    }
    if extra_claims:
        payload.update(extra_claims)
    headers = {"kid": kid} if kid else {}
    return jwt.encode(
        payload,
        private_key,
        algorithm=algorithm,
        headers=headers or None,
    )


def bearer_header(token: str) -> dict[str, str]:
    """Return an Authorization header for ``token``."""
    return {"Authorization": f"Bearer {token}"}
