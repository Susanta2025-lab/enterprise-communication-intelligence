"""Runtime credential-store backend selection tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, ServiceUnavailableError
from app.infrastructure.credentials.aws_secrets_manager import (
    AwsSecretsManagerCommunicationCredentialStore,
)
from app.infrastructure.credentials.azure_key_vault import (
    AzureKeyVaultCommunicationCredentialStore,
)
from app.infrastructure.credentials.factory import (
    build_communication_credential_store,
    resolved_credential_store_backend,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from tests.unit.infrastructure.credentials.cloud_fakes import (
    FakeAzureSecretClient,
    FakeSecretsManagerClient,
    RecordingCredentialMutationCoordinator,
)

_VAULT = "https://eci-dev.vault.azure.net"
_POSTGRES = "postgresql+psycopg://eci:eci@localhost:5432/eci"


def test_development_defaults_to_memory() -> None:
    settings = Settings(_env_file=None, app_env="development")
    assert resolved_credential_store_backend(settings) == "memory"
    store = build_communication_credential_store(settings)
    assert isinstance(store, InMemoryCommunicationCredentialStore)


def test_explicit_memory_store_is_reused() -> None:
    settings = Settings(_env_file=None, credential_store_backend="memory")
    memory = InMemoryCommunicationCredentialStore()
    store = build_communication_credential_store(settings, memory_store=memory)
    assert store is memory


def test_azure_backend_uses_injected_client() -> None:
    settings = Settings(
        _env_file=None,
        credential_store_backend="azure_key_vault",
        azure_key_vault_url=_VAULT,
        database_url=_POSTGRES,
    )
    client = FakeAzureSecretClient()
    coordinator = RecordingCredentialMutationCoordinator()
    store = build_communication_credential_store(
        settings,
        azure_secret_client=client,
        mutation_coordinator=coordinator,
    )
    assert isinstance(store, AzureKeyVaultCommunicationCredentialStore)


def test_aws_backend_uses_injected_client() -> None:
    settings = Settings(
        _env_file=None,
        credential_store_backend="aws_secrets_manager",
        aws_secrets_manager_region="eu-west-1",
        database_url=_POSTGRES,
    )
    store = build_communication_credential_store(
        settings,
        aws_client=FakeSecretsManagerClient(),
        mutation_coordinator=RecordingCredentialMutationCoordinator(),
    )
    assert isinstance(store, AwsSecretsManagerCommunicationCredentialStore)


def test_production_memory_backend_is_rejected_by_factory() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_mode="oidc",
        oidc_issuer="https://example.invalid/",
        oidc_audience="eci-api",
        oidc_jwks_url="https://example.invalid/.well-known/jwks.json",
        database_url=_POSTGRES,
        credential_store_backend="azure_key_vault",
        azure_key_vault_url=_VAULT,
    )
    object.__setattr__(settings, "credential_store_backend", "memory")
    with pytest.raises(ConfigurationError):
        build_communication_credential_store(settings)


def test_cloud_store_settings_require_postgresql() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            credential_store_backend="azure_key_vault",
            azure_key_vault_url=_VAULT,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            credential_store_backend="azure_key_vault",
            azure_key_vault_url=_VAULT,
            database_url="sqlite:///./eci.db",
        )


def test_cloud_store_factory_fails_closed_without_postgres_coordination() -> None:
    settings = Settings(
        _env_file=None,
        credential_store_backend="azure_key_vault",
        azure_key_vault_url=_VAULT,
        database_url=_POSTGRES,
    )
    object.__setattr__(settings, "database_url", "sqlite:///./eci.db")
    with pytest.raises(ConfigurationError):
        build_communication_credential_store(
            settings,
            azure_secret_client=FakeAzureSecretClient(),
        )


def test_cloud_store_factory_fails_closed_when_coordinator_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        credential_store_backend="aws_secrets_manager",
        aws_secrets_manager_region="eu-west-1",
        database_url=_POSTGRES,
    )

    def _boom(_url: str) -> None:
        raise RuntimeError("engine failed")

    monkeypatch.setattr(
        "app.infrastructure.storage.runtime.get_persistence_session_factory",
        _boom,
    )
    with pytest.raises(ServiceUnavailableError):
        build_communication_credential_store(
            settings,
            aws_client=FakeSecretsManagerClient(),
        )


def test_memory_backend_does_not_require_coordinator() -> None:
    settings = Settings(_env_file=None, credential_store_backend="memory")
    store = build_communication_credential_store(settings)
    assert isinstance(store, InMemoryCommunicationCredentialStore)
