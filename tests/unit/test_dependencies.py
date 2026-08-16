"""Unit tests for API dependency providers."""

import pytest

from app.api.dependencies import get_ai_provider, get_communication_analysis_service
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.core.config import get_settings
from app.domain.interfaces import AIProvider
from app.providers.amazon_bedrock.provider import AmazonBedrockProvider
from app.providers.microsoft_foundry.provider import MicrosoftFoundryProvider
from app.providers.mock.provider import MockAIProvider

_FOUNDRY_ENDPOINT = (
    "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev"
)
_FOUNDRY_DEPLOYMENT = "eci-gpt-54-mini"
_BEDROCK_REGION = "eu-south-2"
_BEDROCK_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_get_ai_provider_returns_ai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dependency function should return an object implementing AIProvider."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()

    provider = get_ai_provider()

    assert isinstance(provider, AIProvider)
    assert isinstance(provider, MockAIProvider)


def test_get_ai_provider_uses_configured_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dependency resolution should honor AI_PROVIDER configuration."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()

    provider = get_ai_provider()
    assert provider.PROVIDER_NAME == "mock"


def test_get_ai_provider_rejects_unsupported_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported provider configuration should surface through the dependency."""
    from app.core.exceptions import ConfigurationError

    monkeypatch.setenv("AI_PROVIDER", "azure")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        get_ai_provider()


def test_get_communication_analysis_service_uses_resolved_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service dependency should be built from the configured provider."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()

    service = get_communication_analysis_service(get_ai_provider())

    assert isinstance(service, CommunicationAnalysisService)


def test_get_communication_analysis_service_rejects_unsupported_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported provider configuration must surface before service creation."""
    from app.core.exceptions import ConfigurationError

    monkeypatch.setenv("AI_PROVIDER", "aws")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        get_communication_analysis_service(get_ai_provider())


def test_get_ai_provider_selects_microsoft_foundry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_PROVIDER=microsoft_foundry should resolve MicrosoftFoundryProvider."""
    monkeypatch.setenv("AI_PROVIDER", "microsoft_foundry")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", _FOUNDRY_ENDPOINT)
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", _FOUNDRY_DEPLOYMENT)
    get_settings.cache_clear()

    provider = get_ai_provider()

    assert isinstance(provider, AIProvider)
    assert isinstance(provider, MicrosoftFoundryProvider)
    assert provider.PROVIDER_NAME == "microsoft_foundry"


def test_get_ai_provider_selects_amazon_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_PROVIDER=amazon_bedrock should resolve AmazonBedrockProvider."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.setenv("BEDROCK_REGION", _BEDROCK_REGION)
    monkeypatch.setenv("BEDROCK_MODEL_ID", _BEDROCK_MODEL_ID)
    get_settings.cache_clear()

    provider = get_ai_provider()

    assert isinstance(provider, AIProvider)
    assert isinstance(provider, AmazonBedrockProvider)
    assert provider.PROVIDER_NAME == "amazon_bedrock"
    assert provider._bedrock_runtime_client is None


def test_get_communication_analysis_service_accepts_amazon_bedrock_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service dependency should remain provider-independent for Bedrock."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.setenv("BEDROCK_REGION", _BEDROCK_REGION)
    monkeypatch.setenv("BEDROCK_MODEL_ID", _BEDROCK_MODEL_ID)
    get_settings.cache_clear()

    service = get_communication_analysis_service(get_ai_provider())

    assert isinstance(service, CommunicationAnalysisService)
