"""FastAPI dependency providers."""

from fastapi import Depends

from app.application.services.communication_analysis import CommunicationAnalysisService
from app.core.config import get_settings
from app.domain.interfaces import AIProvider
from app.providers.factory import create_ai_provider


def get_ai_provider() -> AIProvider:
    """Resolve the configured AI provider for request handling."""
    return create_ai_provider(get_settings())


def get_communication_analysis_service(
    provider: AIProvider = Depends(get_ai_provider),
) -> CommunicationAnalysisService:
    """Build the communication analysis service with the configured AI provider."""
    return CommunicationAnalysisService(provider)
