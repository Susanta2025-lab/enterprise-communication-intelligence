"""Owned connected-mailbox message routes.

Listing is a bounded read-through of recent mailbox metadata. Analyze fetches
one owned message and reuses the existing AI workflow. Neither route sends
mail or imports Gmail or Microsoft Graph connector classes.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_connected_mailbox_analysis_service,
    get_connected_mailbox_listing_service,
    require_authenticated_communications_read,
    require_authenticated_communications_read_and_analyze,
)
from app.application.services.connected_mailbox_analysis import (
    ConnectedMailboxAnalysisService,
)
from app.application.services.connected_mailbox_listing import (
    ConnectedMailboxMessageListingService,
)
from app.core.security import AuthenticatedPrincipal
from app.schemas.analysis import CommunicationAnalysisResponse
from app.schemas.errors import ErrorResponse
from app.schemas.mailbox import (
    ConnectorAccountMessageAnalyzeRequest,
    ConnectorAccountMessageListQuery,
    ConnectorAccountMessageListResponse,
)

router = APIRouter(tags=["connector-accounts"])

_MAILBOX_READ_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": "Authenticated caller lacks communications:read.",
    },
    404: {
        "model": ErrorResponse,
        "description": "Connector account is unknown or not owned.",
    },
    409: {
        "model": ErrorResponse,
        "description": "Owned connector account cannot currently be used for mailbox read.",
    },
    500: {
        "model": ErrorResponse,
        "description": "Message-normalization failure.",
    },
    503: {
        "model": ErrorResponse,
        "description": "A required service dependency is currently unavailable.",
    },
}

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


@router.get(
    "/connector-accounts/{connector_account_id}/messages",
    response_model=ConnectorAccountMessageListResponse,
    summary="List messages from a connected mailbox",
    description=(
        "Returns one bounded page of provider-neutral mailbox metadata from an "
        "owned ACTIVE mailbox that allows mail.read. Requires communications:read. "
        "communications:analyze is not required. Listing is a request/response "
        "read-through: it does not synchronize, mirror, search, return bodies or "
        "attachments, invoke AI, create a workflow action, or send mail. "
        "next_cursor is an opaque continuation token, never a provider "
        "pagination URL."
    ),
    responses={
        **_MAILBOX_READ_RESPONSES,
        200: {
            "model": ConnectorAccountMessageListResponse,
            "description": "Bounded page of mailbox list metadata.",
        },
        400: {
            "model": ErrorResponse,
            "description": "Mailbox pagination cursor is invalid.",
        },
    },
)
def list_connected_mailbox_messages(
    connector_account_id: UUID,
    query: Annotated[ConnectorAccountMessageListQuery, Query()],
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_read),
    ],
    service: Annotated[
        ConnectedMailboxMessageListingService,
        Depends(get_connected_mailbox_listing_service),
    ],
) -> ConnectorAccountMessageListResponse:
    """List one bounded page of owned mailbox metadata."""
    return service.list_messages(principal, connector_account_id, query)


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
