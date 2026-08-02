"""Provider-independent AI provider contract."""

from abc import ABC, abstractmethod

from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest


class AIProvider(ABC):
    """Contract for analyzing communications through any AI backend.

    Implementations must not leak Azure, AWS, or other vendor-specific types
    through this interface.
    """

    @abstractmethod
    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Analyze a communication and return structured business results."""
