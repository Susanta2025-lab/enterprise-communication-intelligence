"""Authenticated tracking with explicit verified provenance and confirmation."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.dependencies import (
    get_work_item_service,
    require_authenticated_communications_analyze,
)
from app.application.services.work_items import WorkItemService
from app.core.security import AuthenticatedPrincipal
from app.domain.models.business_work_item import WorkItemCommand, WorkItemEdit
from app.domain.models.work_item_provenance import CandidateQuery
from app.domain.models.work_item_query import WorkItemQuery
from app.schemas.errors import ErrorResponse
from app.schemas.work_items import (
    WorkItemCandidateListResponse,
    WorkItemCreateRequest,
    WorkItemDetailResponse,
    WorkItemEventListResponse,
    WorkItemEventResponse,
    WorkItemFromAnalysisRequest,
    WorkItemListResponse,
    WorkItemPatchRequest,
    WorkItemResponse,
    WorkItemStatusRequest,
    WorkItemVersionRequest,
    item_response,
)


class TrackingRoute(APIRoute):
    """Do not echo business content, unknown field names or locators in errors."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Only schema-owned top-level field names may enter the response.
                # Pydantic messages, inputs, contexts and unknown keys are untrusted.
                fields = (
                    WorkItemCreateRequest.model_fields.keys()
                    | WorkItemFromAnalysisRequest.model_fields.keys()
                    | WorkItemPatchRequest.model_fields.keys()
                    | WorkItemStatusRequest.model_fields.keys()
                    | WorkItemQuery.model_fields.keys()
                    | CandidateQuery.model_fields.keys()
                    | {"item_id"}
                )
                invalid = sorted({
                    error["loc"][1]
                    for error in exc.errors()
                    if len(error["loc"]) > 1 and error["loc"][1] in fields
                })
                detail = "Invalid work item request."
                if invalid:
                    detail += " Review fields: " + ", ".join(invalid) + "."
                return JSONResponse(
                    status_code=422,
                    content=ErrorResponse(detail=detail).model_dump(exclude_none=True)
                )

        return validated


router = APIRouter(
    prefix="/work-items",
    route_class=TrackingRoute,
    tags=["work-items"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)},
)
Principal = Annotated[AuthenticatedPrincipal, Depends(require_authenticated_communications_analyze)]
Service = Annotated[WorkItemService, Depends(get_work_item_service)]


@router.post(
    "",
    status_code=201,
    response_model=WorkItemResponse,
    responses={200: {"model": WorkItemResponse, "description": "Owned creation replay."}},
)
def create_work_item(
    body: WorkItemCreateRequest,
    request: Request,
    response: Response,
    principal: Principal,
    service: Service,
):
    result = service.create_verified(principal, body)
    response.status_code = 200 if result.replayed else 201
    response.headers["Location"] = request.url_for("get_work_item", item_id=result.item.id).path
    return item_response(result.item, datetime.now(UTC))


@router.get("", response_model=WorkItemListResponse)
def list_work_items(
    principal: Principal, service: Service, query: Annotated[WorkItemQuery, Query()]
):
    now = datetime.now(UTC)
    items = service.list(principal, query, now)
    return WorkItemListResponse(
        items=[item_response(i, now) for i in items], limit=query.limit, offset=query.offset
    )


@router.get("/candidates", response_model=WorkItemCandidateListResponse)
def work_item_candidates(
    principal: Principal, service: Service, query: Annotated[CandidateQuery, Query()]
):
    return WorkItemCandidateListResponse(
        items=service.candidates(principal, query),
        limit=query.limit,
        offset=query.offset,
    )


@router.post(
    "/from-analysis",
    status_code=201,
    response_model=WorkItemResponse,
    responses={200: {"model": WorkItemResponse, "description": "Owned creation replay."}},
)
def create_work_item_from_analysis(
    body: WorkItemFromAnalysisRequest,
    request: Request,
    response: Response,
    principal: Principal,
    service: Service,
):
    result = service.create_verified(principal, body)
    response.status_code = 200 if result.replayed else 201
    response.headers["Location"] = request.url_for("get_work_item", item_id=result.item.id).path
    return item_response(result.item, datetime.now(UTC))


@router.get("/{item_id}", response_model=WorkItemDetailResponse)
def get_work_item(item_id: UUID, principal: Principal, service: Service):
    item, sources = service.detail(principal, item_id)
    return item_response(item, datetime.now(UTC), detail=True).model_copy(
        update={"sources": sources}
    )


@router.patch("/{item_id}", response_model=WorkItemResponse)
def patch_work_item(
    item_id: UUID, body: WorkItemPatchRequest, principal: Principal, service: Service
):
    edit = WorkItemEdit(**body.model_dump(exclude={"expected_version"}, exclude_unset=True))
    command = WorkItemCommand(operation="edit", expected_version=body.expected_version, edit=edit)
    return item_response(service.mutate(principal, item_id, command), datetime.now(UTC))


@router.post("/{item_id}/status", response_model=WorkItemResponse)
def status_work_item(
    item_id: UUID, body: WorkItemStatusRequest, principal: Principal, service: Service
):
    command = WorkItemCommand(operation="status", **body.model_dump())
    return item_response(service.mutate(principal, item_id, command), datetime.now(UTC))


@router.post("/{item_id}/archive", response_model=WorkItemResponse)
def archive_work_item(
    item_id: UUID, body: WorkItemVersionRequest, principal: Principal, service: Service
):
    command = WorkItemCommand(operation="archive", expected_version=body.expected_version)
    return item_response(service.mutate(principal, item_id, command), datetime.now(UTC))


@router.post("/{item_id}/restore", response_model=WorkItemResponse)
def restore_work_item(
    item_id: UUID, body: WorkItemVersionRequest, principal: Principal, service: Service
):
    command = WorkItemCommand(operation="restore", expected_version=body.expected_version)
    return item_response(service.mutate(principal, item_id, command), datetime.now(UTC))


@router.get("/{item_id}/events", response_model=WorkItemEventListResponse)
def work_item_events(
    item_id: UUID,
    principal: Principal,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    events = service.events(principal, item_id, limit=limit, offset=offset)
    return WorkItemEventListResponse(
        items=[
            WorkItemEventResponse(**event.model_dump(exclude={"owner_user_id", "actor_user_id"}))
            for event in events
        ],
        limit=limit,
        offset=offset,
    )
