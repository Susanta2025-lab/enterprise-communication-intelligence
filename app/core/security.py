"""Provider-independent JWT bearer authentication and permission checks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    PyJWKClientError,
    PyJWTError,
)

from app.core.config import Settings

ALLOWED_JWT_ALGORITHMS = ("RS256",)
COMMUNICATIONS_WORKFLOW_PERMISSION = "communications:workflow"
COMMUNICATIONS_SEND_PERMISSION = "communications:send"
COMMUNICATIONS_CONNECT_PERMISSION = "communications:connect"
COMMUNICATIONS_READ_PERMISSION = "communications:read"
_PERMISSION_CLAIMS = ("scp", "scope", "roles")


class AuthenticationFailedError(Exception):
    """Raised when a bearer token is missing or cannot be validated."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class AuthorizationFailedError(Exception):
    """Raised when an authenticated principal lacks a required permission."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Generic authenticated caller derived from a validated access token.

    ``issuer`` and ``subject`` come from verified JWT ``iss`` and ``sub`` claims
    after signature, issuer, audience, and expiry checks.
    """

    issuer: str
    subject: str
    permissions: frozenset[str]


class SigningKeyResolver(Protocol):
    """Resolve a JWT signing key without performing claim validation."""

    def get_key(self, token: str) -> Any:
        """Return the key used to verify ``token``."""


class JwksSigningKeyResolver:
    """Resolve signing keys from an OIDC JWKS URL using PyJWT's bounded cache."""

    def __init__(self, jwks_url: str) -> None:
        self._client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)

    def get_key(self, token: str) -> Any:
        try:
            header = jwt.get_unverified_header(token)
        except DecodeError as exc:
            raise AuthenticationFailedError("invalid_token") from exc

        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise AuthenticationFailedError("unknown_signing_key")

        try:
            return self._client.get_signing_key(kid).key
        except PyJWKClientError:
            raise AuthenticationFailedError("unknown_signing_key") from None
        except Exception:
            raise AuthenticationFailedError("invalid_token") from None


class StaticSigningKeyResolver:
    """Resolve signing keys from an in-memory ``kid`` map.

    Intended for offline tests. Does not fetch JWKS and does not persist keys.
    """

    def __init__(self, keys: dict[str, Any]) -> None:
        self._keys = keys

    def get_key(self, token: str) -> Any:
        try:
            header = jwt.get_unverified_header(token)
        except DecodeError as exc:
            raise AuthenticationFailedError("invalid_token") from exc

        kid = header.get("kid")
        if not isinstance(kid, str) or kid not in self._keys:
            raise AuthenticationFailedError("unknown_signing_key")
        return self._keys[kid]


class TokenValidator:
    """Validate OIDC JWT access tokens and extract a principal."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        required_permission: str,
        key_resolver: SigningKeyResolver,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._required_permission = required_permission
        self._key_resolver = key_resolver

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        key_resolver: SigningKeyResolver | None = None,
    ) -> TokenValidator:
        """Build a validator from OIDC Settings.

        ``oidc_issuer``, ``oidc_audience``, and ``oidc_jwks_url`` are required
        when ``AUTH_MODE=oidc``; Settings validation enforces that before startup.
        """
        resolver = key_resolver or JwksSigningKeyResolver(settings.oidc_jwks_url or "")
        return cls(
            issuer=settings.oidc_issuer or "",
            audience=settings.oidc_audience or "",
            required_permission=settings.oidc_required_permission,
            key_resolver=resolver,
        )

    def authenticate(self, token: str) -> AuthenticatedPrincipal:
        """Validate signature, issuer, audience, expiry, and subject."""
        if not token.strip():
            raise AuthenticationFailedError("invalid_token")

        try:
            signing_key = self._key_resolver.get_key(token)
        except AuthenticationFailedError:
            raise
        except Exception:
            raise AuthenticationFailedError("invalid_token") from None

        try:
            payload = jwt.decode(
                token,
                key=signing_key,
                algorithms=list(ALLOWED_JWT_ALGORITHMS),
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except ExpiredSignatureError as exc:
            raise AuthenticationFailedError("expired_token") from exc
        except InvalidIssuerError as exc:
            raise AuthenticationFailedError("invalid_issuer") from exc
        except InvalidAudienceError as exc:
            raise AuthenticationFailedError("invalid_audience") from exc
        except PyJWTError as exc:
            raise AuthenticationFailedError("invalid_token") from exc

        issuer = payload.get("iss")
        if not isinstance(issuer, str) or not issuer.strip():
            raise AuthenticationFailedError("invalid_token")

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationFailedError("invalid_token")

        return AuthenticatedPrincipal(
            issuer=issuer,
            subject=subject,
            permissions=_extract_permissions(payload),
        )

    def authorize(
        self,
        principal: AuthenticatedPrincipal,
        required_permission: str | None = None,
    ) -> None:
        """Require a capability-specific permission.

        When ``required_permission`` is omitted, the configured analyze
        permission (``OIDC_REQUIRED_PERMISSION``) is used so existing callers
        remain unchanged.
        """
        permission = (
            required_permission
            if required_permission is not None
            else self._required_permission
        )
        if not permission.strip() or permission not in principal.permissions:
            raise AuthorizationFailedError("insufficient_permission")

    def authorize_all(
        self,
        principal: AuthenticatedPrincipal,
        required_permissions: Sequence[str],
    ) -> None:
        """Require every listed permission.

        Missing any one permission is ``insufficient_permission``. Permissions
        do not imply each other.
        """
        if not required_permissions:
            raise ValueError("required_permissions must not be empty")
        for permission in required_permissions:
            self.authorize(principal, permission)


def _extract_permissions(payload: dict[str, Any]) -> frozenset[str]:
    """Collect permissions from bounded OIDC/Entra-compatible claims only.

    Supported representations:
    - ``scp``: space-separated string
    - ``scope``: space-separated string
    - ``roles``: list of strings
    """
    permissions: set[str] = set()
    for claim in _PERMISSION_CLAIMS:
        value = payload.get(claim)
        if claim in {"scp", "scope"} and isinstance(value, str):
            permissions.update(part for part in value.split() if part)
        elif claim == "roles" and isinstance(value, list):
            permissions.update(item for item in value if isinstance(item, str) and item)
    return frozenset(permissions)
