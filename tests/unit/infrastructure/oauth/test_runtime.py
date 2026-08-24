"""Runtime mailbox OAuth composition tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.credentials.composite import CompositeCommunicationCredentialResolver
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.infrastructure.oauth.runtime import (
    build_runtime_communication_credential_resolver,
    get_shared_memory_credential_store,
    gmail_oauth_connect_available,
    mailbox_oauth_store_available,
    microsoft_oauth_connect_available,
    require_shared_oauth_store,
    reset_shared_memory_credential_store,
)

_GMAIL_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/gmail"
_MICROSOFT_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/microsoft_graph"


def _dev_gmail_settings() -> Settings:
    return Settings(
        _env_file=None,
        gmail_oauth_client_id="test-client-id.apps.googleusercontent.com",
        gmail_oauth_client_secret="dev-secret",
        gmail_oauth_redirect_uri=_GMAIL_REDIRECT,
        app_env="development",
    )


def _dev_microsoft_settings() -> Settings:
    return Settings(
        _env_file=None,
        microsoft_oauth_client_id="11111111-1111-1111-1111-111111111111",
        microsoft_oauth_client_secret="dev-ms-secret",
        microsoft_oauth_redirect_uri=_MICROSOFT_REDIRECT,
        microsoft_oauth_tenant="consumers",
        app_env="development",
    )


def test_shared_memory_store_is_process_wide() -> None:
    reset_shared_memory_credential_store()
    first = get_shared_memory_credential_store()
    second = get_shared_memory_credential_store()
    assert first is second
    reset_shared_memory_credential_store()
    third = get_shared_memory_credential_store()
    assert third is not first
    reset_shared_memory_credential_store()


def test_runtime_resolver_is_composite_when_gmail_oauth_enabled() -> None:
    reset_shared_memory_credential_store()
    resolver = build_runtime_communication_credential_resolver(_dev_gmail_settings())
    assert isinstance(resolver, CompositeCommunicationCredentialResolver)
    reset_shared_memory_credential_store()


def test_runtime_resolver_is_composite_when_microsoft_oauth_enabled() -> None:
    reset_shared_memory_credential_store()
    resolver = build_runtime_communication_credential_resolver(_dev_microsoft_settings())
    assert isinstance(resolver, CompositeCommunicationCredentialResolver)
    reset_shared_memory_credential_store()


def test_runtime_resolver_stays_environment_without_mailbox_oauth() -> None:
    settings = Settings(_env_file=None, app_env="development")
    resolver = build_runtime_communication_credential_resolver(settings)
    assert isinstance(resolver, EnvironmentCommunicationCredentialResolver)


def test_production_oauth_without_durable_store_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            auth_mode="oidc",
            oidc_issuer="https://example.invalid/",
            oidc_audience="eci-api",
            oidc_jwks_url="https://example.invalid/.well-known/jwks.json",
            database_url="postgresql+psycopg://eci:eci@localhost:5432/eci",
            gmail_oauth_client_id="test-client-id.apps.googleusercontent.com",
            gmail_oauth_client_secret="prod-secret",
            gmail_oauth_redirect_uri=_GMAIL_REDIRECT,
            microsoft_oauth_client_id="11111111-1111-1111-1111-111111111111",
            microsoft_oauth_client_secret="prod-ms-secret",
            microsoft_oauth_redirect_uri=_MICROSOFT_REDIRECT,
            microsoft_oauth_tenant="consumers",
        )


def test_production_memory_backend_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            auth_mode="oidc",
            oidc_issuer="https://example.invalid/",
            oidc_audience="eci-api",
            oidc_jwks_url="https://example.invalid/.well-known/jwks.json",
            database_url="postgresql+psycopg://eci:eci@localhost:5432/eci",
            credential_store_backend="memory",
        )


def test_production_azure_store_enables_oauth_connect() -> None:
    reset_shared_memory_credential_store()
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_mode="oidc",
        oidc_issuer="https://example.invalid/",
        oidc_audience="eci-api",
        oidc_jwks_url="https://example.invalid/.well-known/jwks.json",
        database_url="postgresql+psycopg://eci:eci@localhost:5432/eci",
        gmail_oauth_client_id="test-client-id.apps.googleusercontent.com",
        gmail_oauth_client_secret="prod-secret",
        gmail_oauth_redirect_uri=_GMAIL_REDIRECT,
        microsoft_oauth_client_id="11111111-1111-1111-1111-111111111111",
        microsoft_oauth_client_secret="prod-ms-secret",
        microsoft_oauth_redirect_uri=_MICROSOFT_REDIRECT,
        microsoft_oauth_tenant="consumers",
        credential_store_backend="azure_key_vault",
        azure_key_vault_url="https://eci-dev.vault.azure.net",
    )
    assert gmail_oauth_connect_available(settings) is True
    assert microsoft_oauth_connect_available(settings) is True
    assert mailbox_oauth_store_available(settings) is True
    from app.infrastructure.credentials.azure_key_vault import (
        AzureKeyVaultCommunicationCredentialStore,
    )
    from tests.unit.infrastructure.credentials.cloud_fakes import (
        FakeAzureSecretClient,
        RecordingCredentialMutationCoordinator,
    )

    fake = FakeAzureSecretClient()

    def _build(settings_obj, **_kwargs):  # type: ignore[no-untyped-def]
        return AzureKeyVaultCommunicationCredentialStore(
            settings_obj.azure_key_vault_url,
            secret_client=fake,
            mutation_coordinator=RecordingCredentialMutationCoordinator(),
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.infrastructure.oauth.runtime.build_communication_credential_store",
        _build,
    )
    try:
        store = require_shared_oauth_store(settings)
        assert isinstance(store, AzureKeyVaultCommunicationCredentialStore)
        resolver = build_runtime_communication_credential_resolver(settings)
        assert isinstance(resolver, CompositeCommunicationCredentialResolver)
    finally:
        monkeypatch.undo()
        reset_shared_memory_credential_store()


def test_production_aws_store_enables_oauth_connect() -> None:
    reset_shared_memory_credential_store()
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_mode="oidc",
        oidc_issuer="https://example.invalid/",
        oidc_audience="eci-api",
        oidc_jwks_url="https://example.invalid/.well-known/jwks.json",
        database_url="postgresql+psycopg://eci:eci@localhost:5432/eci",
        gmail_oauth_client_id="test-client-id.apps.googleusercontent.com",
        gmail_oauth_client_secret="prod-secret",
        gmail_oauth_redirect_uri=_GMAIL_REDIRECT,
        microsoft_oauth_client_id="11111111-1111-1111-1111-111111111111",
        microsoft_oauth_client_secret="prod-ms-secret",
        microsoft_oauth_redirect_uri=_MICROSOFT_REDIRECT,
        microsoft_oauth_tenant="consumers",
        credential_store_backend="aws_secrets_manager",
        aws_secrets_manager_region="eu-west-1",
    )
    assert gmail_oauth_connect_available(settings) is True
    assert microsoft_oauth_connect_available(settings) is True
    from app.infrastructure.credentials.aws_secrets_manager import (
        AwsSecretsManagerCommunicationCredentialStore,
    )
    from tests.unit.infrastructure.credentials.cloud_fakes import (
        FakeSecretsManagerClient,
        RecordingCredentialMutationCoordinator,
    )

    fake = FakeSecretsManagerClient()

    def _build(settings_obj, **_kwargs):  # type: ignore[no-untyped-def]
        return AwsSecretsManagerCommunicationCredentialStore(
            settings_obj.aws_secrets_manager_region,
            namespace=settings_obj.aws_secrets_manager_namespace,
            client=fake,
            mutation_coordinator=RecordingCredentialMutationCoordinator(),
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.infrastructure.oauth.runtime.build_communication_credential_store",
        _build,
    )
    try:
        store = require_shared_oauth_store(settings)
        assert isinstance(store, AwsSecretsManagerCommunicationCredentialStore)
        resolver = build_runtime_communication_credential_resolver(settings)
        assert isinstance(resolver, CompositeCommunicationCredentialResolver)
    finally:
        monkeypatch.undo()
        reset_shared_memory_credential_store()


def test_production_without_oauth_keeps_environment_resolver() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_mode="oidc",
        oidc_issuer="https://example.invalid/",
        oidc_audience="eci-api",
        oidc_jwks_url="https://example.invalid/.well-known/jwks.json",
        database_url="postgresql+psycopg://eci:eci@localhost:5432/eci",
    )
    assert gmail_oauth_connect_available(settings) is False
    assert mailbox_oauth_store_available(settings) is False
    resolver = build_runtime_communication_credential_resolver(settings)
    assert isinstance(resolver, EnvironmentCommunicationCredentialResolver)
