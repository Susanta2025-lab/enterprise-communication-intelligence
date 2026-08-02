"""Unit tests for API dependency providers."""

import pytest

from app.api.dependencies import get_ai_provider
from app.core.config import get_settings
from app.domain.interfaces import AIProvider
from app.providers.mock.provider import MockAIProvider


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
