"""Ingest a connector message and delegate analysis to the existing workflow."""

from __future__ import annotations

import time
from uuid import UUID

from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
    PersistedAnalysisOutcome,
)
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.interfaces import CommunicationConnector
from app.domain.schemas import CommunicationRequest

logger = get_logger(__name__)


class CommunicationIngestionService:
    """Fetch a normalized message, then reuse existing analysis orchestration.

    Identity remains on ``CommunicationAnalysisWorkflowService``. This service
    does not perform AI analysis, persist analyses, or interpret vendor SDKs.
    ``connector_account_id`` is mailbox provenance from an already owned
    connector-account context. Direct-text analysis never supplies it.
    """

    def __init__(
        self,
        connector: CommunicationConnector,
        analysis_workflow: CommunicationAnalysisWorkflowService,
        *,
        connector_account_id: UUID | None = None,
    ) -> None:
        self._connector = connector
        self._analysis_workflow = analysis_workflow
        self._connector_account_id = connector_account_id

    def analyze_message(self, provider_message_id: str) -> PersistedAnalysisOutcome:
        """Fetch one message and analyze it through the injected workflow."""
        provider = self._connector.provider
        started_at = time.perf_counter()
        logger.info("connector_fetch_started", provider=provider)

        try:
            message = self._connector.fetch_message(provider_message_id)
        except Exception as exc:
            logger.warning(
                "connector_fetch_failed",
                provider=provider,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "connector_fetch_completed",
            provider=provider,
            duration_ms=elapsed_ms(started_at),
            result_count=1,
        )

        request = CommunicationRequest(message=message)
        return self._analysis_workflow.analyze(
            request,
            connector_account_id=self._connector_account_id,
        )
