"""Configuration-driven AI provider factory."""

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.domain.interfaces import AIProvider


def create_ai_provider(settings: Settings | None = None) -> AIProvider:
    """Create an AI provider based on application settings.

    Supported providers:
    - ``mock``: deterministic offline provider for local development and tests

    Unsupported provider names raise ``ConfigurationError``. There is no silent
    fallback to another provider.
    """
    resolved = settings or get_settings()
    provider_name = resolved.ai_provider.strip().lower()

    if provider_name == "mock":
        from app.providers.mock.provider import MockAIProvider

        return MockAIProvider()

    raise ConfigurationError(
        f"Unsupported AI provider '{resolved.ai_provider}'. Supported providers: mock"
    )
