"""Domain-level schemas for communication analysis and context suggestion."""

from app.domain.schemas.analysis import CommunicationAnalysisResult, CommunicationRequest
from app.domain.schemas.context_suggestion import (
    BusinessContextSuggestionCandidate,
    BusinessContextSuggestionItem,
    BusinessContextSuggestionRequest,
    BusinessContextSuggestionResult,
    CommunicationSuggestionEvidence,
)
from app.domain.schemas.tabular_analysis import (
    TabularAnalysisRequest,
    TabularAnalysisResult,
    TabularSheetSummary,
)

__all__ = [
    "BusinessContextSuggestionCandidate",
    "BusinessContextSuggestionItem",
    "BusinessContextSuggestionRequest",
    "BusinessContextSuggestionResult",
    "CommunicationAnalysisResult",
    "CommunicationRequest",
    "CommunicationSuggestionEvidence",
    "TabularAnalysisRequest",
    "TabularAnalysisResult",
    "TabularSheetSummary",
]
