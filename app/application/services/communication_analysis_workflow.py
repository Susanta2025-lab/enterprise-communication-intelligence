"""Persistence-aware orchestration around the AI-only analysis service."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import error_class
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."


@dataclass(frozen=True, slots=True)
class PersistedAnalysisOutcome:
    """AI analysis result plus an optional persisted resource id."""

    result: CommunicationAnalysisResult
    analysis_id: UUID | None


class CommunicationAnalysisWorkflowService:
    """Resolve ownership, call the AI service, then persist when configured.

    ``CommunicationAnalysisService`` remains AI-only. Database transactions are
    never held open during a provider call.
    """

    def __init__(
        self,
        analysis_service: CommunicationAnalysisService,
        *,
        principal: AuthenticatedPrincipal | None = None,
        identity_resolver: IdentityResolver | None = None,
        history_service: AnalysisHistoryService | None = None,
    ) -> None:
        self._analysis_service = analysis_service
        self._principal = principal
        self._identity_resolver = identity_resolver
        self._history_service = history_service

    def analyze(
        self,
        request: CommunicationRequest,
        *,
        connector_account_id: UUID | None = None,
    ) -> PersistedAnalysisOutcome:
        """Analyze a communication and optionally persist the result.

        ``connector_account_id`` is mailbox provenance supplied by connector
        ingestion. Direct-text analysis omits it. The generic analyze API
        never accepts this argument.
        """
        principal = self._principal
        identity_resolver = self._identity_resolver
        history_service = self._history_service
        if principal is None or identity_resolver is None or history_service is None:
            result = self._analysis_service.analyze(request)
            return PersistedAnalysisOutcome(result=result, analysis_id=None)

        try:
            user_id = identity_resolver.resolve_or_create(principal)
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            logger.warning(
                "identity_resolution_failed",
                operation="resolve_or_create",
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        result = self._analysis_service.analyze(request)

        try:
            saved = history_service.save(
                user_id,
                request,
                result,
                connector_account_id=connector_account_id,
            )
        except PersistenceError as exc:
            logger.warning(
                "analysis_persistence_failed",
                operation="save",
                error_class=error_class(exc),
            )
            return PersistedAnalysisOutcome(result=result, analysis_id=None)

        return PersistedAnalysisOutcome(result=result, analysis_id=saved.id)
