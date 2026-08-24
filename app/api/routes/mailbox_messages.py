"""Owned connected-mailbox message routes.

Phase 14C mounts mailbox-backed analyze only. Bounded listing remains later.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_connected_mailbox_analysis_service,
    require_authenticated_communications_read_and_analyze,
)
from app.application.services.connected_mailbox_analysis import (
    ConnectedMailboxAnalysisService,
)
from app.core.security import AuthenticatedPrincipal
from app.schemas.analysis import CommunicationAnalysisResponse
from app.schemas.errors import ErrorResponse
from app.schemas.mailbox import ConnectorAccountMessageAnalyzeRequest

router = APIRouter(tags=["connector-accounts"])

_MAILBOX_ANALYZE_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": (
            "Authenticated caller lacks communications:read or communications:analyze."
        ),
    },
    404: {
        "model": ErrorResponse,
        "description": (
            "Connector account is unknown or not owned, or the mailbox message "
            "was not found."
        ),
    },
    409: {
        "model": ErrorResponse,
        "description": "Owned connector account cannot currently be used for mailbox read.",
    },
    500: {
        "model": ErrorResponse,
        "description": "Analysis or message-normalization failure.",
    },
    503: {
        "model": ErrorResponse,
        "description": "A required service dependency is currently unavailable.",
    },
}


@router.post(
    "/connector-accounts/{connector_account_id}/messages/analyze",
    response_model=CommunicationAnalysisResponse,
    summary="Analyze a message from a connected mailbox",
    description=(
        "Fetches one message from an owned ACTIVE mailbox that allows mail.read "
        "and returns the existing structured analysis contract. Requires both "
        "communications:read and communications:analyze. Direct-text "
        "POST /communications/analyze remains analyze-only and does not use "
        "connector accounts. Raw mailbox bodies, credential locators, and tokens "
        "are never returned. This does not list mailbox messages, create a "
        "workflow action, or send mail."
    ),
    responses={
        **_MAILBOX_ANALYZE_RESPONSES,
        200: {
            "model": CommunicationAnalysisResponse,
            "description": "Structured analysis of the connected mailbox message.",
        },
    },
)
def analyze_connected_mailbox_message(
    connector_account_id: UUID,
    request: ConnectorAccountMessageAnalyzeRequest,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_read_and_analyze),
    ],
    service: Annotated[
        ConnectedMailboxAnalysisService,
        Depends(get_connected_mailbox_analysis_service),
    ],
) -> CommunicationAnalysisResponse:
    """Analyze one owned mailbox message through the connected-mailbox service."""
    outcome = service.analyze(
        principal,
        connector_account_id,
        request.provider_message_id,
    )
    return CommunicationAnalysisResponse(
        analysis=outcome.result.analysis,
        provider=outcome.result.provider,
        analysis_id=outcome.analysis_id,
    )
