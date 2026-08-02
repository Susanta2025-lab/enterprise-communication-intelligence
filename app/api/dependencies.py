"""FastAPI dependency providers."""

from app.core.config import get_settings
from app.domain.interfaces import AIProvider
from app.providers.factory import create_ai_provider


def get_ai_provider() -> AIProvider:
    """Resolve the configured AI provider for request handling."""
    return create_ai_provider(get_settings())
