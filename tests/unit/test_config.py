"""Unit tests for application configuration."""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings

_TEST_POSTGRES_URL = "postgresql+psycopg://eci_test:test@localhost:5432/eci_test"
_SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "LOG_LEVEL",
    "API_V1_PREFIX",
    "AI_PROVIDER",
    "FOUNDRY_PROJECT_ENDPOINT",
    "FOUNDRY_MODEL_DEPLOYMENT",
    "BEDROCK_REGION",
    "BEDROCK_MODEL_ID",
    "AUTH_MODE",
    "OIDC_ISSUER",
    "OIDC_AUDIENCE",
    "OIDC_JWKS_URL",
    "OIDC_REQUIRED_PERMISSION",
    "DATABASE_URL",
    "OAUTH_AUTHORIZATION_SESSION_TTL_SECONDS",
    "GMAIL_OAUTH_CLIENT_ID",
    "GMAIL_OAUTH_CLIENT_SECRET",
    "GMAIL_OAUTH_REDIRECT_URI",
    "MICROSOFT_OAUTH_CLIENT_ID",
    "MICROSOFT_OAUTH_CLIENT_SECRET",
    "MICROSOFT_OAUTH_REDIRECT_URI",
    "MICROSOFT_OAUTH_TENANT",
    "CREDENTIAL_STORE_BACKEND",
    "AZURE_KEY_VAULT_URL",
    "AWS_SECRETS_MANAGER_REGION",
    "AWS_SECRETS_MANAGER_NAMESPACE",
    "CORS_ALLOWED_ORIGINS",
    "FRONTEND_OAUTH_RETURN_URL",
)


@pytest.fixture
def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove ECI Platform settings variables so defaults can be asserted."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


def test_settings_defaults(clear_settings_env: None) -> None:
    """Settings should expose sensible development defaults."""
    settings = Settings(_env_file=None)

    assert settings.app_name == "Enterprise Communication Intelligence Platform"
    assert settings.app_version == "0.1.0"
    assert settings.app_env == "development"
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 8000
    assert settings.log_level == "INFO"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.ai_provider == "mock"
    assert settings.foundry_project_endpoint is None
    assert settings.foundry_model_deployment is None
    assert settings.bedrock_region is None
    assert settings.bedrock_model_id is None
    assert settings.auth_mode == "disabled"
    assert settings.oidc_issuer is None
    assert settings.oidc_audience is None
    assert settings.oidc_jwks_url is None
    assert settings.oidc_required_permission == "communications:analyze"
    assert settings.database_url is None
    assert settings.oauth_authorization_session_ttl_seconds == 600
    assert settings.gmail_oauth_client_id is None
    assert settings.gmail_oauth_client_secret is None
    assert settings.gmail_oauth_redirect_uri is None
    assert settings.gmail_oauth_is_configured is False
    assert settings.microsoft_oauth_client_id is None
    assert settings.microsoft_oauth_client_secret is None
    assert settings.microsoft_oauth_redirect_uri is None
    assert settings.microsoft_oauth_tenant is None
    assert settings.microsoft_oauth_is_configured is False
    assert settings.credential_store_backend is None
    assert settings.azure_key_vault_url is None
    assert settings.aws_secrets_manager_region is None
    assert settings.aws_secrets_manager_namespace == "eci/mailbox-oauth"
    assert settings.durable_oauth_store_is_configured is False
    assert settings.cors_allowed_origins == ""
    assert settings.cors_allow_origins == ()
    assert settings.frontend_oauth_return_url is None


def test_mailbox_credential_env_vars_are_ignored_by_settings(
    clear_settings_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mailbox secrets must not load into Settings or block ordinary startup."""
    token = "SUPER_SECRET_TEST_TOKEN_123"
    env_name = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_DEMO_ACCOUNT_ACCESS_TOKEN"
    monkeypatch.setenv(env_name, token)
    settings = Settings(_env_file=None)
    assert settings.ai_provider == "mock"
    dumped = settings.model_dump()
    blob = f"{dumped!s}{settings!r}{settings}"
    assert token not in blob
    assert env_name not in blob
    assert "credential" not in dumped


def test_get_settings_returns_cached_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_settings should cache the Settings instance."""
    monkeypatch.delenv("APP_NAME", raising=False)
    first = get_settings()
    second = get_settings()
    assert first is second


@pytest.mark.parametrize("port", ["0", "65536", "-1", "not-a-port"])
def test_invalid_port_raises(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    """APP_PORT outside 1-65535 must fail validation."""
    monkeypatch.setenv("APP_PORT", port)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("app_env", ["dev", "prod", "local", "test"])
def test_invalid_app_env_raises(monkeypatch: pytest.MonkeyPatch, app_env: str) -> None:
    """APP_ENV must be one of development, staging, or production."""
    monkeypatch.setenv("APP_ENV", app_env)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("log_level", ["TRACE", "verbose", "fatal"])
def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch, log_level: str) -> None:
    """LOG_LEVEL must be a supported standard logging level."""
    monkeypatch.setenv("LOG_LEVEL", log_level)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_log_level_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """LOG_LEVEL values should be normalized to uppercase."""
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = Settings(_env_file=None)
    assert settings.log_level == "DEBUG"


def test_app_env_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_ENV values should be normalized to lowercase."""
    monkeypatch.setenv("APP_ENV", "STAGING")
    settings = Settings(_env_file=None)
    assert settings.app_env == "staging"


def test_ai_provider_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI_PROVIDER values should be normalized to lowercase."""
    monkeypatch.setenv("AI_PROVIDER", "MOCK")
    settings = Settings(_env_file=None)
    assert settings.ai_provider == "mock"


def test_mock_provider_does_not_require_foundry_or_bedrock_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_PROVIDER=mock must work without Foundry or Bedrock configuration."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_MODEL_DEPLOYMENT", raising=False)
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "mock"
    assert settings.foundry_project_endpoint is None
    assert settings.foundry_model_deployment is None
    assert settings.bedrock_region is None
    assert settings.bedrock_model_id is None


def test_microsoft_foundry_settings_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Foundry settings should load when the Microsoft Foundry provider is selected."""
    monkeypatch.setenv("AI_PROVIDER", "microsoft_foundry")
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev",
    )
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", "eci-gpt-54-mini")

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "microsoft_foundry"
    assert settings.foundry_project_endpoint == (
        "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev"
    )
    assert settings.foundry_model_deployment == "eci-gpt-54-mini"


def test_microsoft_foundry_requires_project_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FOUNDRY_PROJECT_ENDPOINT is required when AI_PROVIDER=microsoft_foundry."""
    monkeypatch.setenv("AI_PROVIDER", "microsoft_foundry")
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", "eci-gpt-54-mini")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_microsoft_foundry_requires_model_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FOUNDRY_MODEL_DEPLOYMENT is required when AI_PROVIDER=microsoft_foundry."""
    monkeypatch.setenv("AI_PROVIDER", "microsoft_foundry")
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev",
    )
    monkeypatch.delenv("FOUNDRY_MODEL_DEPLOYMENT", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_foundry_settings_are_treated_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank Foundry values should not satisfy microsoft_foundry configuration."""
    monkeypatch.setenv("AI_PROVIDER", "microsoft_foundry")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "   ")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", "eci-gpt-54-mini")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_foundry_endpoint_must_be_https(monkeypatch: pytest.MonkeyPatch) -> None:
    """FOUNDRY_PROJECT_ENDPOINT must use https when provided."""
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "http://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev",
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_microsoft_foundry_does_not_require_bedrock_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_PROVIDER=microsoft_foundry must work without Bedrock configuration."""
    monkeypatch.setenv("AI_PROVIDER", "microsoft_foundry")
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev",
    )
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", "eci-gpt-54-mini")
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "microsoft_foundry"
    assert settings.bedrock_region is None
    assert settings.bedrock_model_id is None


def test_amazon_bedrock_settings_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bedrock settings should load when the Amazon Bedrock provider is selected."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.setenv("BEDROCK_REGION", "eu-south-2")
    monkeypatch.setenv(
        "BEDROCK_MODEL_ID",
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    )
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_MODEL_DEPLOYMENT", raising=False)

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "amazon_bedrock"
    assert settings.bedrock_region == "eu-south-2"
    assert settings.bedrock_model_id == "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert settings.foundry_project_endpoint is None
    assert settings.foundry_model_deployment is None


def test_amazon_bedrock_region_and_model_id_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bedrock region and model ID values should be stripped of surrounding whitespace."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.setenv("BEDROCK_REGION", "  eu-south-2  ")
    monkeypatch.setenv(
        "BEDROCK_MODEL_ID",
        "  eu.anthropic.claude-haiku-4-5-20251001-v1:0  ",
    )

    settings = Settings(_env_file=None)

    assert settings.bedrock_region == "eu-south-2"
    assert settings.bedrock_model_id == "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_blank_bedrock_settings_are_treated_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank Bedrock values should remain unset when another provider is selected."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("BEDROCK_REGION", "   ")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "   ")

    settings = Settings(_env_file=None)

    assert settings.bedrock_region is None
    assert settings.bedrock_model_id is None


def test_amazon_bedrock_requires_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """BEDROCK_REGION is required when AI_PROVIDER=amazon_bedrock."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.setenv(
        "BEDROCK_MODEL_ID",
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_amazon_bedrock_requires_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """BEDROCK_MODEL_ID is required when AI_PROVIDER=amazon_bedrock."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.setenv("BEDROCK_REGION", "eu-south-2")
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_amazon_bedrock_requires_region_and_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both Bedrock settings are required when AI_PROVIDER=amazon_bedrock."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "BEDROCK_REGION" in str(exc_info.value)
    assert "BEDROCK_MODEL_ID" in str(exc_info.value)


def test_blank_bedrock_settings_do_not_satisfy_amazon_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank Bedrock values should not satisfy amazon_bedrock configuration."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.setenv("BEDROCK_REGION", "   ")
    monkeypatch.setenv(
        "BEDROCK_MODEL_ID",
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_do_not_include_aws_credential_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AWS credentials and profile names must remain outside application Settings."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    settings = Settings(_env_file=None)
    field_names = set(type(settings).model_fields)

    assert "aws_access_key_id" not in field_names
    assert "aws_secret_access_key" not in field_names
    assert "aws_session_token" not in field_names
    assert "aws_profile" not in field_names


def _complete_oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://example.invalid/")
    monkeypatch.setenv("OIDC_AUDIENCE", "eci-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://example.invalid/.well-known/jwks.json")


def test_development_auth_disabled_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development may start with AUTH_MODE=disabled."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    settings = Settings(_env_file=None)
    assert settings.auth_mode == "disabled"


def test_oidc_mode_with_complete_configuration_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUTH_MODE=oidc is valid when issuer, audience, and JWKS URL are set."""
    _complete_oidc_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.auth_mode == "oidc"
    assert settings.oidc_issuer == "https://example.invalid/"
    assert settings.oidc_audience == "eci-api"
    assert settings.oidc_jwks_url == "https://example.invalid/.well-known/jwks.json"
    assert settings.oidc_required_permission == "communications:analyze"


def test_oidc_mode_missing_issuer_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """OIDC_ISSUER is required when AUTH_MODE=oidc."""
    _complete_oidc_env(monkeypatch)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_oidc_mode_missing_audience_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """OIDC_AUDIENCE is required when AUTH_MODE=oidc."""
    _complete_oidc_env(monkeypatch)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_oidc_mode_missing_jwks_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """OIDC_JWKS_URL is required when AUTH_MODE=oidc."""
    _complete_oidc_env(monkeypatch)
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_with_auth_disabled_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production must not start with AUTH_MODE=disabled."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_with_incomplete_oidc_config_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production OIDC mode still requires issuer, audience, and JWKS URL."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_oidc_with_complete_configuration_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APP_ENV=production is valid when AUTH_MODE=oidc and OIDC settings are complete."""
    monkeypatch.setenv("APP_ENV", "PRODUCTION")
    _complete_oidc_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    settings = Settings(_env_file=None)
    assert settings.app_env == "production"
    assert settings.auth_mode == "oidc"
    assert settings.database_url == _TEST_POSTGRES_URL


def test_blank_oidc_settings_do_not_satisfy_oidc_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank OIDC values should not satisfy AUTH_MODE=oidc."""
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "   ")
    monkeypatch.setenv("OIDC_AUDIENCE", "eci-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_oidc_issuer_and_jwks_url_must_be_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OIDC issuer and JWKS URL must use https when provided."""
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "http://example.invalid/")
    monkeypatch.setenv("OIDC_AUDIENCE", "eci-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("OIDC_ISSUER", "https://example.invalid/")
    monkeypatch.setenv("OIDC_JWKS_URL", "http://example.invalid/.well-known/jwks.json")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_auth_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUTH_MODE must be disabled or oidc."""
    monkeypatch.setenv("AUTH_MODE", "entra")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_development_may_omit_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development startup does not require DATABASE_URL and creates no DB file."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.database_url is None


def test_development_explicit_sqlite_url_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit SQLite URL is allowed outside production."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    settings = Settings(_env_file=None)
    assert settings.database_url == "sqlite+pysqlite:///:memory:"


def test_production_missing_database_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production must not start without DATABASE_URL."""
    _complete_oidc_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "DATABASE_URL" in str(exc_info.value)


def test_production_sqlite_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production must reject SQLite database URLs."""
    _complete_oidc_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "DATABASE_URL" in str(exc_info.value)


def test_production_postgres_psycopg_url_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production accepts a postgresql+psycopg URL without connecting."""
    _complete_oidc_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    settings = Settings(_env_file=None)
    assert settings.database_url == _TEST_POSTGRES_URL


def test_unsupported_database_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsupported schemes are rejected in any environment."""
    monkeypatch.setenv("DATABASE_URL", "mysql://eci_test:test@localhost:3306/eci_test")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("DATABASE_URL", "postgresql://eci_test:test@localhost:5432/eci_test")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_malformed_database_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed DATABASE_URL values are rejected without connecting."""
    monkeypatch.setenv("DATABASE_URL", "not-a-url")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_database_url_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank DATABASE_URL should be equivalent to omitting it."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "   ")
    settings = Settings(_env_file=None)
    assert settings.database_url is None


def test_database_url_validation_error_does_not_include_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rejected DATABASE_URL values must not echo credentials in ValidationError."""
    secret = "eci-db-password-sentinel"
    monkeypatch.setenv("DATABASE_URL", f"mysql://eci:{secret}@localhost:3306/eci")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "DATABASE_URL" in str(exc_info.value)
    assert secret not in str(exc_info.value)


def test_oauth_authorization_session_ttl_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mailbox authorization session TTL is bounded and has no network dependency."""
    monkeypatch.setenv("OAUTH_AUTHORIZATION_SESSION_TTL_SECONDS", "60")
    settings = Settings(_env_file=None)
    assert settings.oauth_authorization_session_ttl_seconds == 60
    monkeypatch.setenv("OAUTH_AUTHORIZATION_SESSION_TTL_SECONDS", "1800")
    settings = Settings(_env_file=None)
    assert settings.oauth_authorization_session_ttl_seconds == 1800
    monkeypatch.setenv("OAUTH_AUTHORIZATION_SESSION_TTL_SECONDS", "59")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("OAUTH_AUTHORIZATION_SESSION_TTL_SECONDS", "1801")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("OAUTH_AUTHORIZATION_SESSION_TTL_SECONDS", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("OAUTH_AUTHORIZATION_SESSION_TTL_SECONDS", "not-an-int")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


_GMAIL_OAUTH_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/gmail"
_GMAIL_OAUTH_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_GMAIL_OAUTH_SECRET = "gmail-oauth-client-secret-sentinel"


def test_gmail_oauth_settings_are_optional(clear_settings_env: None) -> None:
    """Ordinary startup must not require Gmail OAuth configuration."""
    settings = Settings(_env_file=None)
    assert settings.gmail_oauth_is_configured is False
    assert settings.app_env == "development"


def test_gmail_oauth_settings_load_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """Complete Gmail OAuth settings load without becoming the production store."""
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_ID", f"  {_GMAIL_OAUTH_CLIENT_ID}  ")
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_SECRET", f"  {_GMAIL_OAUTH_SECRET}  ")
    monkeypatch.setenv("GMAIL_OAUTH_REDIRECT_URI", f"  {_GMAIL_OAUTH_REDIRECT}  ")
    settings = Settings(_env_file=None)
    assert settings.gmail_oauth_client_id == _GMAIL_OAUTH_CLIENT_ID
    assert settings.gmail_oauth_redirect_uri == _GMAIL_OAUTH_REDIRECT
    assert settings.gmail_oauth_is_configured is True
    assert settings.gmail_oauth_client_secret is not None
    assert settings.gmail_oauth_client_secret.get_secret_value() == _GMAIL_OAUTH_SECRET
    blob = f"{settings!r}{settings}{settings.model_dump()!s}"
    assert _GMAIL_OAUTH_SECRET not in blob
    assert "**********" in repr(settings.gmail_oauth_client_secret)


def test_gmail_oauth_partial_configuration_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A half-configured Gmail OAuth client must not start."""
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_ID", _GMAIL_OAUTH_CLIENT_ID)
    monkeypatch.delenv("GMAIL_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GMAIL_OAUTH_REDIRECT_URI", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_gmail_oauth_redirect_uri_must_be_absolute_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect URIs must be absolute http(s) URLs without fragments."""
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_ID", _GMAIL_OAUTH_CLIENT_ID)
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_SECRET", _GMAIL_OAUTH_SECRET)
    monkeypatch.setenv("GMAIL_OAUTH_REDIRECT_URI", "/oauth/callbacks/gmail")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv(
        "GMAIL_OAUTH_REDIRECT_URI",
        f"{_GMAIL_OAUTH_REDIRECT}#fragment",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_gmail_oauth_secret_is_hidden_in_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rejected Gmail OAuth configuration must not echo the client secret."""
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_ID", _GMAIL_OAUTH_CLIENT_ID)
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_SECRET", _GMAIL_OAUTH_SECRET)
    monkeypatch.setenv("GMAIL_OAUTH_REDIRECT_URI", "not-a-url")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert _GMAIL_OAUTH_SECRET not in str(exc_info.value)


def test_production_does_not_require_gmail_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production startup must not fail solely because Gmail OAuth is unset."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://example.invalid/")
    monkeypatch.setenv("OIDC_AUDIENCE", "eci-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    monkeypatch.delenv("GMAIL_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GMAIL_OAUTH_REDIRECT_URI", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == "production"
    assert settings.gmail_oauth_is_configured is False
    assert settings.microsoft_oauth_is_configured is False


_MICROSOFT_OAUTH_REDIRECT = "https://eci.example.invalid/api/v1/oauth/callbacks/microsoft_graph"
_MICROSOFT_OAUTH_CLIENT_ID = "11111111-1111-1111-1111-111111111111"
_MICROSOFT_OAUTH_SECRET = "microsoft-oauth-client-secret-sentinel"
_MICROSOFT_OAUTH_TENANT = "consumers"


def test_microsoft_oauth_settings_are_optional(clear_settings_env: None) -> None:
    """Ordinary startup must not require Microsoft OAuth configuration."""
    settings = Settings(_env_file=None)
    assert settings.microsoft_oauth_is_configured is False
    assert settings.app_env == "development"


def test_microsoft_oauth_settings_load_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """Complete Microsoft OAuth settings load without becoming the production store."""
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", f"  {_MICROSOFT_OAUTH_CLIENT_ID}  ")
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_SECRET", f"  {_MICROSOFT_OAUTH_SECRET}  ")
    monkeypatch.setenv("MICROSOFT_OAUTH_REDIRECT_URI", f"  {_MICROSOFT_OAUTH_REDIRECT}  ")
    monkeypatch.setenv("MICROSOFT_OAUTH_TENANT", "  Consumers  ")
    settings = Settings(_env_file=None)
    assert settings.microsoft_oauth_client_id == _MICROSOFT_OAUTH_CLIENT_ID
    assert settings.microsoft_oauth_redirect_uri == _MICROSOFT_OAUTH_REDIRECT
    assert settings.microsoft_oauth_tenant == _MICROSOFT_OAUTH_TENANT
    assert settings.microsoft_oauth_is_configured is True
    assert settings.microsoft_oauth_client_secret is not None
    assert settings.microsoft_oauth_client_secret.get_secret_value() == _MICROSOFT_OAUTH_SECRET
    blob = f"{settings!r}{settings}{settings.model_dump()!s}"
    assert _MICROSOFT_OAUTH_SECRET not in blob
    assert "**********" in repr(settings.microsoft_oauth_client_secret)


def test_microsoft_oauth_partial_configuration_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A half-configured Microsoft OAuth client must not start."""
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", _MICROSOFT_OAUTH_CLIENT_ID)
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_TENANT", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_microsoft_oauth_redirect_uri_must_be_absolute_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect URIs must be absolute http(s) URLs without fragments."""
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", _MICROSOFT_OAUTH_CLIENT_ID)
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_SECRET", _MICROSOFT_OAUTH_SECRET)
    monkeypatch.setenv("MICROSOFT_OAUTH_TENANT", _MICROSOFT_OAUTH_TENANT)
    monkeypatch.setenv(
        "MICROSOFT_OAUTH_REDIRECT_URI",
        "/oauth/callbacks/microsoft_graph",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv(
        "MICROSOFT_OAUTH_REDIRECT_URI",
        f"{_MICROSOFT_OAUTH_REDIRECT}#fragment",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_microsoft_oauth_tenant_rejects_authority_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant must be an alias or GUID, never a login host URL."""
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", _MICROSOFT_OAUTH_CLIENT_ID)
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_SECRET", _MICROSOFT_OAUTH_SECRET)
    monkeypatch.setenv("MICROSOFT_OAUTH_REDIRECT_URI", _MICROSOFT_OAUTH_REDIRECT)
    monkeypatch.setenv(
        "MICROSOFT_OAUTH_TENANT",
        "https://login.microsoftonline.com/consumers",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_microsoft_oauth_secret_is_hidden_in_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rejected Microsoft OAuth configuration must not echo the client secret."""
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", _MICROSOFT_OAUTH_CLIENT_ID)
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_SECRET", _MICROSOFT_OAUTH_SECRET)
    monkeypatch.setenv("MICROSOFT_OAUTH_TENANT", _MICROSOFT_OAUTH_TENANT)
    monkeypatch.setenv("MICROSOFT_OAUTH_REDIRECT_URI", "not-a-url")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert _MICROSOFT_OAUTH_SECRET not in str(exc_info.value)


def test_production_does_not_require_microsoft_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production startup must not fail solely because Microsoft OAuth is unset."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://example.invalid/")
    monkeypatch.setenv("OIDC_AUDIENCE", "eci-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_TENANT", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == "production"
    assert settings.microsoft_oauth_is_configured is False
    assert settings.durable_oauth_store_is_configured is False


def test_foundry_ai_provider_does_not_select_key_vault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mailbox credential storage is independent of AI_PROVIDER."""
    monkeypatch.setenv("AI_PROVIDER", "microsoft_foundry")
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://example.invalid/api/projects/eci",
    )
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", "eci-gpt")
    settings = Settings(_env_file=None)
    assert settings.credential_store_backend is None
    assert settings.durable_oauth_store_is_configured is False


def test_partial_azure_store_configuration_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "azure_key_vault")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://eci-dev.vault.azure.net")
    monkeypatch.delenv("CREDENTIAL_STORE_BACKEND", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_complete_azure_store_configuration_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "azure_key_vault")
    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://eci-dev.vault.azure.net/")
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    settings = Settings(_env_file=None)
    assert settings.credential_store_backend == "azure_key_vault"
    assert settings.azure_key_vault_url == "https://eci-dev.vault.azure.net"
    assert settings.durable_oauth_store_is_configured is True


def test_complete_aws_store_configuration_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "aws_secrets_manager")
    monkeypatch.setenv("AWS_SECRETS_MANAGER_REGION", "eu-west-1")
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    settings = Settings(_env_file=None)
    assert settings.credential_store_backend == "aws_secrets_manager"
    assert settings.aws_secrets_manager_region == "eu-west-1"
    assert settings.aws_secrets_manager_namespace == "eci/mailbox-oauth"
    assert settings.durable_oauth_store_is_configured is True


def test_azure_store_with_sqlite_database_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "azure_key_vault")
    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://eci-dev.vault.azure.net")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./eci.db")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_oauth_requires_durable_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    _complete_oidc_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_ID", "id.apps.googleusercontent.com")
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv(
        "GMAIL_OAUTH_REDIRECT_URI",
        "https://eci.example.invalid/api/v1/oauth/callbacks/gmail",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_memory_backend_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    _complete_oidc_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "memory")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_oauth_with_azure_store_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    _complete_oidc_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_ID", "id.apps.googleusercontent.com")
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv(
        "GMAIL_OAUTH_REDIRECT_URI",
        "https://eci.example.invalid/api/v1/oauth/callbacks/gmail",
    )
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "azure_key_vault")
    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://eci-dev.vault.azure.net")
    settings = Settings(_env_file=None)
    assert settings.durable_oauth_store_is_configured is True
    assert settings.gmail_oauth_is_configured is True


def test_cors_allowed_origins_default_is_empty(clear_settings_env: None) -> None:
    """An unset CORS allowlist keeps the API backend-only."""
    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == ""
    assert settings.cors_allow_origins == ()


def test_cors_allowed_origins_parses_comma_separated_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173, https://eci.example.invalid",
    )
    settings = Settings(_env_file=None)
    assert settings.cors_allow_origins == (
        "http://localhost:5173",
        "https://eci.example.invalid",
    )


def test_cors_allowed_origins_blank_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "  ")
    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == ""
    assert settings.cors_allow_origins == ()


def test_cors_allowed_origins_rejects_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_allowed_origins_rejects_wildcard_in_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,*")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_allowed_origins_rejects_malformed_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "localhost:5173")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_allowed_origins_rejects_origin_with_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173/app")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_frontend_oauth_return_url_default_is_unset(clear_settings_env: None) -> None:
    settings = Settings(_env_file=None)
    assert settings.frontend_oauth_return_url is None


def test_frontend_oauth_return_url_blank_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTEND_OAUTH_RETURN_URL", "  ")
    settings = Settings(_env_file=None)
    assert settings.frontend_oauth_return_url is None


def test_frontend_oauth_return_url_accepts_localhost_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRONTEND_OAUTH_RETURN_URL", "http://localhost:5173")
    settings = Settings(_env_file=None)
    assert settings.frontend_oauth_return_url == "http://localhost:5173"


def test_frontend_oauth_return_url_accepts_https_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRONTEND_OAUTH_RETURN_URL", "https://eci.example.invalid/oauth")
    settings = Settings(_env_file=None)
    assert settings.frontend_oauth_return_url == "https://eci.example.invalid/oauth"


@pytest.mark.parametrize(
    "value",
    [
        "localhost:5173",
        "http://example.com",
        "https://user:pass@eci.example.invalid",
        "https://eci.example.invalid?next=1",
        "https://eci.example.invalid#frag",
        "javascript:alert(1)",
        "//evil.example",
    ],
)
def test_frontend_oauth_return_url_rejects_unsafe_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("FRONTEND_OAUTH_RETURN_URL", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_frontend_oauth_return_url_production_requires_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://example.invalid/")
    monkeypatch.setenv("OIDC_AUDIENCE", "eci-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", _TEST_POSTGRES_URL)
    monkeypatch.setenv("FRONTEND_OAUTH_RETURN_URL", "http://localhost:5173")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
