"""Process-level mailbox OAuth composition for runtime.

Development may share an in-memory credential store between OAuth callback
creation and token refresh. Production requires a durable Azure Key Vault or
AWS Secrets Manager backend and never uses process memory for OAuth secrets.
"""

from __future__ import annotations

import threading

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.domain.interfaces.communication_credential_resolver import (
    CommunicationCredentialResolver,
)
from app.domain.interfaces.communication_credential_store import CommunicationCredentialStore
from app.infrastructure.credentials.composite import CompositeCommunicationCredentialResolver
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.infrastructure.credentials.factory import (
    build_communication_credential_store,
    resolved_credential_store_backend,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.oauth import OAuthCommunicationCredentialResolver
from app.infrastructure.credentials.refresh import RefreshableCredentialAdapter
from app.infrastructure.oauth.google import (
    GoogleMailboxOAuthClient,
    GoogleRefreshableCredentialAdapter,
)
from app.infrastructure.oauth.microsoft import (
    MicrosoftMailboxOAuthClient,
    MicrosoftRefreshableCredentialAdapter,
)

_GMAIL_UNAVAILABLE = "Gmail mailbox authorization is unavailable."
_MICROSOFT_UNAVAILABLE = "Microsoft mailbox authorization is unavailable."
_MEMORY_FORBIDDEN = "In-memory credential store is not allowed when APP_ENV=production."

_lock = threading.Lock()
_memory_store: InMemoryCommunicationCredentialStore | None = None
_store: CommunicationCredentialStore | None = None
_oauth_resolver: OAuthCommunicationCredentialResolver | None = None


def _credential_store_ready(settings: Settings) -> bool:
    backend = settings.credential_store_backend
    if settings.app_env == "production":
        return settings.durable_oauth_store_is_configured
    if backend is None or backend == "memory":
        return True
    return settings.durable_oauth_store_is_configured


def gmail_oauth_connect_available(settings: Settings) -> bool:
    """Return True when Gmail OAuth connect may use the configured store.

    Production must not claim durable OAuth with a process-memory store.
    """
    if not settings.gmail_oauth_is_configured:
        return False
    return _credential_store_ready(settings)


def microsoft_oauth_connect_available(settings: Settings) -> bool:
    """Return True when Microsoft OAuth connect may use the configured store.

    Production must not claim durable OAuth with a process-memory store.
    """
    if not settings.microsoft_oauth_is_configured:
        return False
    return _credential_store_ready(settings)


def mailbox_oauth_store_available(settings: Settings) -> bool:
    """Return True when any mailbox OAuth provider may use the credential store."""
    return gmail_oauth_connect_available(settings) or microsoft_oauth_connect_available(
        settings
    )


def get_shared_memory_credential_store() -> InMemoryCommunicationCredentialStore:
    """Return the process-wide in-memory store. Not production storage."""
    with _lock:
        return _memory_store_locked()


def _memory_store_locked() -> InMemoryCommunicationCredentialStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = InMemoryCommunicationCredentialStore()
    return _memory_store


def get_shared_credential_store(settings: Settings) -> CommunicationCredentialStore:
    """Return the process-wide store selected by Settings."""
    global _store
    with _lock:
        if _store is None:
            backend = resolved_credential_store_backend(settings)
            if backend == "memory":
                if settings.app_env == "production":
                    raise ServiceUnavailableError(_MEMORY_FORBIDDEN)
                _store = _memory_store_locked()
            else:
                _store = build_communication_credential_store(settings)
        return _store


def reset_shared_memory_credential_store() -> None:
    """Drop the process-wide store. Intended for tests only."""
    global _memory_store, _store, _oauth_resolver
    with _lock:
        _memory_store = None
        _store = None
        _oauth_resolver = None


def build_gmail_oauth_client(settings: Settings) -> GoogleMailboxOAuthClient:
    """Construct the Google OAuth adapter from complete Settings."""
    if not settings.gmail_oauth_is_configured:
        raise ServiceUnavailableError(_GMAIL_UNAVAILABLE)
    secret = settings.gmail_oauth_client_secret
    if secret is None or settings.gmail_oauth_client_id is None:
        raise ServiceUnavailableError(_GMAIL_UNAVAILABLE)
    if settings.gmail_oauth_redirect_uri is None:
        raise ServiceUnavailableError(_GMAIL_UNAVAILABLE)
    return GoogleMailboxOAuthClient(
        client_id=settings.gmail_oauth_client_id,
        client_secret=secret.get_secret_value(),
        redirect_uri=settings.gmail_oauth_redirect_uri,
    )


def build_microsoft_oauth_client(settings: Settings) -> MicrosoftMailboxOAuthClient:
    """Construct the Microsoft OAuth adapter from complete Settings."""
    if not settings.microsoft_oauth_is_configured:
        raise ServiceUnavailableError(_MICROSOFT_UNAVAILABLE)
    secret = settings.microsoft_oauth_client_secret
    if secret is None or settings.microsoft_oauth_client_id is None:
        raise ServiceUnavailableError(_MICROSOFT_UNAVAILABLE)
    if settings.microsoft_oauth_redirect_uri is None:
        raise ServiceUnavailableError(_MICROSOFT_UNAVAILABLE)
    if settings.microsoft_oauth_tenant is None:
        raise ServiceUnavailableError(_MICROSOFT_UNAVAILABLE)
    return MicrosoftMailboxOAuthClient(
        client_id=settings.microsoft_oauth_client_id,
        client_secret=secret.get_secret_value(),
        redirect_uri=settings.microsoft_oauth_redirect_uri,
        tenant=settings.microsoft_oauth_tenant,
    )


def _build_oauth_adapters(settings: Settings) -> dict[str, RefreshableCredentialAdapter]:
    adapters: dict[str, RefreshableCredentialAdapter] = {}
    if settings.gmail_oauth_is_configured:
        secret = settings.gmail_oauth_client_secret
        if secret is None or settings.gmail_oauth_client_id is None:
            raise ServiceUnavailableError(_GMAIL_UNAVAILABLE)
        adapters["gmail"] = GoogleRefreshableCredentialAdapter(
            client_id=settings.gmail_oauth_client_id,
            client_secret=secret.get_secret_value(),
        )
    if settings.microsoft_oauth_is_configured:
        secret = settings.microsoft_oauth_client_secret
        if (
            secret is None
            or settings.microsoft_oauth_client_id is None
            or settings.microsoft_oauth_tenant is None
        ):
            raise ServiceUnavailableError(_MICROSOFT_UNAVAILABLE)
        adapters["microsoft_graph"] = MicrosoftRefreshableCredentialAdapter(
            client_id=settings.microsoft_oauth_client_id,
            client_secret=secret.get_secret_value(),
            tenant=settings.microsoft_oauth_tenant,
        )
    if not adapters:
        raise ServiceUnavailableError(_GMAIL_UNAVAILABLE)
    return adapters


def get_shared_oauth_resolver(settings: Settings) -> OAuthCommunicationCredentialResolver:
    """Return a process-wide OAuth resolver bound to the configured store."""
    global _oauth_resolver
    store = get_shared_credential_store(settings)
    with _lock:
        if _oauth_resolver is None:
            adapters = _build_oauth_adapters(settings)
            _oauth_resolver = OAuthCommunicationCredentialResolver(store, adapters)
        return _oauth_resolver


def build_runtime_communication_credential_resolver(
    settings: Settings,
) -> CommunicationCredentialResolver:
    """Compose environment plus OAuth resolvers for the current process.

    Unconfigured environments keep the environment resolver. Production OAuth
    uses the durable cloud store when it is configured.
    """
    environment = EnvironmentCommunicationCredentialResolver()
    if not mailbox_oauth_store_available(settings):
        return environment
    return CompositeCommunicationCredentialResolver(
        oauth_resolver=get_shared_oauth_resolver(settings),
        environment_resolver=environment,
    )


def require_shared_oauth_store(settings: Settings) -> CommunicationCredentialStore:
    """Return the configured store when mailbox OAuth connect is available."""
    if not mailbox_oauth_store_available(settings):
        raise ServiceUnavailableError(_GMAIL_UNAVAILABLE)
    return get_shared_credential_store(settings)
