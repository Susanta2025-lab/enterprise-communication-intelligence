"""Unit tests for provider-independent JWT validation and authorization."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from jwt.exceptions import PyJWKClientConnectionError

from app.core.security import (
    COMMUNICATIONS_SEND_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticationFailedError,
    AuthorizationFailedError,
    JwksSigningKeyResolver,
    StaticSigningKeyResolver,
    TokenValidator,
)
from tests.support.jwt_tokens import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    TEST_KID,
    TEST_PERMISSION,
    TEST_SUBJECT,
    encode_test_token,
    generate_test_rsa_private_key,
    make_test_validator,
)


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def validator(private_key) -> TokenValidator:
    return make_test_validator(private_key)


def test_valid_signed_token_returns_principal(private_key, validator: TokenValidator) -> None:
    """A correctly signed token should authenticate and expose bounded permissions."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": TEST_PERMISSION},
    )
    principal = validator.authenticate(token)
    assert principal.issuer == TEST_ISSUER
    assert principal.subject == TEST_SUBJECT
    assert TEST_PERMISSION in principal.permissions
    validator.authorize(principal)


def test_expired_token_is_rejected(private_key, validator: TokenValidator) -> None:
    """Expired tokens must fail authentication."""
    token = encode_test_token(
        private_key,
        expires_delta=timedelta(minutes=-1),
        extra_claims={"scp": TEST_PERMISSION},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason == "expired_token"


def test_wrong_issuer_is_rejected(private_key, validator: TokenValidator) -> None:
    """Tokens from another issuer must fail authentication."""
    token = encode_test_token(
        private_key,
        issuer="https://other.example.invalid/",
        extra_claims={"scp": TEST_PERMISSION},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason == "invalid_issuer"


def test_wrong_audience_is_rejected(private_key, validator: TokenValidator) -> None:
    """Tokens for another audience must fail authentication."""
    token = encode_test_token(
        private_key,
        audience="other-api",
        extra_claims={"scp": TEST_PERMISSION},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason == "invalid_audience"


def test_invalid_signature_is_rejected(private_key, validator: TokenValidator) -> None:
    """A token signed by a different key must fail authentication."""
    other_key = generate_test_rsa_private_key()
    token = encode_test_token(other_key, extra_claims={"scp": TEST_PERMISSION})
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason == "invalid_token"


def test_unknown_signing_key_is_rejected(private_key, validator: TokenValidator) -> None:
    """A token whose kid is not in the resolver must fail authentication."""
    token = encode_test_token(
        private_key,
        kid="unknown-kid",
        extra_claims={"scp": TEST_PERMISSION},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason == "unknown_signing_key"


def test_malformed_token_is_rejected(validator: TokenValidator) -> None:
    """Non-JWT input must fail authentication."""
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate("not-a-jwt")
    assert exc_info.value.reason == "invalid_token"


def test_empty_token_is_rejected(validator: TokenValidator) -> None:
    """An empty bearer credential must fail authentication."""
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate("   ")
    assert exc_info.value.reason == "invalid_token"


def test_alg_none_token_is_rejected(validator: TokenValidator) -> None:
    """Unsigned alg=none tokens must not authenticate."""
    token = (
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIiwia2lkIjoiZWNpLXRlc3Qta2V5In0."
        "eyJzdWIiOiJlY2ktdGVzdC1zdWJqZWN0In0."
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason in {"invalid_token", "unknown_signing_key"}


def test_missing_issuer_is_rejected(private_key, validator: TokenValidator) -> None:
    """Tokens without a usable iss claim must fail authentication."""
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": TEST_SUBJECT,
            "aud": TEST_AUDIENCE,
            "exp": now + timedelta(minutes=5),
            "iat": now,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": TEST_KID},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason in {"invalid_token", "invalid_issuer"}


def test_missing_subject_is_rejected(private_key, validator: TokenValidator) -> None:
    """Tokens without a usable sub claim must fail authentication."""
    token = encode_test_token(
        private_key,
        subject="",
        extra_claims={"scp": TEST_PERMISSION},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason == "invalid_token"


def test_scope_claim_authorizes_analyze(private_key, validator: TokenValidator) -> None:
    """The OIDC scope claim may carry communications:analyze."""
    token = encode_test_token(
        private_key,
        extra_claims={"scope": TEST_PERMISSION},
    )
    principal = validator.authenticate(token)
    validator.authorize(principal)


def test_roles_claim_authorizes_analyze(private_key, validator: TokenValidator) -> None:
    """The roles claim may carry communications:analyze."""
    token = encode_test_token(
        private_key,
        extra_claims={"roles": [TEST_PERMISSION]},
    )
    principal = validator.authenticate(token)
    validator.authorize(principal)


def test_valid_token_without_permission_is_forbidden(
    private_key,
    validator: TokenValidator,
) -> None:
    """A valid token without the analyze permission must fail authorization."""
    token = encode_test_token(private_key)
    principal = validator.authenticate(token)
    with pytest.raises(AuthorizationFailedError) as exc_info:
        validator.authorize(principal)
    assert exc_info.value.reason == "insufficient_permission"


def test_unrelated_permission_is_forbidden(private_key, validator: TokenValidator) -> None:
    """Unrelated scopes must not satisfy communications:analyze."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": "other:permission"},
    )
    principal = validator.authenticate(token)
    with pytest.raises(AuthorizationFailedError) as exc_info:
        validator.authorize(principal)
    assert exc_info.value.reason == "insufficient_permission"


def test_workflow_permission_does_not_satisfy_analyze(
    private_key,
    validator: TokenValidator,
) -> None:
    """communications:workflow must not implicitly grant communications:analyze."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": COMMUNICATIONS_WORKFLOW_PERMISSION},
    )
    principal = validator.authenticate(token)
    assert COMMUNICATIONS_WORKFLOW_PERMISSION in principal.permissions
    assert TEST_PERMISSION not in principal.permissions
    with pytest.raises(AuthorizationFailedError) as exc_info:
        validator.authorize(principal)
    assert exc_info.value.reason == "insufficient_permission"
    with pytest.raises(AuthorizationFailedError):
        validator.authorize(principal, TEST_PERMISSION)
    validator.authorize(principal, COMMUNICATIONS_WORKFLOW_PERMISSION)


def test_analyze_permission_does_not_satisfy_workflow(
    private_key,
    validator: TokenValidator,
) -> None:
    """communications:analyze must not implicitly grant communications:workflow."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": TEST_PERMISSION},
    )
    principal = validator.authenticate(token)
    validator.authorize(principal)
    with pytest.raises(AuthorizationFailedError) as exc_info:
        validator.authorize(principal, COMMUNICATIONS_WORKFLOW_PERMISSION)
    assert exc_info.value.reason == "insufficient_permission"


def test_send_permission_does_not_satisfy_analyze_or_workflow(
    private_key,
    validator: TokenValidator,
) -> None:
    """communications:send must not implicitly grant analyze or workflow."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": COMMUNICATIONS_SEND_PERMISSION},
    )
    principal = validator.authenticate(token)
    assert COMMUNICATIONS_SEND_PERMISSION in principal.permissions
    with pytest.raises(AuthorizationFailedError):
        validator.authorize(principal)
    with pytest.raises(AuthorizationFailedError):
        validator.authorize(principal, TEST_PERMISSION)
    with pytest.raises(AuthorizationFailedError):
        validator.authorize(principal, COMMUNICATIONS_WORKFLOW_PERMISSION)
    validator.authorize(principal, COMMUNICATIONS_SEND_PERMISSION)


def test_workflow_permission_does_not_satisfy_send(
    private_key,
    validator: TokenValidator,
) -> None:
    """communications:workflow must not implicitly grant communications:send."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": COMMUNICATIONS_WORKFLOW_PERMISSION},
    )
    principal = validator.authenticate(token)
    with pytest.raises(AuthorizationFailedError):
        validator.authorize(principal, COMMUNICATIONS_SEND_PERMISSION)


def test_principal_with_both_permissions_satisfies_either_check(
    private_key,
    validator: TokenValidator,
) -> None:
    """A principal may hold analyze and workflow permissions independently."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": f"{TEST_PERMISSION} {COMMUNICATIONS_WORKFLOW_PERMISSION}"},
    )
    principal = validator.authenticate(token)
    assert TEST_PERMISSION in principal.permissions
    assert COMMUNICATIONS_WORKFLOW_PERMISSION in principal.permissions
    validator.authorize(principal)
    validator.authorize(principal, TEST_PERMISSION)
    validator.authorize(principal, COMMUNICATIONS_WORKFLOW_PERMISSION)


def test_permission_matching_is_exact(
    private_key,
    validator: TokenValidator,
) -> None:
    """Authorization must not treat prefixes, suffixes, or substrings as grants."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": TEST_PERMISSION},
    )
    principal = validator.authenticate(token)
    for required in (
        "communications",
        "analyze",
        "communications:anal",
        f"{TEST_PERMISSION}:extra",
        f"prefix:{TEST_PERMISSION}",
    ):
        with pytest.raises(AuthorizationFailedError) as exc_info:
            validator.authorize(principal, required)
        assert exc_info.value.reason == "insufficient_permission"
    validator.authorize(principal, TEST_PERMISSION)


def test_blank_required_permission_does_not_authorize(
    private_key,
    validator: TokenValidator,
) -> None:
    """An empty or whitespace permission argument must fail closed."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": TEST_PERMISSION},
    )
    principal = validator.authenticate(token)
    for required in ("", "   "):
        with pytest.raises(AuthorizationFailedError) as exc_info:
            validator.authorize(principal, required)
        assert exc_info.value.reason == "insufficient_permission"
    validator.authorize(principal)


def test_arbitrary_claim_is_not_used_for_authorization(
    private_key,
    validator: TokenValidator,
) -> None:
    """Permissions must not be taken from unsupported claims."""
    token = encode_test_token(
        private_key,
        extra_claims={"permissions": [TEST_PERMISSION], "groups": [TEST_PERMISSION]},
    )
    principal = validator.authenticate(token)
    assert TEST_PERMISSION not in principal.permissions
    with pytest.raises(AuthorizationFailedError):
        validator.authorize(principal)


def test_static_resolver_does_not_use_network(private_key) -> None:
    """Static key resolution stays in-process and keyed by kid."""
    resolver = StaticSigningKeyResolver({TEST_KID: private_key.public_key()})
    token = encode_test_token(private_key, extra_claims={"scp": TEST_PERMISSION})
    key = resolver.get_key(token)
    assert key is not None


def test_missing_kid_is_rejected(private_key, validator: TokenValidator) -> None:
    """Tokens without a kid must fail authentication."""
    token = encode_test_token(
        private_key,
        kid="",
        extra_claims={"scp": TEST_PERMISSION},
    )
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason == "unknown_signing_key"


def test_jwks_connection_error_becomes_authentication_failure(private_key) -> None:
    """JWKS network failures must not escape as unhandled errors."""
    resolver = JwksSigningKeyResolver("https://example.invalid/.well-known/jwks.json")

    def _raise_connection_error(_kid: str) -> None:
        raise PyJWKClientConnectionError("ECI_PRIVATE_JWKS_SENTINEL")

    resolver._client.get_signing_key = _raise_connection_error
    token = encode_test_token(private_key, extra_claims={"scp": TEST_PERMISSION})
    with pytest.raises(AuthenticationFailedError) as exc_info:
        resolver.get_key(token)
    assert exc_info.value.reason == "unknown_signing_key"
    assert exc_info.value.__cause__ is None
    assert "ECI_PRIVATE_JWKS_SENTINEL" not in str(exc_info.value)


def test_unexpected_key_resolution_error_becomes_invalid_token(private_key) -> None:
    """Unexpected JWKS/parse errors must fail closed as invalid_token."""

    class _BrokenResolver:
        def get_key(self, _token: str) -> object:
            raise OSError("ECI_PRIVATE_JWKS_SENTINEL")

    validator = TokenValidator(
        issuer="https://example.invalid/",
        audience="eci-api",
        required_permission=TEST_PERMISSION,
        key_resolver=_BrokenResolver(),
    )
    token = encode_test_token(private_key, extra_claims={"scp": TEST_PERMISSION})
    with pytest.raises(AuthenticationFailedError) as exc_info:
        validator.authenticate(token)
    assert exc_info.value.reason == "invalid_token"
    assert exc_info.value.__cause__ is None
    assert "ECI_PRIVATE_JWKS_SENTINEL" not in str(exc_info.value)


def test_malformed_send_permission_claims_are_not_grants(
    private_key,
    validator: TokenValidator,
) -> None:
    """Non-string scp/scope/roles representations must not grant communications:send."""
    for extra_claims in (
        {"scp": [COMMUNICATIONS_SEND_PERMISSION]},
        {"scope": [COMMUNICATIONS_SEND_PERMISSION]},
        {"roles": COMMUNICATIONS_SEND_PERMISSION},
        {"roles": [1]},
        {"scp": {"permission": COMMUNICATIONS_SEND_PERMISSION}},
    ):
        token = encode_test_token(private_key, extra_claims=extra_claims)
        principal = validator.authenticate(token)
        assert COMMUNICATIONS_SEND_PERMISSION not in principal.permissions
        with pytest.raises(AuthorizationFailedError):
            validator.authorize(principal, COMMUNICATIONS_SEND_PERMISSION)
