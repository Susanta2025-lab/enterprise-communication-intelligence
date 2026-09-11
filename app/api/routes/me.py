"""Server-authoritative current-user application identity endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import (
    UnitOfWorkFactory,
    authenticate_caller,
    get_unit_of_work_factory,
)
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import ApplicationRole
from app.schemas.errors import ErrorResponse
from app.schemas.me import MeResponse

logger = get_logger(__name__)

router = APIRouter(tags=["me"])

_AUTHENTICATE_DETAIL = "Not authenticated"
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}
_UNAVAILABLE = "Persistence is currently unavailable."
_IDENTITY_UNAVAILABLE = "Application identity is currently unavailable."
_IDENTITY_NOT_FOUND = "Application identity was not found."

_ME_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    404: {
        "model": ErrorResponse,
        "description": "Authenticated caller has no resolved ECI user.",
    },
    503: {
        "model": ErrorResponse,
        "description": "Persistence or application identity is unavailable.",
    },
}


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Current application identity",
    description=(
        "Returns the caller's persisted application_role after verified "
        "(iss, sub) identity resolution. Frontend UX only — not an "
        "authorization mechanism. Does not create users. Does not expose "
        "issuer, subject, email, mailbox identity, or tokens."
    ),
    responses=_ME_RESPONSES,
)
def get_me(
    principal: Annotated[
        AuthenticatedPrincipal | None,
        Depends(authenticate_caller),
    ],
    uow_factory: Annotated[
        UnitOfWorkFactory | None,
        Depends(get_unit_of_work_factory),
    ],
) -> MeResponse:
    """Return server-authoritative application role for the authenticated caller."""
    if principal is None:
        logger.warning("authentication_failed", reason="missing_token", operation="get_me")
        raise HTTPException(
            status_code=401,
            detail=_AUTHENTICATE_DETAIL,
            headers=_WWW_AUTHENTICATE,
        )

    if uow_factory is None:
        logger.warning("persistence_unavailable", operation="get_me")
        raise ServiceUnavailableError(_UNAVAILABLE)

    try:
        with uow_factory() as uow:
            user_id = uow.identity_repository.get_user_id_by_external_identity(
                principal.issuer,
                principal.subject,
            )
            if user_id is None:
                logger.info("me_identity_not_found", operation="get_me")
                raise HTTPException(status_code=404, detail=_IDENTITY_NOT_FOUND)

            role = uow.identity_repository.get_application_role_for_user(user_id)
            if role == ApplicationRole.OWNER.value:
                return MeResponse(application_role="owner", is_owner=True)
            if role == ApplicationRole.USER.value:
                return MeResponse(application_role="user", is_owner=False)

            logger.warning(
                "me_identity_unavailable",
                operation="get_me",
                reason="unsupported_application_role",
            )
            raise HTTPException(status_code=503, detail=_IDENTITY_UNAVAILABLE)
    except PersistenceError as exc:
        logger.warning(
            "persistence_unavailable",
            operation="get_me",
            error_class=type(exc).__name__,
        )
        raise ServiceUnavailableError(_UNAVAILABLE) from None
