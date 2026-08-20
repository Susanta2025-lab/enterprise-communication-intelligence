"""Provider-independent domain interfaces."""

from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.analysis_repository import (
    AnalysisRecord,
    AnalysisRepository,
    NewAnalysis,
)
from app.domain.interfaces.communication_connector import (
    CommunicationConnector,
    ConnectorMessageQuery,
    MessagePage,
)
from app.domain.interfaces.identity_repository import IdentityRepository
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork

__all__ = [
    "AIProvider",
    "AnalysisRecord",
    "AnalysisRepository",
    "CommunicationConnector",
    "ConnectorMessageQuery",
    "IdentityRepository",
    "MessagePage",
    "NewAnalysis",
    "PersistenceUnitOfWork",
]
