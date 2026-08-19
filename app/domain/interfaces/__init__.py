"""Provider-independent domain interfaces."""

from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.analysis_repository import (
    AnalysisRecord,
    AnalysisRepository,
    NewAnalysis,
)
from app.domain.interfaces.identity_repository import IdentityRepository
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

__all__ = [
    "AIProvider",
    "AnalysisRecord",
    "AnalysisRepository",
    "IdentityRepository",
    "NewAnalysis",
    "PersistenceUnitOfWork",
]
