"""Unit tests for the AI provider factory."""

from unittest.mock import patch

import pytest

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.domain.interfaces import AIProvider
from app.providers.amazon_bedrock.provider import AmazonBedrockProvider
from app.providers.factory import create_ai_provider
from app.providers.microsoft_foundry.provider import MicrosoftFoundryProvider
from app.providers.mock.provider import MockAIProvider

_FOUNDRY_ENDPOINT = (
    "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev"
)
_FOUNDRY_DEPLOYMENT = "eci-gpt-54-mini"
_BEDROCK_REGION = "eu-south-2"
_BEDROCK_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def _foundry_settings(ai_provider: str = "microsoft_foundry") -> Settings:
    return Settings(
        ai_provider=ai_provider,
        foundry_project_endpoint=_FOUNDRY_ENDPOINT,
        foundry_model_deployment=_FOUNDRY_DEPLOYMENT,
        _env_file=None,
    )


def _bedrock_settings(ai_provider: str = "amazon_bedrock") -> Settings:
    return Settings(
        ai_provider=ai_provider,
        bedrock_region=_BEDROCK_REGION,
        bedrock_model_id=_BEDROCK_MODEL_ID,
        _env_file=None,
    )


def test_factory_selects_mock_provider() -> None:
    """AI_PROVIDER=mock should return MockAIProvider."""
    settings = Settings(ai_provider="mock", _env_file=None)
    provider = create_ai_provider(settings)

    assert isinstance(provider, MockAIProvider)
    assert isinstance(provider, AIProvider)


@pytest.mark.parametrize("provider_name", ["MOCK", " Mock ", "mock"])
def test_factory_accepts_normalized_provider_naming(provider_name: str) -> None:
    """Provider names should be matched after lowercase normalization."""
    settings = Settings(ai_provider=provider_name, _env_file=None)
    provider = create_ai_provider(settings)

    assert isinstance(provider, MockAIProvider)
    assert settings.ai_provider == "mock"


@pytest.mark.parametrize("provider_name", ["azure", "aws", "openai", "unknown"])
def test_factory_rejects_unsupported_providers(provider_name: str) -> None:
    """Unsupported providers must fail explicitly without fallback."""
    settings = Settings(ai_provider=provider_name, _env_file=None)

    with pytest.raises(ConfigurationError) as exc_info:
        create_ai_provider(settings)

    assert "Unsupported AI provider" in exc_info.value.message
    assert "mock" in exc_info.value.message
    assert "microsoft_foundry" in exc_info.value.message
    assert "amazon_bedrock" in exc_info.value.message


def test_factory_selects_microsoft_foundry_provider() -> None:
    """AI_PROVIDER=microsoft_foundry should return MicrosoftFoundryProvider."""
    provider = create_ai_provider(_foundry_settings())

    assert isinstance(provider, MicrosoftFoundryProvider)
    assert isinstance(provider, AIProvider)
    assert provider.PROVIDER_NAME == "microsoft_foundry"


@pytest.mark.parametrize(
    "provider_name",
    ["MICROSOFT_FOUNDRY", " Microsoft_Foundry ", "microsoft_foundry"],
)
def test_factory_accepts_normalized_microsoft_foundry_naming(provider_name: str) -> None:
    """Microsoft Foundry provider names should be matched after lowercase normalization."""
    settings = _foundry_settings(provider_name)
    provider = create_ai_provider(settings)

    assert isinstance(provider, MicrosoftFoundryProvider)
    assert settings.ai_provider == "microsoft_foundry"


def test_factory_does_not_silently_fall_back_to_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unsupported configured provider must not resolve to mock."""
    monkeypatch.setenv("AI_PROVIDER", "bedrock")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError) as exc_info:
        create_ai_provider(get_settings())

    assert "Unsupported AI provider" in exc_info.value.message
    assert "bedrock" in exc_info.value.message


def test_factory_selects_amazon_bedrock_provider() -> None:
    """AI_PROVIDER=amazon_bedrock should return AmazonBedrockProvider."""
    provider = create_ai_provider(_bedrock_settings())

    assert isinstance(provider, AmazonBedrockProvider)
    assert isinstance(provider, AIProvider)
    assert provider.PROVIDER_NAME == "amazon_bedrock"
    assert provider._region == _BEDROCK_REGION
    assert provider._model_id == _BEDROCK_MODEL_ID
    assert provider._bedrock_runtime_client is None


@pytest.mark.parametrize(
    "provider_name",
    ["AMAZON_BEDROCK", " Amazon_Bedrock ", "amazon_bedrock"],
)
def test_factory_accepts_normalized_amazon_bedrock_naming(provider_name: str) -> None:
    """Amazon Bedrock provider names should be matched after lowercase normalization."""
    settings = _bedrock_settings(provider_name)
    provider = create_ai_provider(settings)

    assert isinstance(provider, AmazonBedrockProvider)
    assert settings.ai_provider == "amazon_bedrock"


def test_factory_does_not_construct_bedrock_client() -> None:
    """Factory construction must not create a boto3 Bedrock Runtime client."""
    with patch("app.providers.amazon_bedrock.provider.boto3.client") as mock_boto_client:
        provider = create_ai_provider(_bedrock_settings())

    mock_boto_client.assert_not_called()
    assert provider._bedrock_runtime_client is None


def test_factory_rejects_amazon_bedrock_without_required_settings() -> None:
    """Missing Bedrock settings must fail explicitly at the factory boundary."""
    settings = Settings.model_construct(
        ai_provider="amazon_bedrock",
        bedrock_region=None,
        bedrock_model_id=None,
    )

    with pytest.raises(ConfigurationError) as exc_info:
        create_ai_provider(settings)

    assert "BEDROCK_REGION" in exc_info.value.message
    assert "BEDROCK_MODEL_ID" in exc_info.value.message
