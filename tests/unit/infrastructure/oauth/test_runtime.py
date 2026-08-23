"""Runtime mailbox OAuth composition tests."""

from __future__ import annotations

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


def test_production_does_not_enable_memory_oauth_store() -> None:
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
    )
    assert settings.gmail_oauth_is_configured is True
    assert settings.microsoft_oauth_is_configured is True
    assert gmail_oauth_connect_available(settings) is False
    assert microsoft_oauth_connect_available(settings) is False
    assert mailbox_oauth_store_available(settings) is False
    resolver = build_runtime_communication_credential_resolver(settings)
    assert isinstance(resolver, EnvironmentCommunicationCredentialResolver)
