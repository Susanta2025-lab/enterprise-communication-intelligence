"""REST endpoints for authenticated attachment-analysis history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_attachment_analysis_history_service,
    get_identity_resolver,
    require_authenticated_communications_analyze,
)
from app.application.exceptions import AttachmentAnalysisNotFoundError
from app.application.services.attachment_analysis_history import (
    AttachmentAnalysisHistoryService,
)
from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.schemas.attachments import (
    AttachmentAnalysisListResponse,
    AttachmentAnalysisResponse,
    attachment_analysis_from_record,
)
from app.schemas.errors import ErrorResponse

router = APIRouter(prefix="/attachment-analyses", tags=["attachment-analyses"])

_HISTORY_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": "Authenticated caller lacks communications:analyze.",
    },
    503: {
        "model": ErrorResponse,
        "description": "Persistence is currently unavailable.",
    },
}


def _existing_user_id(
    principal: AuthenticatedPrincipal,
    identity_resolver: IdentityResolver,
) -> UUID | None:
    return identity_resolver.find_existing(principal)


@router.get(
    "",
    response_model=AttachmentAnalysisListResponse,
    summary="List owned attachment analyses",
    description=(
        "Returns a bounded page of attachment analyses owned by the "
        "authenticated caller. Optional connector and message filters are "
        "applied only to that caller's rows. Callers without an identity "
        "mapping receive an empty page."
    ),
    responses=_HISTORY_RESPONSES,
)
def list_attachment_analyses(
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    identity_resolver: Annotated[IdentityResolver, Depends(get_identity_resolver)],
    history_service: Annotated[
        AttachmentAnalysisHistoryService,
        Depends(get_attachment_analysis_history_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    connector_account_id: Annotated[UUID | None, Query()] = None,
    provider_message_id: Annotated[str | None, Query()] = None,
) -> AttachmentAnalysisListResponse:
    """List attachment analyses owned by the current authenticated user."""
    user_id = _existing_user_id(principal, identity_resolver)
    if user_id is None:
        return AttachmentAnalysisListResponse(items=[], limit=limit, offset=offset)
    message_id = provider_message_id.strip() if provider_message_id else None
    if message_id == "":
        message_id = None
    records = history_service.list_for_user(
        user_id,
        limit,
        offset,
        connector_account_id=connector_account_id,
        provider_message_id=message_id,
    )
    return AttachmentAnalysisListResponse(
        items=[attachment_analysis_from_record(record) for record in records],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{attachment_analysis_id}",
    response_model=AttachmentAnalysisResponse,
    summary="Get an owned attachment analysis",
    description=(
        "Returns one attachment analysis when it is owned by the authenticated "
        "caller. Unknown and cross-user ids are indistinguishable."
    ),
    responses={
        **_HISTORY_RESPONSES,
        404: {
            "model": ErrorResponse,
            "description": "Attachment analysis is unknown or not owned by the caller.",
        },
    },
)
def get_attachment_analysis(
    attachment_analysis_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    identity_resolver: Annotated[IdentityResolver, Depends(get_identity_resolver)],
    history_service: Annotated[
        AttachmentAnalysisHistoryService,
        Depends(get_attachment_analysis_history_service),
    ],
) -> AttachmentAnalysisResponse:
    """Return an owned attachment analysis. Cross-user ids are not distinguished."""
    user_id = _existing_user_id(principal, identity_resolver)
    if user_id is None:
        raise AttachmentAnalysisNotFoundError()
    record = history_service.get_for_user(attachment_analysis_id, user_id)
    return attachment_analysis_from_record(record)
