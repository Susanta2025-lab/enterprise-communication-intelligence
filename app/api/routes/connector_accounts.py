"""Owned connector-account disconnect and reauthorization routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_connector_account_oauth_service,
    get_connector_account_service,
    require_authenticated_communications_connect,
)
from app.application.services.connector_account_oauth import ConnectorAccountOAuthService
from app.application.services.connector_accounts import ConnectorAccountService
from app.core.security import AuthenticatedPrincipal
from app.schemas.errors import ErrorResponse
from app.schemas.oauth import (
    ConnectorAccountReauthorizeResponse,
    ConnectorAccountResponse,
)

router = APIRouter(tags=["connector-accounts"])

_CONNECT_AUTH_RESPONSES = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid bearer token.",
    },
    403: {
        "model": ErrorResponse,
        "description": "Authenticated caller lacks communications:connect.",
    },
    404: {
        "model": ErrorResponse,
        "description": "Connector account is unknown or not owned by the caller.",
    },
    503: {
        "model": ErrorResponse,
        "description": "Connector-account lifecycle is currently unavailable.",
    },
}


@router.post(
    "/connector-accounts/{connector_account_id}/disconnect",
    response_model=ConnectorAccountResponse,
    summary="Disconnect an owned connector account",
    description=(
        "Removes ECI's stored delegated mailbox credential for the owned account "
        "and marks it disconnected. Requires communications:connect. Repeated "
        "disconnect is idempotent. Unknown and cross-user ids are indistinguishable. "
        "Credential locators and tokens are never returned. Google grant revocation "
        "is best-effort after local credential removal. Microsoft-side application "
        "consent is not revoked by this operation."
    ),
    responses={
        **_CONNECT_AUTH_RESPONSES,
        200: {
            "model": ConnectorAccountResponse,
            "description": "Disconnected connector account metadata.",
        },
    },
)
def disconnect_connector_account(
    connector_account_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_connect),
    ],
    service: Annotated[
        ConnectorAccountService,
        Depends(get_connector_account_service),
    ],
) -> ConnectorAccountResponse:
    """Disconnect an owned connector account and delete local credential material."""
    result = service.disconnect_owned(principal, connector_account_id)
    return ConnectorAccountResponse(
        id=result.id,
        provider=result.provider,
        external_account_id=result.external_account_id,
        status=result.status,
        granted_capabilities=result.granted_capabilities,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.post(
    "/connector-accounts/{connector_account_id}/reauthorize",
    response_model=ConnectorAccountReauthorizeResponse,
    summary="Start mailbox OAuth reauthorization",
    description=(
        "Starts a server-side mailbox consent session bound to the owned "
        "connector account. Requires communications:connect. The account's "
        "stored provider is used; callers cannot switch provider or supply "
        "scopes. ACTIVE accounts are rejected. DISCONNECTED and REAUTH_REQUIRED "
        "accounts are accepted. This is not ECI login."
    ),
    responses={
        **_CONNECT_AUTH_RESPONSES,
        400: {
            "model": ErrorResponse,
            "description": "Mailbox reauthorization could not be started.",
        },
        409: {
            "model": ErrorResponse,
            "description": "Connector account is not in a reauthorizable lifecycle state.",
        },
    },
)
def reauthorize_connector_account(
    connector_account_id: UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_connect),
    ],
    service: Annotated[
        ConnectorAccountOAuthService,
        Depends(get_connector_account_oauth_service),
    ],
) -> ConnectorAccountReauthorizeResponse:
    """Return the provider authorization URL for an owned reauthorize session."""
    result = service.start_reauthorization(principal, connector_account_id)
    return ConnectorAccountReauthorizeResponse(
        authorization_url=result.authorization_url,
        expires_at=result.expires_at,
    )
