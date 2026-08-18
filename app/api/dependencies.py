"""FastAPI dependency providers."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.services.communication_analysis import CommunicationAnalysisService
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import (
    AuthenticatedPrincipal,
    AuthenticationFailedError,
    AuthorizationFailedError,
    TokenValidator,
)
from app.domain.interfaces import AIProvider
from app.providers.factory import create_ai_provider

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")

_AUTHENTICATE_DETAIL = "Not authenticated"
_AUTHORIZE_DETAIL = "Not authorized"
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def get_ai_provider() -> AIProvider:
    """Resolve the configured AI provider for request handling."""
    return create_ai_provider(get_settings())


def get_token_validator() -> TokenValidator | None:
    """Return an OIDC token validator when authentication is enabled."""
    settings = get_settings()
    if settings.auth_mode != "oidc":
        return None
    return TokenValidator.from_settings(settings)


def require_communications_analyze(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    validator: Annotated[TokenValidator | None, Depends(get_token_validator)],
) -> AuthenticatedPrincipal | None:
    """Authenticate the caller and require ``communications:analyze``.

    When ``AUTH_MODE=disabled`` this returns ``None`` without contacting an
    identity provider. When ``AUTH_MODE=oidc``, a valid bearer token with the
    configured permission is required before analysis dependencies run.
    """
    if validator is None:
        return None

    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning("authentication_failed", reason="missing_token")
        raise HTTPException(
            status_code=401,
            detail=_AUTHENTICATE_DETAIL,
            headers=_WWW_AUTHENTICATE,
        )

    try:
        principal = validator.authenticate(credentials.credentials)
    except AuthenticationFailedError as exc:
        logger.warning("authentication_failed", reason=exc.reason)
        raise HTTPException(
            status_code=401,
            detail=_AUTHENTICATE_DETAIL,
            headers=_WWW_AUTHENTICATE,
        ) from None

    logger.info("authentication_succeeded")

    try:
        validator.authorize(principal)
    except AuthorizationFailedError as exc:
        logger.warning(
            "authorization_failed",
            reason=exc.reason,
            required_permission=get_settings().oidc_required_permission,
        )
        raise HTTPException(
            status_code=403,
            detail=_AUTHORIZE_DETAIL,
        ) from None

    return principal


def get_communication_analysis_service(
    _: Annotated[
        AuthenticatedPrincipal | None,
        Depends(require_communications_analyze),
    ],
    provider: AIProvider = Depends(get_ai_provider),
) -> CommunicationAnalysisService:
    """Build the analysis service after authentication and authorization."""
    return CommunicationAnalysisService(provider)
