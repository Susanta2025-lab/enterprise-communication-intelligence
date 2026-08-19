"""REST endpoint for communication analysis."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_communication_analysis_workflow_service
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.core.logging import get_logger
from app.domain.schemas import CommunicationRequest
from app.schemas.analysis import CommunicationAnalysisResponse
from app.schemas.errors import ErrorResponse

router = APIRouter(prefix="/communications", tags=["communications"])
logger = get_logger(__name__)


@router.post(
    "/analyze",
    response_model=CommunicationAnalysisResponse,
    summary="Analyze a business communication",
    description=(
        "Validates a communication and returns a structured analysis "
        "(summary, priority, category, action items, and an optional draft reply) "
        "produced by the configured AI provider. When persistence is configured "
        "and the caller is authenticated, a successful analysis is stored and "
        "``analysis_id`` is returned."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Authenticated caller lacks communications:analyze.",
        },
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
    workflow: CommunicationAnalysisWorkflowService = Depends(
        get_communication_analysis_workflow_service
    ),
) -> CommunicationAnalysisResponse:
    """Analyze a communication using the configured AI provider."""
    logger.info(
        "communication_analysis_request_received",
        source_type=request.message.metadata.source_type.value,
        message_id=request.message.message_id,
    )
    outcome = workflow.analyze(request)
    return CommunicationAnalysisResponse(
        analysis=outcome.result.analysis,
        provider=outcome.result.provider,
        analysis_id=outcome.analysis_id,
    )
