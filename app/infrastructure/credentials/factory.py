"""Construct the configured CommunicationCredentialStore.

Mailbox OAuth storage is independent of AI_PROVIDER. Tests inject cloud
clients so default cloud identity constructors are not used.

Durable cloud backends require PostgreSQL advisory-lock coordination. The
memory backend keeps in-process behavior and does not use PostgreSQL.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, ServiceUnavailableError
from app.domain.interfaces.communication_credential_store import CommunicationCredentialStore
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.mutation import CredentialMutationCoordinator

_MEMORY_FORBIDDEN = "In-memory credential store is not allowed when APP_ENV=production."
_AZURE_INCOMPLETE = "CREDENTIAL_STORE_BACKEND=azure_key_vault requires AZURE_KEY_VAULT_URL."
_AWS_INCOMPLETE = (
    "CREDENTIAL_STORE_BACKEND=aws_secrets_manager requires AWS_SECRETS_MANAGER_REGION."
)
_UNKNOWN_BACKEND = "CREDENTIAL_STORE_BACKEND is not a supported credential store."
_COORDINATOR_REQUIRED = "Durable cloud credential stores require PostgreSQL mutation coordination."
_POSTGRES_SCHEME = "postgresql+psycopg"


def resolved_credential_store_backend(settings: Settings) -> str:
    """Return the effective backend name, defaulting unset values to memory."""
    backend = settings.credential_store_backend
    if backend is None:
        return "memory"
    return backend


def build_communication_credential_store(
    settings: Settings,
    *,
    memory_store: InMemoryCommunicationCredentialStore | None = None,
    azure_secret_client: Any | None = None,
    aws_client: Any | None = None,
    mutation_coordinator: CredentialMutationCoordinator | None = None,
) -> CommunicationCredentialStore:
    """Build the store selected by Settings. Production never returns memory."""
    backend = resolved_credential_store_backend(settings)
    if backend == "memory":
        if settings.app_env == "production":
            raise ConfigurationError(_MEMORY_FORBIDDEN)
        return memory_store if memory_store is not None else InMemoryCommunicationCredentialStore()
    if backend == "azure_key_vault":
        vault_url = settings.azure_key_vault_url
        if not vault_url:
            raise ConfigurationError(_AZURE_INCOMPLETE)
        from app.infrastructure.credentials.azure_key_vault import (
            AzureKeyVaultCommunicationCredentialStore,
        )

        return AzureKeyVaultCommunicationCredentialStore(
            vault_url,
            secret_client=azure_secret_client,
            mutation_coordinator=_require_cloud_mutation_coordinator(
                settings,
                mutation_coordinator,
            ),
        )
    if backend == "aws_secrets_manager":
        region = settings.aws_secrets_manager_region
        if not region:
            raise ConfigurationError(_AWS_INCOMPLETE)
        from app.infrastructure.credentials.aws_secrets_manager import (
            AwsSecretsManagerCommunicationCredentialStore,
        )

        return AwsSecretsManagerCommunicationCredentialStore(
            region,
            namespace=settings.aws_secrets_manager_namespace,
            client=aws_client,
            mutation_coordinator=_require_cloud_mutation_coordinator(
                settings,
                mutation_coordinator,
            ),
        )
    raise ConfigurationError(_UNKNOWN_BACKEND)


def require_durable_oauth_store(settings: Settings) -> None:
    """Fail closed when production OAuth would otherwise use process memory."""
    if settings.app_env != "production":
        return
    backend = resolved_credential_store_backend(settings)
    if backend == "memory":
        raise ServiceUnavailableError(_MEMORY_FORBIDDEN)


def _is_postgresql_url(database_url: str | None) -> bool:
    if not database_url:
        return False
    return urlparse(database_url).scheme.lower() == _POSTGRES_SCHEME


def _require_cloud_mutation_coordinator(
    settings: Settings,
    injected: CredentialMutationCoordinator | None,
) -> CredentialMutationCoordinator:
    if injected is not None:
        return injected
    if not _is_postgresql_url(settings.database_url):
        raise ConfigurationError(_COORDINATOR_REQUIRED)
    database_url = settings.database_url
    if database_url is None:
        raise ConfigurationError(_COORDINATOR_REQUIRED)
    try:
        from app.infrastructure.storage.credential_mutation import (
            PostgresCredentialMutationCoordinator,
        )
        from app.infrastructure.storage.runtime import get_persistence_session_factory

        factory = get_persistence_session_factory(database_url)
        return PostgresCredentialMutationCoordinator(factory)
    except ConfigurationError:
        raise
    except Exception:
        raise ServiceUnavailableError(_COORDINATOR_REQUIRED) from None
