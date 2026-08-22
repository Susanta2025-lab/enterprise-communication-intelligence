"""REST endpoints for approval-gated workflow actions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_workflow_action_execution_service,
    get_workflow_action_service,
    require_authenticated_communications_send,
    require_authenticated_communications_workflow,
)
from app.application.services.workflow_action_execution import WorkflowActionExecutionService
from app.application.services.workflow_actions import WorkflowActionService
from app.core.security import AuthenticatedPrincipal
from app.schemas.errors import ErrorResponse
from app.schemas.workflow import (
    WorkflowActionCreateRequest,
    WorkflowActionListResponse,
    WorkflowActionResponse,
    workflow_action_response,
)

router = APIRouter(prefix="/workflow-actions", tags=["workflow-actions"])

_WORKFLOW_AUTH_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": "Authenticated caller lacks communications:workflow.",
    },
    503: {
        "model": ErrorResponse,
        "description": "Persistence is currently unavailable.",
    },
}

_WORKFLOW_NOT_FOUND = {
    404: {
        "model": ErrorResponse,
        "description": "Workflow action is unknown or not owned by the caller.",
    },
}

_WORKFLOW_CONFLICT = {
    409: {
        "model": ErrorResponse,
        "description": "Invalid workflow state transition or concurrent update.",
    },
}

_SEND_AUTH_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": "Authenticated caller lacks communications:send.",
    },
    503: {
        "model": ErrorResponse,
        "description": (
            "Persistence, credential material, or the mailbox provider is currently "
            "unavailable. If provider execution had already begun, the action may "
            "remain EXECUTING."
        ),
    },
}


@router.post(
    "",
    status_code=201,
    response_model=WorkflowActionResponse,
    summary="Create a workflow action proposal",
    description=(
        "Creates a PENDING reply workflow action by snapshotting the draft reply "
        "from an analysis owned by the authenticated caller. The request accepts "
        "only analysis_id; callers cannot supply status, action type, or reply text."
    ),
    responses={
        **_WORKFLOW_AUTH_RESPONSES,
        404: {
            "model": ErrorResponse,
            "description": "Analysis is unknown or not owned by the caller.",
        },
        409: {
            "model": ErrorResponse,
            "description": "Analysis has no usable draft reply.",
        },
    },
)
def create_workflow_action(
    request: WorkflowActionCreateRequest,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_workflow),
    ],
    service: Annotated[WorkflowActionService, Depends(get_workflow_action_service)],
) -> WorkflowActionResponse:
    """Create a pending workflow action from an owned analysis draft reply."""
    action = service.create(principal, request.analysis_id)
    return workflow_action_response(action)


@router.get(
    "",
    response_model=WorkflowActionListResponse,
    summary="List owned workflow actions",
    description=(
        "Returns a bounded page of workflow actions owned by the authenticated caller. "
        "Callers without an identity mapping receive an empty page."
    ),
    responses=_WORKFLOW_AUTH_RESPONSES,
)
def list_workflow_actions(
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_workflow),
    ],
    service: Annotated[WorkflowActionService, Depends(get_workflow_action_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkflowActionListResponse:
    """List workflow actions owned by the current authenticated user."""
    actions = service.list(principal, limit, offset)
    return WorkflowActionListResponse(
        items=[workflow_action_response(action) for action in actions],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{action_id}",
    response_model=WorkflowActionResponse,
    summary="Get an owned workflow action",
    description=(
        "Returns one workflow action when it is owned by the authenticated caller. "
        "The referenced analysis is not dereferenced and may have been deleted."
    ),
    responses={
        **_WORKFLOW_AUTH_RESPONSES,
        **_WORKFLOW_NOT_FOUND,
    },
)
def get_workflow_action(
    action_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_workflow),
    ],
    service: Annotated[WorkflowActionService, Depends(get_workflow_action_service)],
) -> WorkflowActionResponse:
    """Return an owned workflow action. Unknown and cross-user ids are indistinguishable."""
    action = service.get(principal, action_id)
    return workflow_action_response(action)


@router.post(
    "/{action_id}/approve",
    response_model=WorkflowActionResponse,
    summary="Approve a pending workflow action",
    description=(
        "Approves a PENDING workflow action owned by the authenticated caller. "
        "The approved reply is copied from the stored proposal. The request has no body."
    ),
    responses={
        **_WORKFLOW_AUTH_RESPONSES,
        **_WORKFLOW_NOT_FOUND,
        **_WORKFLOW_CONFLICT,
    },
)
def approve_workflow_action(
    action_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_workflow),
    ],
    service: Annotated[WorkflowActionService, Depends(get_workflow_action_service)],
) -> WorkflowActionResponse:
    """Approve an owned pending workflow action."""
    action = service.approve(principal, action_id)
    return workflow_action_response(action)


@router.post(
    "/{action_id}/reject",
    response_model=WorkflowActionResponse,
    summary="Reject a pending workflow action",
    description=(
        "Rejects a PENDING workflow action owned by the authenticated caller. "
        "The request has no body and does not accept a rejection reason."
    ),
    responses={
        **_WORKFLOW_AUTH_RESPONSES,
        **_WORKFLOW_NOT_FOUND,
        **_WORKFLOW_CONFLICT,
    },
)
def reject_workflow_action(
    action_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_workflow),
    ],
    service: Annotated[WorkflowActionService, Depends(get_workflow_action_service)],
) -> WorkflowActionResponse:
    """Reject an owned pending workflow action."""
    action = service.reject(principal, action_id)
    return workflow_action_response(action)


@router.post(
    "/{action_id}/execute",
    response_model=WorkflowActionResponse,
    summary="Execute an approved workflow action",
    description=(
        "Executes an owned APPROVED workflow action through the mailbox account "
        "snapshotted at proposal time. The request has no body. Callers cannot "
        "supply reply text, provider, connector account, credentials, or a "
        "provider message id. A recorded terminal FAILED outcome is returned as "
        "HTTP 200 with status FAILED. Uncertain provider or credential failures "
        "return 503 and may leave the action EXECUTING."
    ),
    responses={
        **_SEND_AUTH_RESPONSES,
        **_WORKFLOW_NOT_FOUND,
        409: {
            "model": ErrorResponse,
            "description": (
                "Workflow action is not executable, is not APPROVED, or was "
                "updated concurrently."
            ),
        },
        200: {
            "model": WorkflowActionResponse,
            "description": (
                "Terminal EXECUTED or FAILED workflow action. FAILED means the "
                "provider definitely rejected the send and that outcome was stored."
            ),
        },
    },
)
def execute_workflow_action(
    action_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_send),
    ],
    service: Annotated[
        WorkflowActionExecutionService,
        Depends(get_workflow_action_execution_service),
    ],
) -> WorkflowActionResponse:
    """Execute an owned approved workflow action using the stored snapshot."""
    action = service.execute(principal, action_id)
    return workflow_action_response(action)
