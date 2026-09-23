"""Application service orchestrating communication analysis."""

import time

from app.application.exceptions import AnalysisFailedError
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class, resolve_provider_name
from app.domain.interfaces import AIProvider
from app.domain.models import Summary
from app.domain.schemas import (
    CommunicationAnalysisResult,
    CommunicationRequest,
    TabularAnalysisRequest,
    TabularAnalysisResult,
)

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

    def supports_image_input(self) -> bool:
        """Return whether the injected provider explicitly accepts image input."""
        return self._provider.supports_image_input()

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Validate, delegate, and return the analysis for a communication request.

        Raises:
            AnalysisFailedError: if the underlying provider fails to analyze
                the communication.
        """
        provider_name = resolve_provider_name(self._provider)
        started_at = time.perf_counter()

        logger.info(
            "communication_analysis_started",
            provider=provider_name,
            operation="analyze",
            source_type=request.message.metadata.source_type.value,
        )

        try:
            result = self._provider.analyze(request)
        except Exception as exc:
            logger.error(
                "communication_analysis_failed",
                provider=provider_name,
                operation="analyze",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise AnalysisFailedError(
                f"AI provider '{type(self._provider).__name__}' failed to analyze "
                "the communication."
            ) from exc

        logger.info(
            "communication_analysis_completed",
            provider=provider_name,
            operation="analyze",
            priority=result.analysis.priority.level.value,
            category=result.analysis.category.value,
            duration_ms=elapsed_ms(started_at),
        )

        return result

    def analyze_tabular(self, request: TabularAnalysisRequest) -> TabularAnalysisResult:
        """Delegate bounded XLSX/tabular analysis to the injected AI provider.

        Raises:
            AnalysisFailedError: if the provider fails or returns invalid output.
        """
        provider_name = resolve_provider_name(self._provider)
        started_at = time.perf_counter()

        logger.info(
            "tabular_analysis_started",
            provider=provider_name,
            operation="analyze_tabular",
            input_character_count=request.input_character_count,
            source_truncated=request.source_truncated,
        )

        try:
            result = self._provider.analyze_tabular(request)
            # Revalidate custom adapters and model_construct/model_copy outputs
            # before logging success or mapping into the attachment contract.
            result = TabularAnalysisResult.model_validate(result.model_dump())
            Summary(text=result.summary)
        except Exception as exc:
            logger.error(
                "tabular_analysis_failed",
                provider=provider_name,
                operation="analyze_tabular",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise AnalysisFailedError(
                f"AI provider '{type(self._provider).__name__}' failed to analyze "
                "the tabular workbook."
            ) from exc

        logger.info(
            "tabular_analysis_completed",
            provider=result.provider or provider_name,
            operation="analyze_tabular",
            duration_ms=elapsed_ms(started_at),
            source_truncated=result.source_truncated,
            sheet_summary_count=len(result.sheet_summaries),
        )
        return result
