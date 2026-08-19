"""REST endpoints for authenticated analysis history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import (
    get_analysis_history_service,
    get_identity_resolver,
    require_authenticated_communications_analyze,
)
from app.application.exceptions import AnalysisNotFoundError
from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.schemas.analysis import (
    AnalysisHistoryItem,
    AnalysisHistoryListResponse,
    history_item_from_record,
)
from app.schemas.errors import ErrorResponse

router = APIRouter(prefix="/analyses", tags=["analyses"])

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
    response_model=AnalysisHistoryListResponse,
    summary="List owned communication analyses",
    description=(
        "Returns a bounded page of analyses owned by the authenticated caller. "
        "Callers without an identity mapping receive an empty page."
    ),
    responses=_HISTORY_RESPONSES,
)
def list_analyses(
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    identity_resolver: Annotated[IdentityResolver, Depends(get_identity_resolver)],
    history_service: Annotated[AnalysisHistoryService, Depends(get_analysis_history_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnalysisHistoryListResponse:
    """List analyses owned by the current authenticated user."""
    user_id = _existing_user_id(principal, identity_resolver)
    if user_id is None:
        return AnalysisHistoryListResponse(items=[], limit=limit, offset=offset)
    records = history_service.list_for_user(user_id, limit, offset)
    return AnalysisHistoryListResponse(
        items=[history_item_from_record(record) for record in records],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{analysis_id}",
    response_model=AnalysisHistoryItem,
    summary="Get an owned communication analysis",
    description="Returns one analysis when it is owned by the authenticated caller.",
    responses={
        **_HISTORY_RESPONSES,
        404: {
            "model": ErrorResponse,
            "description": "Analysis is unknown or not owned by the caller.",
        },
    },
)
def get_analysis(
    analysis_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    identity_resolver: Annotated[IdentityResolver, Depends(get_identity_resolver)],
    history_service: Annotated[AnalysisHistoryService, Depends(get_analysis_history_service)],
) -> AnalysisHistoryItem:
    """Return an owned analysis. Unknown and cross-user ids are indistinguishable."""
    user_id = _existing_user_id(principal, identity_resolver)
    if user_id is None:
        raise AnalysisNotFoundError()
    record = history_service.get_for_user(analysis_id, user_id)
    return history_item_from_record(record)


@router.delete(
    "/{analysis_id}",
    status_code=204,
    summary="Delete an owned communication analysis",
    description="Hard-deletes an analysis owned by the authenticated caller.",
    responses={
        **_HISTORY_RESPONSES,
        204: {"description": "Analysis deleted."},
        404: {
            "model": ErrorResponse,
            "description": "Analysis is unknown or not owned by the caller.",
        },
    },
)
def delete_analysis(
    analysis_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    identity_resolver: Annotated[IdentityResolver, Depends(get_identity_resolver)],
    history_service: Annotated[AnalysisHistoryService, Depends(get_analysis_history_service)],
) -> Response:
    """Delete an owned analysis. Unknown and cross-user ids are indistinguishable."""
    user_id = _existing_user_id(principal, identity_resolver)
    if user_id is None:
        raise AnalysisNotFoundError()
    history_service.delete_for_user(analysis_id, user_id)
    return Response(status_code=204)
