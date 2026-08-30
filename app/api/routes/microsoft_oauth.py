"""Microsoft Graph mailbox OAuth start and Microsoft callback routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from app.api.dependencies import (
    get_microsoft_mailbox_oauth_callback_service,
    get_microsoft_mailbox_oauth_service,
    require_authenticated_communications_connect,
)
from app.api.oauth_frontend_return import (
    classify_oauth_callback_failure,
    is_oauth_callback_failure,
    maybe_oauth_frontend_redirect,
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


@router.post(
    "/connector-accounts/microsoft_graph/authorize/another",
    response_model=MicrosoftAuthorizationStartResponse,
    summary="Start Microsoft mailbox OAuth for a different account",
    description=(
        "Starts a server-side Microsoft mailbox consent session that asks the "
        "identity platform to let the user choose an account. Requires "
        "communications:connect. This does not bind or mutate an existing "
        "connector row. Reconnect remains exact-account only. Callers cannot "
        "supply scopes, redirect URIs, or credential locators. This is not ECI login."
    ),
    responses={
        **_CONNECT_AUTH_RESPONSES,
        400: {
            "model": ErrorResponse,
            "description": "Mailbox authorization could not be started.",
        },
    },
)
def start_microsoft_connect_another_authorization(
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_connect),
    ],
    service: Annotated[
        MicrosoftMailboxOAuthService,
        Depends(get_microsoft_mailbox_oauth_service),
    ],
) -> MicrosoftAuthorizationStartResponse:
    """Return the Microsoft authorization URL for connecting a different Outlook account."""
    result = service.start_connect_another(principal)
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
        "Authorization codes and tokens are never returned. When "
        "FRONTEND_OAUTH_RETURN_URL is configured, a 302 returns the browser to "
        "that fixed location after server-side completion. The return target is "
        "never taken from callback query input."
    ),
    responses={
        200: {
            "model": MicrosoftAuthorizationCallbackResponse,
            "description": "Sanitized JSON result when no frontend return URL is configured.",
        },
        302: {
            "description": "Redirect to the configured frontend return URL.",
        },
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
) -> MicrosoftAuthorizationCallbackResponse | RedirectResponse:
    """Consume OAuth state and complete Microsoft mailbox credential storage."""
    try:
        result = service.complete_authorization(code=code, state=state, error=error)
    except Exception as exc:
        if is_oauth_callback_failure(exc):
            redirected = maybe_oauth_frontend_redirect(
                provider="microsoft_graph",
                oauth=classify_oauth_callback_failure(exc),
            )
            if redirected is not None:
                return redirected
        raise
    redirected = maybe_oauth_frontend_redirect(provider="microsoft_graph", oauth="success")
    if redirected is not None:
        return redirected
    return MicrosoftAuthorizationCallbackResponse(
        provider=result.provider,
        connector_account_id=result.connector_account_id,
        status=result.status,
        granted_capabilities=result.granted_capabilities,
    )
