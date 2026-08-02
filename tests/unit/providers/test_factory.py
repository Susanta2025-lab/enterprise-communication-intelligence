"""Unit tests for the AI provider factory."""

import pytest

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.domain.interfaces import AIProvider
from app.providers.factory import create_ai_provider
from app.providers.mock.provider import MockAIProvider


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
