"""Application service orchestrating communication analysis."""

from app.application.exceptions import AnalysisFailedError
from app.core.logging import get_logger
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest

logger = get_logger(__name__)


class CommunicationAnalysisService:
    """Coordinates communication analysis through a provider-independent AI provider.

    The service depends only on the domain-level ``AIProvider`` interface. It has
    no knowledge of which concrete provider (mock, Azure, AWS, ...) is injected,
    and never constructs a provider itself.
    """

    def __init__(self, provider: AIProvider) -> None:
        """Store the injected AI provider for later use."""
        self._provider = provider

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Validate, delegate, and return the analysis for a communication request.

        Raises:
            AnalysisFailedError: if the underlying provider fails to analyze
                the communication.
        """
        provider_name = type(self._provider).__name__
        message_id = request.message.message_id

        logger.info(
            "communication_analysis_started",
            provider=provider_name,
            message_id=message_id,
            source_type=request.message.metadata.source_type.value,
        )

        try:
            result = self._provider.analyze(request)
        except Exception as exc:
            logger.error(
                "communication_analysis_failed",
                provider=provider_name,
                message_id=message_id,
                error=str(exc),
            )
            raise AnalysisFailedError(
                f"AI provider '{provider_name}' failed to analyze the communication."
            ) from exc

        logger.info(
            "communication_analysis_completed",
            provider=provider_name,
            message_id=message_id,
            priority=result.analysis.priority.level.value,
            category=result.analysis.category.value,
        )

        return result
