"""Microsoft Graph mailbox OAuth start and Microsoft callback routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_microsoft_mailbox_oauth_callback_service,
    get_microsoft_mailbox_oauth_service,
    require_authenticated_communications_connect,
)
from app.application.services.microsoft_mailbox_oauth import MicrosoftMailboxOAuthService
from app.core.security import AuthenticatedPrincipal
from app.schemas.errors import ErrorResponse
from app.schemas.oauth import (
    MicrosoftAuthorizationCallbackResponse,
    MicrosoftAuthorizationStartResponse,
)

router = APIRouter(tags=["microsoft-oauth"])

_CONNECT_AUTH_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": "Authenticated caller lacks communications:connect.",
    },
    503: {
        "model": ErrorResponse,
        "description": "Microsoft mailbox authorization is currently unavailable.",
    },
}


@router.post(
    "/connector-accounts/microsoft_graph/authorize",
    response_model=MicrosoftAuthorizationStartResponse,
    summary="Start Microsoft mailbox OAuth authorization",
    description=(
        "Starts a server-side Microsoft mailbox consent session for the authenticated "
        "ECI user and returns the Microsoft identity platform authorization URL. Requires "
        "communications:connect. Callers cannot supply scopes, redirect URIs, "
        "or credential locators. This is not ECI login."
    ),
    responses={
        **_CONNECT_AUTH_RESPONSES,
        400: {
            "model": ErrorResponse,
            "description": "Mailbox authorization could not be started.",
        },
    },
)
def start_microsoft_authorization(
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_connect),
    ],
    service: Annotated[
        MicrosoftMailboxOAuthService,
        Depends(get_microsoft_mailbox_oauth_service),
    ],
) -> MicrosoftAuthorizationStartResponse:
    """Return the Microsoft authorization URL for a new Graph mailbox connection."""
    result = service.start_authorization(principal)
    return MicrosoftAuthorizationStartResponse(
        authorization_url=result.authorization_url,
        expires_at=result.expires_at,
    )


@router.get(
    "/oauth/callbacks/microsoft_graph",
    response_model=MicrosoftAuthorizationCallbackResponse,
    summary="Complete Microsoft mailbox OAuth callback",
    description=(
        "Microsoft redirect target for Graph mailbox consent. This endpoint does not "
        "use the ECI bearer token. Ownership comes from the authorization session. "
        "Authorization codes and tokens are never returned."
    ),
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Mailbox authorization was denied or could not be completed.",
        },
        503: {
            "model": ErrorResponse,
            "description": "Microsoft mailbox authorization is currently unavailable.",
        },
    },
)
def complete_microsoft_authorization(
    service: Annotated[
        MicrosoftMailboxOAuthService,
        Depends(get_microsoft_mailbox_oauth_callback_service),
    ],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> MicrosoftAuthorizationCallbackResponse:
    """Consume OAuth state and complete Microsoft mailbox credential storage."""
    result = service.complete_authorization(code=code, state=state, error=error)
    return MicrosoftAuthorizationCallbackResponse(
        provider=result.provider,
        connector_account_id=result.connector_account_id,
        external_account_id=result.external_account_id,
        status=result.status,
        granted_capabilities=result.granted_capabilities,
    )
