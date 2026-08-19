"""Provider-independent domain interfaces."""

from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.analysis_repository import (
    AnalysisRecord,
    AnalysisRepository,
    NewAnalysis,
)
from app.domain.interfaces.identity_repository import IdentityRepository

__all__ = [
    "AIProvider",
    "AnalysisRecord",
    "AnalysisRepository",
    "IdentityRepository",
    "NewAnalysis",
]
