"""Owned connected-mailbox attachment-analysis route.

The POST is explicit authorization to retrieve and analyze exactly one
attachment. It does not list attachments, analyze email bodies, create a
workflow action, or send mail.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_connected_mailbox_attachment_analysis_service,
    require_authenticated_communications_read_and_analyze,
)
from app.application.services.connected_mailbox_attachment_analysis import (
    ConnectedMailboxAttachmentAnalysisService,
)
from app.core.security import AuthenticatedPrincipal
from app.schemas.attachments import (
    AttachmentAnalysisResponse,
    ConnectorAccountAttachmentAnalyzeRequest,
    attachment_analysis_from_record,
)
from app.schemas.errors import ErrorResponse

router = APIRouter(tags=["connector-accounts"])

_ATTACHMENT_ANALYZE_RESPONSES = {
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
            "or attachment was not found."
        ),
    },
    409: {
        "model": ErrorResponse,
        "description": (
            "Owned connector account cannot currently be used for mailbox read, "
            "or image analysis is not available."
        ),
    },
    422: {
        "model": ErrorResponse,
        "description": (
            "Attachment is unsupported, exceeds limits, failed scan policy, "
            "or could not be processed."
        ),
    },
    500: {
        "model": ErrorResponse,
        "description": "Analysis or message-normalization failure.",
    },
    503: {
        "model": ErrorResponse,
        "description": (
            "A required service dependency is currently unavailable, including "
            "an unconfigured attachment scanner."
        ),
    },
}


@router.post(
    "/connector-accounts/{connector_account_id}/messages/attachments/analyze",
    response_model=AttachmentAnalysisResponse,
    summary="Analyze one attachment from a connected mailbox",
    description=(
        "Retrieves exactly one attachment from an owned ACTIVE mailbox that "
        "allows mail.read, scans it, parses it, and returns a structured "
        "analysis. Requires both communications:read and communications:analyze. "
        "The request is explicit authorization for that one attachment. "
        "Raw bytes, extracted document text, and scanner implementation details "
        "are never returned. This does not create a workflow action or send mail. "
        "Each successful request creates a new attachment-analysis record."
    ),
    responses={
        **_ATTACHMENT_ANALYZE_RESPONSES,
        200: {
            "model": AttachmentAnalysisResponse,
            "description": "Structured analysis of the selected attachment.",
        },
    },
)
def analyze_connected_mailbox_attachment(
    connector_account_id: UUID,
    request: ConnectorAccountAttachmentAnalyzeRequest,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_read_and_analyze),
    ],
    service: Annotated[
        ConnectedMailboxAttachmentAnalysisService,
        Depends(get_connected_mailbox_attachment_analysis_service),
    ],
) -> AttachmentAnalysisResponse:
    """Analyze one owned mailbox attachment through the application service."""
    outcome = service.analyze(
        principal,
        connector_account_id,
        request.provider_message_id,
        request.provider_attachment_id,
    )
    return attachment_analysis_from_record(outcome.record)
