"""Domain-level schemas for communication analysis and context suggestion."""

from app.domain.schemas.analysis import CommunicationAnalysisResult, CommunicationRequest
from app.domain.schemas.context_suggestion import (
    BusinessContextSuggestionCandidate,
    BusinessContextSuggestionItem,
    BusinessContextSuggestionRequest,
    BusinessContextSuggestionResult,
    CommunicationSuggestionEvidence,
)

__all__ = [
    "BusinessContextSuggestionCandidate",
    "BusinessContextSuggestionItem",
    "BusinessContextSuggestionRequest",
    "BusinessContextSuggestionResult",
    "CommunicationAnalysisResult",
    "CommunicationRequest",
    "CommunicationSuggestionEvidence",
]
