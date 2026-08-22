"""Environment-backed CommunicationCredentialResolver for local development.

This is not production OAuth, token refresh, Azure Key Vault, or AWS Secrets
Manager. Ordinary application startup does not require mailbox secrets.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Mapping

from app.core.exceptions import (
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.interfaces.communication_credential_resolver import (
    AccessTokenProvider,
    CommunicationCredentialResolver,
)

logger = get_logger(__name__)

_ENV_PREFIX = "ECI_COMMUNICATION_CREDENTIAL_"
_ENV_SUFFIX = "_ACCESS_TOKEN"
_CREDENTIAL_REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,62}$")
_PROVIDER_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_SUPPORTED_PROVIDERS = frozenset({"gmail", "microsoft_graph"})
_RESOLVER_BACKEND = "environment"


class EnvironmentCommunicationCredentialResolver(CommunicationCredentialResolver):
    """Map an opaque credential_ref to a process-environment access token.

    Environment lookup is injected for tests. The default source is the live
    process environment. Secrets are not cached globally.

    ``credential_ref`` is not unique on ConnectorAccount, so the environment
    variable includes the validated provider slug. Underscores are rejected in
    locators so hyphen-to-underscore encoding cannot collide.
    """

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    def __repr__(self) -> str:
        return "EnvironmentCommunicationCredentialResolver()"

    def resolve(
        self,
        *,
        credential_ref: str,
        provider: str,
    ) -> AccessTokenProvider:
        """Validate locator and provider, then return an on-demand token callable."""
        started_at = time.perf_counter()
        try:
            locator = _require_credential_ref(credential_ref)
            provider_slug = _require_supported_provider(provider)
        except (
            CommunicationCredentialUnavailableError,
            UnsupportedCommunicationCredentialProviderError,
        ) as exc:
            logger.warning(
                "communication_credential_resolution_failed",
                operation="resolve",
                resolver_backend=_RESOLVER_BACKEND,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise
        env_name = _environment_variable_name(locator, provider_slug)
        environ = self._environ

        def provide_access_token() -> str:
            lookup_started_at = time.perf_counter()
            try:
                return _require_access_token(environ.get(env_name))
            except CommunicationCredentialUnavailableError as exc:
                _log_token_lookup_failure(lookup_started_at, provider_slug, exc)
                raise
            except Exception:
                unavailable = CommunicationCredentialUnavailableError()
                _log_token_lookup_failure(lookup_started_at, provider_slug, unavailable)
                raise unavailable from None

        return provide_access_token


def _log_token_lookup_failure(
    started_at: float,
    provider_slug: str,
    exc: CommunicationCredentialUnavailableError,
) -> None:
    logger.warning(
        "communication_credential_unavailable",
        operation="provide_access_token",
        provider=provider_slug,
        resolver_backend=_RESOLVER_BACKEND,
        duration_ms=elapsed_ms(started_at),
        error_class=error_class(exc),
    )


def _require_credential_ref(credential_ref: str) -> str:
    if not isinstance(credential_ref, str):
        raise CommunicationCredentialUnavailableError()
    if _CREDENTIAL_REF_PATTERN.fullmatch(credential_ref) is None:
        raise CommunicationCredentialUnavailableError()
    return credential_ref


def _require_supported_provider(provider: str) -> str:
    if not isinstance(provider, str):
        raise UnsupportedCommunicationCredentialProviderError()
    slug = provider.strip().lower()
    if not slug or _PROVIDER_SLUG.fullmatch(slug) is None:
        raise UnsupportedCommunicationCredentialProviderError()
    if slug not in _SUPPORTED_PROVIDERS:
        raise UnsupportedCommunicationCredentialProviderError()
    return slug


def _environment_variable_name(credential_ref: str, provider: str) -> str:
    normalized_ref = credential_ref.upper().replace("-", "_")
    return f"{_ENV_PREFIX}{provider.upper()}_{normalized_ref}{_ENV_SUFFIX}"


def _require_access_token(raw: object) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise CommunicationCredentialUnavailableError()
    return raw.strip()
