"""Non-authoritative AI BusinessContext suggestion use case.

AI may suggest owned active contexts for an owned communication analysis.
Suggestions never create ``BusinessContextCommunicationLink`` rows. Explicit
association remains the Phase 20D associate service.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.application.exceptions import (
    AnalysisFailedError,
    AnalysisNotFoundError,
    ConnectorAccountNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class, resolve_provider_name
from app.domain.enums import BusinessContextStatus, BusinessContextType, ContextMatchStrength
from app.domain.interfaces import AIProvider
from app.domain.interfaces.analysis_repository import AnalysisRecord
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models.business_context import BusinessContext
from app.domain.schemas.context_suggestion import (
    BusinessContextSuggestionCandidate,
    BusinessContextSuggestionRequest,
    BusinessContextSuggestionResult,
    CommunicationSuggestionEvidence,
)

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_MAX_CANDIDATES = 50
_MAX_SUGGESTIONS = 3
_DESCRIPTION_PROMPT_MAX = 400
_ACTION_ITEM_MAX = 10
_ACTION_ITEM_DESC_MAX = 240


@dataclass(frozen=True, slots=True)
class ValidatedContextSuggestion:
    """Application-validated advisory suggestion enriched with context metadata."""

    business_context_id: UUID
    type: BusinessContextType
    title: str
    reference: str | None
    match_strength: ContextMatchStrength
    rationale: str


@dataclass(frozen=True, slots=True)
class ContextSuggestionOutcome:
    """Non-authoritative suggestion response for the API layer."""

    suggestions: list[ValidatedContextSuggestion]
    no_match_reason: str | None
    provider: str | None


class BusinessContextSuggestionService:
    """Suggest BusinessContext candidates without creating authoritative links."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
        ai_provider: AIProvider,
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory
        self._ai_provider = ai_provider

    def suggest(
        self,
        principal: AuthenticatedPrincipal,
        *,
        connector_account_id: UUID,
        provider_message_id: str,
        analysis_id: UUID,
    ) -> ContextSuggestionOutcome:
        """Return advisory context matches for an owned analyzed communication.

        Never creates association links. Never retrieves mailbox content.
        """
        started_at = time.perf_counter()
        provider_name = resolve_provider_name(self._ai_provider)
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise AnalysisNotFoundError()

        message_id = provider_message_id.strip()
        if not message_id:
            raise AnalysisNotFoundError()

        candidate_count = 0
        try:
            with self._unit_of_work_factory() as uow:
                analysis = uow.analysis_repository.get_by_id_for_user(analysis_id, user_id)
                if analysis is None:
                    raise AnalysisNotFoundError()
                _require_analysis_provenance_match(
                    analysis,
                    connector_account_id=connector_account_id,
                    provider_message_id=message_id,
                )

                connector = uow.connector_accounts.get_owned(
                    connector_account_id, user_id
                )
                if connector is None:
                    raise ConnectorAccountNotFoundError()

                candidates = uow.business_contexts.list_owned(
                    user_id,
                    limit=_MAX_CANDIDATES,
                    offset=0,
                    status=BusinessContextStatus.ACTIVE,
                )
                candidate_count = len(candidates)
                candidate_by_id = {item.id: item for item in candidates}
                suggestion_request = BusinessContextSuggestionRequest(
                    evidence=_evidence_from_analysis(analysis),
                    candidates=[
                        _candidate_from_context(item) for item in candidates
                    ],
                )

                logger.info(
                    "business_context_suggestion_started",
                    provider=provider_name,
                    operation="suggest_business_context",
                    candidate_count=candidate_count,
                )

                try:
                    raw_result = self._ai_provider.suggest_business_context(
                        suggestion_request
                    )
                except Exception as exc:
                    logger.error(
                        "business_context_suggestion_failed",
                        provider=provider_name,
                        operation="suggest_business_context",
                        duration_ms=elapsed_ms(started_at),
                        error_class=error_class(exc),
                        candidate_count=candidate_count,
                    )
                    raise AnalysisFailedError(
                        f"AI provider '{type(self._ai_provider).__name__}' failed to "
                        "suggest a business context."
                    ) from exc

                outcome = _validate_and_enrich_suggestions(
                    raw_result,
                    candidate_by_id=candidate_by_id,
                    uow=uow,
                    user_id=user_id,
                )
                # Suggestion path is read-only for associations; commit only
                # closes the unit of work without creating link rows.
                uow.commit()
        except (AnalysisNotFoundError, ConnectorAccountNotFoundError, AnalysisFailedError):
            raise
        except PersistenceError as exc:
            logger.warning(
                "business_context_suggestion_persistence_failed",
                operation="suggest_business_context",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "business_context_suggestion_completed",
            provider=outcome.provider or provider_name,
            operation="suggest_business_context",
            duration_ms=elapsed_ms(started_at),
            candidate_count=candidate_count,
            suggestion_count=len(outcome.suggestions),
        )
        return outcome


def _require_analysis_provenance_match(
    analysis: AnalysisRecord,
    *,
    connector_account_id: UUID,
    provider_message_id: str,
) -> None:
    """Reject analysis when mailbox provenance does not match the request."""
    if (
        analysis.connector_account_id != connector_account_id
        or analysis.message_id != provider_message_id
    ):
        raise AnalysisNotFoundError()


def _evidence_from_analysis(analysis: AnalysisRecord) -> CommunicationSuggestionEvidence:
    """Build minimized prompt evidence from persisted analysis fields only."""
    action_descriptions: list[str] = []
    for item in analysis.action_items[:_ACTION_ITEM_MAX]:
        if not isinstance(item, dict):
            continue
        description = item.get("description")
        if isinstance(description, str):
            text = description.strip()
            if text:
                action_descriptions.append(text[:_ACTION_ITEM_DESC_MAX])
    summary = analysis.summary_text.strip() or "No summary available."
    return CommunicationSuggestionEvidence(
        summary_text=summary[:4000],
        category=analysis.category,
        priority=analysis.priority,
        action_item_descriptions=action_descriptions,
    )


def _candidate_from_context(context: BusinessContext) -> BusinessContextSuggestionCandidate:
    """Map an owned active context into bounded AI candidate metadata."""
    description = context.description
    if description is not None and len(description) > _DESCRIPTION_PROMPT_MAX:
        description = description[:_DESCRIPTION_PROMPT_MAX]
    return BusinessContextSuggestionCandidate(
        business_context_id=context.id,
        type=context.type,
        title=context.title,
        reference=context.reference,
        description=description,
    )


def _validate_and_enrich_suggestions(
    raw_result: BusinessContextSuggestionResult,
    *,
    candidate_by_id: dict[UUID, BusinessContext],
    uow: PersistenceUnitOfWork,
    user_id: UUID,
) -> ContextSuggestionOutcome:
    """Discard hallucinated/stale IDs and revalidate ownership/active status."""
    seen: set[UUID] = set()
    validated: list[ValidatedContextSuggestion] = []

    for item in raw_result.suggestions:
        if len(validated) >= _MAX_SUGGESTIONS:
            break
        context_id = item.business_context_id
        if context_id in seen:
            continue
        seen.add(context_id)
        if context_id not in candidate_by_id:
            continue
        current = uow.business_contexts.get_owned(context_id, user_id)
        if current is None:
            continue
        if current.status is not BusinessContextStatus.ACTIVE:
            continue
        validated.append(
            ValidatedContextSuggestion(
                business_context_id=current.id,
                type=current.type,
                title=current.title,
                reference=current.reference,
                match_strength=item.match_strength,
                rationale=item.rationale,
            )
        )

    no_match_reason = raw_result.no_match_reason
    if validated:
        no_match_reason = None
    elif not candidate_by_id:
        no_match_reason = no_match_reason or (
            "No active contexts were available to compare."
        )
    elif not no_match_reason:
        no_match_reason = "No suitable active context matched the analysis."

    return ContextSuggestionOutcome(
        suggestions=validated,
        no_match_reason=no_match_reason,
        provider=raw_result.provider,
    )
