"""Minimal platform-owner authorization probe endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import require_owner
from app.core.security import AuthenticatedPrincipal
from app.schemas.admin import AdminPingResponse
from app.schemas.errors import ErrorResponse

router = APIRouter(prefix="/admin", tags=["admin"])

_OWNER_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": "Authenticated caller is not a platform owner.",
    },
    503: {
        "model": ErrorResponse,
        "description": "Persistence is currently unavailable.",
    },
}


@router.get(
    "/ping",
    response_model=AdminPingResponse,
    summary="Owner authorization probe",
    description=(
        "Returns a non-sensitive ok payload when the caller is an authenticated "
        "ECI user with persisted application_role=owner. Establishes the Phase 19 "
        "server-side owner boundary only. Does not list users, expose secrets, "
        "mailbox data, or perform administrative mutations."
    ),
    responses=_OWNER_RESPONSES,
)
def admin_ping(
    _principal: Annotated[AuthenticatedPrincipal, Depends(require_owner)],
) -> AdminPingResponse:
    """Probe that server-side owner authorization succeeded."""
    return AdminPingResponse(status="ok")
