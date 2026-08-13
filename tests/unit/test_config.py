"""Unit tests for application configuration."""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings

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
    monkeypatch.setenv("APP_ENV", "PRODUCTION")
    settings = Settings(_env_file=None)
    assert settings.app_env == "production"


def test_ai_provider_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI_PROVIDER values should be normalized to lowercase."""
    monkeypatch.setenv("AI_PROVIDER", "MOCK")
    settings = Settings(_env_file=None)
    assert settings.ai_provider == "mock"


def test_mock_provider_does_not_require_foundry_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_PROVIDER=mock must work without Foundry configuration."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_MODEL_DEPLOYMENT", raising=False)

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "mock"
    assert settings.foundry_project_endpoint is None
    assert settings.foundry_model_deployment is None


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
