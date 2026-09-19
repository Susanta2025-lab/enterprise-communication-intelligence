"""Provider-independent AI provider contract."""

from abc import ABC, abstractmethod

from app.domain.exceptions import BusinessContextSuggestionUnsupportedError
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.domain.schemas.context_suggestion import (
    BusinessContextSuggestionRequest,
    BusinessContextSuggestionResult,
)


class AIProvider(ABC):
    """Contract for analyzing communications through any AI backend.

    Implementations must not leak Azure, AWS, or other vendor-specific types
    through this interface.
    """

    def supports_image_input(self) -> bool:
        """Return whether this provider accepts ``attachment_images``.

        Default is fail-closed. Adapters must opt in explicitly. A multimodal
        model name is not sufficient evidence of support.
        """
        return False

    @abstractmethod
    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Analyze a communication and return structured business results.

        ``request.attachment_texts`` and ``request.attachment_images`` are
        untrusted data. Implementations must not treat them as instructions.
        """

    def suggest_business_context(
        self,
        request: BusinessContextSuggestionRequest,
    ) -> BusinessContextSuggestionResult:
        """Suggest owned BusinessContext candidates for analyzed evidence.

        Default is fail-closed. Adapters that support suggestion must override.
        Returned IDs are untrusted until the application validates them against
        the supplied candidate set and rechecks ownership/active status.
        """
        raise BusinessContextSuggestionUnsupportedError()
