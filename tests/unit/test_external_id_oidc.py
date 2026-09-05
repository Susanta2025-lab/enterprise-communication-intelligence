"""Offline External ID / CIAM-shaped OIDC authentication tests.

These tests never contact Microsoft discovery or JWKS endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    COMMUNICATIONS_CONNECT_PERMISSION,
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticationFailedError,
    StaticSigningKeyResolver,
    TokenValidator,
)
from tests.support.jwt_tokens import (
    CIAM_TEST_AUDIENCE,
    CIAM_TEST_ISSUER,
    CIAM_TEST_JWKS_URL,
    TEST_KID,
    TEST_PERMISSION,
    TEST_SUBJECT,
    WORKFORCE_LOOKING_ISSUER,
    encode_test_token,
    generate_test_rsa_private_key,
    make_test_validator,
)

_ECI_SCOPES = " ".join(
    (
        COMMUNICATIONS_READ_PERMISSION,
        TEST_PERMISSION,
        COMMUNICATIONS_CONNECT_PERMISSION,
        COMMUNICATIONS_WORKFLOW_PERMISSION,
        COMMUNICATIONS_SEND_PERMISSION,
    )
)


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def ciam_validator(private_key) -> TokenValidator:
    return make_test_validator(
        private_key,
        issuer=CIAM_TEST_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
    )


def test_ciam_shaped_issuer_is_accepted_when_configured(
    private_key,
    ciam_validator: TokenValidator,
) -> None:
    """A CIAM issuer authenticates only when it exactly matches OIDC_ISSUER."""
    token = encode_test_token(
        private_key,
        issuer=CIAM_TEST_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
        extra_claims={"scp": _ECI_SCOPES},
    )
    principal = ciam_validator.authenticate(token)
    assert principal.issuer == CIAM_TEST_ISSUER
    assert principal.subject == TEST_SUBJECT
    assert principal.permissions == frozenset(
        {
            COMMUNICATIONS_READ_PERMISSION,
            TEST_PERMISSION,
            COMMUNICATIONS_CONNECT_PERMISSION,
            COMMUNICATIONS_WORKFLOW_PERMISSION,
            COMMUNICATIONS_SEND_PERMISSION,
        }
    )
    ciam_validator.authorize(principal)


def test_different_issuer_is_rejected_against_ciam_configuration(
    private_key,
    ciam_validator: TokenValidator,
) -> None:
    """A non-matching issuer fails closed, including a workforce-looking host."""
    for issuer in (
        "https://other.example.ciamlogin.com/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/v2.0",
        WORKFORCE_LOOKING_ISSUER,
    ):
        token = encode_test_token(
            private_key,
            issuer=issuer,
            audience=CIAM_TEST_AUDIENCE,
            extra_claims={"scp": TEST_PERMISSION},
        )
        with pytest.raises(AuthenticationFailedError) as exc_info:
            ciam_validator.authenticate(token)
        assert exc_info.value.reason == "invalid_issuer"


def test_wrong_audience_is_rejected_against_ciam_configuration(
    private_key,
    ciam_validator: TokenValidator,
) -> None:
    """Audience remains exact; a different API identifier is rejected."""
    token = encode_test_token(
        private_key,
        issuer=CIAM_TEST_ISSUER,
        audience="33333333-3333-3333-3333-333333333333",
        extra_claims={"scp": TEST_PERMISSION},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        ciam_validator.authenticate(token)
    assert exc_info.value.reason == "invalid_audience"


def test_missing_or_blank_subject_is_rejected_against_ciam_configuration(
    private_key,
    ciam_validator: TokenValidator,
) -> None:
    """Subject remains required. oid/email cannot substitute for sub."""
    blank = encode_test_token(
        private_key,
        subject="",
        issuer=CIAM_TEST_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
        extra_claims={"scp": TEST_PERMISSION, "oid": "not-a-subject"},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        ciam_validator.authenticate(blank)
    assert exc_info.value.reason == "invalid_token"

    now = datetime.now(UTC)
    missing_sub = jwt.encode(
        {
            "iss": CIAM_TEST_ISSUER,
            "aud": CIAM_TEST_AUDIENCE,
            "exp": now + timedelta(minutes=5),
            "iat": now,
            "oid": "not-a-subject",
            "email": "ada@example.com",
            "scp": TEST_PERMISSION,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": TEST_KID},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        ciam_validator.authenticate(missing_sub)
    assert exc_info.value.reason == "invalid_token"


def test_permissions_continue_from_scp_scope_and_roles(
    private_key,
    ciam_validator: TokenValidator,
) -> None:
    """External ID tokens still authorize from the existing permission claims."""
    for extra_claims in (
        {"scp": COMMUNICATIONS_WORKFLOW_PERMISSION},
        {"scope": COMMUNICATIONS_CONNECT_PERMISSION},
        {"roles": [COMMUNICATIONS_SEND_PERMISSION]},
    ):
        token = encode_test_token(
            private_key,
            issuer=CIAM_TEST_ISSUER,
            audience=CIAM_TEST_AUDIENCE,
            extra_claims=extra_claims,
        )
        principal = ciam_validator.authenticate(token)
        required = next(iter(principal.permissions))
        ciam_validator.authorize(principal, required)


def test_tid_and_oid_are_not_required_for_authentication(
    private_key,
    ciam_validator: TokenValidator,
) -> None:
    """Application authentication must not depend on tid or oid."""
    without_directory_claims = encode_test_token(
        private_key,
        issuer=CIAM_TEST_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
        extra_claims={"scp": TEST_PERMISSION},
    )
    principal = ciam_validator.authenticate(without_directory_claims)
    assert principal.issuer == CIAM_TEST_ISSUER
    assert principal.subject == TEST_SUBJECT
    ciam_validator.authorize(principal)

    with_unused_directory_claims = encode_test_token(
        private_key,
        issuer=CIAM_TEST_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
        extra_claims={
            "scp": TEST_PERMISSION,
            "tid": "44444444-4444-4444-4444-444444444444",
            "oid": "55555555-5555-5555-5555-555555555555",
            "email": "ada@example.com",
        },
    )
    ignored = ciam_validator.authenticate(with_unused_directory_claims)
    assert ignored.issuer == CIAM_TEST_ISSUER
    assert ignored.subject == TEST_SUBJECT
    assert ignored.subject != "55555555-5555-5555-5555-555555555555"


def test_principal_identity_is_verified_iss_and_sub(
    private_key,
    ciam_validator: TokenValidator,
) -> None:
    """IdentityResolver receives the verified issuer and subject only."""
    token = encode_test_token(
        private_key,
        subject="pairwise-external-id-subject",
        issuer=CIAM_TEST_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
        extra_claims={
            "scp": TEST_PERMISSION,
            "oid": "should-not-become-subject",
            "email": "should-not-become-identity@example.com",
        },
    )
    principal = ciam_validator.authenticate(token)
    assert principal.issuer == CIAM_TEST_ISSUER
    assert principal.subject == "pairwise-external-id-subject"
    assert set(principal.__dataclass_fields__) == {"issuer", "subject", "permissions"}


def test_issuer_matching_is_exact_not_hostname_specific(private_key) -> None:
    """Workforce and CIAM-looking hosts are accepted only as the configured issuer."""
    workforce_validator = make_test_validator(
        private_key,
        issuer=WORKFORCE_LOOKING_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
    )
    ciam_token = encode_test_token(
        private_key,
        issuer=CIAM_TEST_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
        extra_claims={"scp": TEST_PERMISSION},
    )
    workforce_token = encode_test_token(
        private_key,
        issuer=WORKFORCE_LOOKING_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
        extra_claims={"scp": TEST_PERMISSION},
    )

    assert workforce_validator.authenticate(workforce_token).issuer == WORKFORCE_LOOKING_ISSUER
    with pytest.raises(AuthenticationFailedError) as exc_info:
        workforce_validator.authenticate(ciam_token)
    assert exc_info.value.reason == "invalid_issuer"


def test_settings_accept_ciam_shaped_oidc_contract(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    """OIDC settings accept an External ID issuer without a workforce host."""
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", CIAM_TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", CIAM_TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", CIAM_TEST_JWKS_URL)
    settings = Settings(_env_file=None)
    assert settings.oidc_issuer == CIAM_TEST_ISSUER
    assert settings.oidc_audience == CIAM_TEST_AUDIENCE
    assert settings.oidc_jwks_url == CIAM_TEST_JWKS_URL
    assert "login.microsoftonline.com" not in (settings.oidc_issuer or "")
    assert "login.microsoftonline.com" not in (settings.oidc_jwks_url or "")

    validator = TokenValidator.from_settings(
        settings,
        key_resolver=StaticSigningKeyResolver({TEST_KID: private_key.public_key()}),
    )
    token = encode_test_token(
        private_key,
        issuer=CIAM_TEST_ISSUER,
        audience=CIAM_TEST_AUDIENCE,
        extra_claims={"scp": TEST_PERMISSION},
    )
    principal = validator.authenticate(token)
    assert principal.issuer == CIAM_TEST_ISSUER
    assert principal.subject == TEST_SUBJECT
