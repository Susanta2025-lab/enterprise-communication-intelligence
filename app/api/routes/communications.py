"""REST endpoint for communication analysis."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_communication_analysis_service
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.core.logging import get_logger
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.schemas.errors import ErrorResponse

router = APIRouter(prefix="/communications", tags=["communications"])
logger = get_logger(__name__)


@router.post(
    "/analyze",
    response_model=CommunicationAnalysisResult,
    summary="Analyze a business communication",
    description=(
        "Validates a communication and returns a structured analysis "
        "(summary, priority, category, action items, and an optional draft reply) "
        "produced by the configured AI provider."
    ),
    responses={
        500: {
            "model": ErrorResponse,
            "description": "Analysis or configuration failure.",
        },
        503: {
            "model": ErrorResponse,
            "description": "A required service dependency is unavailable.",
        },
    },
)
def analyze_communication(
    request: CommunicationRequest,
    service: CommunicationAnalysisService = Depends(get_communication_analysis_service),
) -> CommunicationAnalysisResult:
    """Analyze a communication using the configured AI provider."""
    logger.info(
        "communication_analysis_request_received",
        source_type=request.message.metadata.source_type.value,
        message_id=request.message.message_id,
    )
    return service.analyze(request)
