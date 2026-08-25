"""Gmail mailbox OAuth start and Google callback routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from app.api.dependencies import (
    get_gmail_mailbox_oauth_callback_service,
    get_gmail_mailbox_oauth_service,
    require_authenticated_communications_connect,
)
from app.api.oauth_frontend_return import (
    classify_oauth_callback_failure,
    is_oauth_callback_failure,
    maybe_oauth_frontend_redirect,
)
from app.application.services.gmail_mailbox_oauth import GmailMailboxOAuthService
from app.core.security import AuthenticatedPrincipal
from app.schemas.errors import ErrorResponse
from app.schemas.oauth import (
    GmailAuthorizationCallbackResponse,
    GmailAuthorizationStartResponse,
)

router = APIRouter(tags=["gmail-oauth"])

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
        "description": "Gmail mailbox authorization is currently unavailable.",
    },
}


@router.post(
    "/connector-accounts/gmail/authorize",
    response_model=GmailAuthorizationStartResponse,
    summary="Start Gmail mailbox OAuth authorization",
    description=(
        "Starts a server-side Gmail mailbox consent session for the authenticated "
        "ECI user and returns the Google authorization URL. Requires "
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
def start_gmail_authorization(
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_connect),
    ],
    service: Annotated[
        GmailMailboxOAuthService,
        Depends(get_gmail_mailbox_oauth_service),
    ],
) -> GmailAuthorizationStartResponse:
    """Return the Google authorization URL for a new Gmail mailbox connection."""
    result = service.start_authorization(principal)
    return GmailAuthorizationStartResponse(
        authorization_url=result.authorization_url,
        expires_at=result.expires_at,
    )


@router.get(
    "/oauth/callbacks/gmail",
    response_model=GmailAuthorizationCallbackResponse,
    summary="Complete Gmail mailbox OAuth callback",
    description=(
        "Google redirect target for Gmail mailbox consent. This endpoint does not "
        "use the ECI bearer token. Ownership comes from the authorization session. "
        "Authorization codes and tokens are never returned. When "
        "FRONTEND_OAUTH_RETURN_URL is configured, a 302 returns the browser to "
        "that fixed location after server-side completion. The return target is "
        "never taken from callback query input."
    ),
    responses={
        200: {
            "model": GmailAuthorizationCallbackResponse,
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
            "description": "Gmail mailbox authorization is currently unavailable.",
        },
    },
)
def complete_gmail_authorization(
    service: Annotated[
        GmailMailboxOAuthService,
        Depends(get_gmail_mailbox_oauth_callback_service),
    ],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> GmailAuthorizationCallbackResponse | RedirectResponse:
    """Consume OAuth state and complete Gmail mailbox credential storage."""
    try:
        result = service.complete_authorization(code=code, state=state, error=error)
    except Exception as exc:
        if is_oauth_callback_failure(exc):
            redirected = maybe_oauth_frontend_redirect(
                provider="gmail",
                oauth=classify_oauth_callback_failure(exc),
            )
            if redirected is not None:
                return redirected
        raise
    redirected = maybe_oauth_frontend_redirect(provider="gmail", oauth="success")
    if redirected is not None:
        return redirected
    return GmailAuthorizationCallbackResponse(
        provider=result.provider,
        connector_account_id=result.connector_account_id,
        external_account_id=result.external_account_id,
        status=result.status,
        granted_capabilities=result.granted_capabilities,
    )
