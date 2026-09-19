"""REST endpoints for BusinessContext CRUD, lifecycle, provenance links, and timeline."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import (
    get_business_context_communication_link_service,
    get_business_context_service,
    get_business_context_suggestion_service,
    get_context_timeline_service,
    require_authenticated_communications_analyze,
    require_authenticated_communications_read_and_analyze,
)
from app.application.services.business_context_communication_links import (
    BusinessContextCommunicationLinkService,
)
from app.application.services.business_context_suggestions import (
    BusinessContextSuggestionService,
)
from app.application.services.business_contexts import BusinessContextService
from app.application.services.context_timeline import ContextTimelineService
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import BusinessContextStatus, BusinessContextType
from app.schemas.business_contexts import (
    BusinessContextCommunicationAssociateRequest,
    BusinessContextCommunicationLinkListResponse,
    BusinessContextCommunicationLinkResponse,
    BusinessContextCreateRequest,
    BusinessContextListResponse,
    BusinessContextResponse,
    BusinessContextSuggestionListResponse,
    BusinessContextSuggestionRequestBody,
    BusinessContextUpdateRequest,
    ContextTimelineListResponse,
    business_context_communication_link_response,
    business_context_response,
    business_context_suggestion_list_response,
    context_timeline_entry_response,
)
from app.schemas.errors import ErrorResponse

router = APIRouter(prefix="/contexts", tags=["contexts"])

_ANALYZE_AUTH_RESPONSES = {
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

_READ_ANALYZE_AUTH_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": (
            "Authenticated caller lacks communications:read and/or "
            "communications:analyze."
        ),
    },
    503: {
        "model": ErrorResponse,
        "description": "Persistence is currently unavailable.",
    },
}

_CONTEXT_NOT_FOUND = {
    404: {
        "model": ErrorResponse,
        "description": "Business context is unknown or not owned by the caller.",
    },
}

_LINK_NOT_FOUND = {
    404: {
        "model": ErrorResponse,
        "description": (
            "Business context or communication link is unknown or not owned "
            "by the caller."
        ),
    },
}

_CONTEXT_CONFLICT = {
    409: {
        "model": ErrorResponse,
        "description": "Business context cannot be updated in its current state.",
    },
}

_LINK_CONFLICT = {
    409: {
        "model": ErrorResponse,
        "description": (
            "Provenance association conflicts (duplicate link or archived context)."
        ),
    },
}


@router.post(
    "",
    status_code=201,
    response_model=BusinessContextResponse,
    summary="Create a BusinessContext",
    description=(
        "Creates an active BusinessContext owned by the authenticated caller. "
        "Requires ``communications:analyze``. Ownership and lifecycle fields are "
        "server-authoritative; mailbox connection is not required. Platform Owner "
        "does not bypass object ownership."
    ),
    responses=_ANALYZE_AUTH_RESPONSES,
)
def create_business_context(
    request: BusinessContextCreateRequest,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    service: Annotated[BusinessContextService, Depends(get_business_context_service)],
) -> BusinessContextResponse:
    """Create an owned active BusinessContext."""
    context = service.create(
        principal,
        type=request.type,
        title=request.title,
        description=request.description,
        reference=request.reference,
    )
    return business_context_response(context)


@router.get(
    "",
    response_model=BusinessContextListResponse,
    summary="List owned BusinessContexts",
    description=(
        "Returns a bounded page of BusinessContexts owned by the authenticated "
        "caller. Default filter is ``status=active``. Use ``status=archived`` for "
        "archived-only, or ``include_archived=true`` to return every lifecycle "
        "state. Optional ``type`` and ``reference`` apply exact-match filters. "
        "Callers without an identity mapping receive an empty page."
    ),
    responses=_ANALYZE_AUTH_RESPONSES,
)
def list_business_contexts(
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    service: Annotated[BusinessContextService, Depends(get_business_context_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[
        BusinessContextStatus | None,
        Query(alias="status"),
    ] = BusinessContextStatus.ACTIVE,
    type_filter: Annotated[
        BusinessContextType | None,
        Query(alias="type"),
    ] = None,
    reference: Annotated[str | None, Query(max_length=128)] = None,
    include_archived: Annotated[
        bool,
        Query(
            description=(
                "When true, return contexts in every lifecycle state "
                "(active and archived). When false, apply the ``status`` filter "
                "(default active)."
            ),
        ),
    ] = False,
) -> BusinessContextListResponse:
    """List BusinessContexts owned by the current authenticated user."""
    effective_status: BusinessContextStatus | None = (
        None if include_archived else status_filter
    )
    contexts = service.list(
        principal,
        limit,
        offset,
        status=effective_status,
        type=type_filter,
        reference=reference,
    )
    return BusinessContextListResponse(
        items=[business_context_response(item) for item in contexts],
        limit=limit,
        offset=offset,
    )


@router.post(
    "/suggestions",
    response_model=BusinessContextSuggestionListResponse,
    summary="Suggest BusinessContexts for an analyzed communication",
    description=(
        "Returns non-authoritative AI suggestions for which owned active "
        "BusinessContexts may match an owned persisted communication analysis. "
        "Requires ``communications:read`` and ``communications:analyze``. "
        "Suggestions never create association links; callers must use the "
        "explicit associate endpoint after human confirmation. Does not "
        "retrieve mailbox content or attachment bytes. Platform Owner does "
        "not bypass object ownership."
    ),
    responses={
        **_READ_ANALYZE_AUTH_RESPONSES,
        404: {
            "model": ErrorResponse,
            "description": (
                "Analysis or connector account is unknown or not owned by the caller."
            ),
        },
        500: {
            "model": ErrorResponse,
            "description": "AI provider failed to produce suggestions.",
        },
    },
)
def suggest_business_contexts(
    request: BusinessContextSuggestionRequestBody,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_read_and_analyze),
    ],
    service: Annotated[
        BusinessContextSuggestionService,
        Depends(get_business_context_suggestion_service),
    ],
) -> BusinessContextSuggestionListResponse:
    """Return advisory context matches without creating associations."""
    outcome = service.suggest(
        principal,
        connector_account_id=request.connector_account_id,
        provider_message_id=request.provider_message_id,
        analysis_id=request.analysis_id,
    )
    return business_context_suggestion_list_response(outcome)


@router.get(
    "/{context_id}",
    response_model=BusinessContextResponse,
    summary="Get an owned BusinessContext",
    description=(
        "Returns one BusinessContext when owned by the authenticated caller. "
        "Unknown and cross-user ids are indistinguishable (404)."
    ),
    responses={**_ANALYZE_AUTH_RESPONSES, **_CONTEXT_NOT_FOUND},
)
def get_business_context(
    context_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    service: Annotated[BusinessContextService, Depends(get_business_context_service)],
) -> BusinessContextResponse:
    """Return an owned BusinessContext."""
    context = service.get(principal, context_id)
    return business_context_response(context)


@router.patch(
    "/{context_id}",
    response_model=BusinessContextResponse,
    summary="Update an owned BusinessContext",
    description=(
        "Partially updates type, title, description, and/or reference on an "
        "owned active context. Ownership and lifecycle fields cannot be set. "
        "Archived contexts reject updates (409)."
    ),
    responses={
        **_ANALYZE_AUTH_RESPONSES,
        **_CONTEXT_NOT_FOUND,
        **_CONTEXT_CONFLICT,
    },
)
def update_business_context(
    context_id: UUID,
    request: BusinessContextUpdateRequest,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    service: Annotated[BusinessContextService, Depends(get_business_context_service)],
) -> BusinessContextResponse:
    """Partially update an owned active BusinessContext."""
    fields_set = request.model_fields_set
    kwargs: dict = {}
    if "type" in fields_set:
        kwargs["type"] = request.type
    if "title" in fields_set:
        kwargs["title"] = request.title
    if "description" in fields_set:
        kwargs["description"] = request.description
    if "reference" in fields_set:
        kwargs["reference"] = request.reference
    context = service.update(principal, context_id, **kwargs)
    return business_context_response(context)


@router.post(
    "/{context_id}/archive",
    response_model=BusinessContextResponse,
    summary="Archive an owned BusinessContext",
    description=(
        "Moves an owned context from active to archived. Idempotent when already "
        "archived. Does not delete provenance links, analyses, workflows, "
        "connectors, or provider mail."
    ),
    responses={**_ANALYZE_AUTH_RESPONSES, **_CONTEXT_NOT_FOUND},
)
def archive_business_context(
    context_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    service: Annotated[BusinessContextService, Depends(get_business_context_service)],
) -> BusinessContextResponse:
    """Archive an owned BusinessContext."""
    context = service.archive(principal, context_id)
    return business_context_response(context)


@router.post(
    "/{context_id}/restore",
    response_model=BusinessContextResponse,
    summary="Restore an owned BusinessContext",
    description=(
        "Moves an owned context from archived to active. Idempotent when already "
        "active. Restored contexts may receive new communication associations."
    ),
    responses={**_ANALYZE_AUTH_RESPONSES, **_CONTEXT_NOT_FOUND},
)
def restore_business_context(
    context_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    service: Annotated[BusinessContextService, Depends(get_business_context_service)],
) -> BusinessContextResponse:
    """Restore an owned BusinessContext."""
    context = service.restore(principal, context_id)
    return business_context_response(context)


@router.post(
    "/{context_id}/communications",
    status_code=201,
    response_model=BusinessContextCommunicationLinkResponse,
    summary="Associate a communication with a BusinessContext",
    description=(
        "Creates a manual provenance link from an owned active context to an "
        "owned connector message identified by "
        "``(connector_account_id, provider_message_id)``. Requires "
        "``communications:read`` and ``communications:analyze``. Does not call "
        "mailbox providers, retrieve attachments, or invoke AI. Optional "
        "``analysis_id`` must be owned and match the same provenance."
    ),
    responses={
        **_READ_ANALYZE_AUTH_RESPONSES,
        **_LINK_NOT_FOUND,
        **_LINK_CONFLICT,
        404: {
            "model": ErrorResponse,
            "description": (
                "Business context, connector account, or analysis is unknown "
                "or not owned by the caller."
            ),
        },
    },
)
def associate_communication(
    context_id: UUID,
    request: BusinessContextCommunicationAssociateRequest,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_read_and_analyze),
    ],
    service: Annotated[
        BusinessContextCommunicationLinkService,
        Depends(get_business_context_communication_link_service),
    ],
) -> BusinessContextCommunicationLinkResponse:
    """Associate provider-backed communication provenance with an owned context."""
    link = service.associate(
        principal,
        context_id,
        request.connector_account_id,
        request.provider_message_id,
        analysis_id=request.analysis_id,
    )
    return business_context_communication_link_response(link)


@router.get(
    "/{context_id}/communications",
    response_model=BusinessContextCommunicationLinkListResponse,
    summary="List communication associations for a BusinessContext",
    description=(
        "Returns durable provenance-link metadata for an owned context "
        "(including archived). Does not fetch mailbox content."
    ),
    responses={**_READ_ANALYZE_AUTH_RESPONSES, **_CONTEXT_NOT_FOUND},
)
def list_communications(
    context_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_read_and_analyze),
    ],
    service: Annotated[
        BusinessContextCommunicationLinkService,
        Depends(get_business_context_communication_link_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BusinessContextCommunicationLinkListResponse:
    """List provenance links for an owned BusinessContext."""
    links = service.list_for_context(
        principal,
        context_id,
        limit=limit,
        offset=offset,
    )
    return BusinessContextCommunicationLinkListResponse(
        items=[business_context_communication_link_response(item) for item in links],
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/{context_id}/communications/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remove a communication association",
    description=(
        "Deletes only the provenance link row for an owned context. Allowed for "
        "archived contexts. Does not delete analyses, workflows, connectors, "
        "credentials, or provider mail."
    ),
    responses={
        **_READ_ANALYZE_AUTH_RESPONSES,
        **_LINK_NOT_FOUND,
        204: {"description": "Association removed."},
    },
)
def remove_communication(
    context_id: UUID,
    link_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_read_and_analyze),
    ],
    service: Annotated[
        BusinessContextCommunicationLinkService,
        Depends(get_business_context_communication_link_service),
    ],
) -> Response:
    """Remove an owned provenance association."""
    service.remove(principal, context_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{context_id}/timeline",
    response_model=ContextTimelineListResponse,
    summary="List timeline events for a BusinessContext",
    description=(
        "Returns a bounded, ownership-scoped read model assembled from durable "
        "BusinessContext, communication-link, analysis, attachment-analysis, and "
        "workflow records. Requires ``communications:analyze``. Does not call "
        "mailbox providers, retrieve attachment bytes, or invoke AI. Archive "
        "history is limited to the current archived state when present; restore "
        "transitions are not fabricated."
    ),
    responses={**_ANALYZE_AUTH_RESPONSES, **_CONTEXT_NOT_FOUND},
)
def list_context_timeline(
    context_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_analyze),
    ],
    service: Annotated[ContextTimelineService, Depends(get_context_timeline_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ContextTimelineListResponse:
    """List projected timeline entries for an owned BusinessContext."""
    entries = service.list_timeline(principal, context_id, limit=limit, offset=offset)
    return ContextTimelineListResponse(
        items=[context_timeline_entry_response(item) for item in entries],
        limit=limit,
        offset=offset,
    )
