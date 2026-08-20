"""FastAPI dependency providers."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import (
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticatedPrincipal,
    AuthenticationFailedError,
    AuthorizationFailedError,
    TokenValidator,
)
from app.domain.interfaces import AIProvider, PersistenceUnitOfWork
from app.providers.factory import create_ai_provider

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")

_AUTHENTICATE_DETAIL = "Not authenticated"
_AUTHORIZE_DETAIL = "Not authorized"
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}
_UNAVAILABLE = "Persistence is currently unavailable."

UnitOfWorkFactory = Callable[[], PersistenceUnitOfWork]


def get_ai_provider() -> AIProvider:
    """Resolve the configured AI provider for request handling."""
    return create_ai_provider(get_settings())


def get_token_validator() -> TokenValidator | None:
    """Return an OIDC token validator when authentication is enabled."""
    settings = get_settings()
    if settings.auth_mode != "oidc":
        return None
    return TokenValidator.from_settings(settings)


def authenticate_caller(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    validator: Annotated[TokenValidator | None, Depends(get_token_validator)],
) -> AuthenticatedPrincipal | None:
    """Authenticate the caller without checking a capability permission.

    When ``AUTH_MODE=disabled`` this returns ``None`` without contacting an
    identity provider. When ``AUTH_MODE=oidc``, a valid bearer token is
    required. Permission checks happen in ``require_permission`` and
    ``require_communications_analyze``.
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
    return principal


def _enforce_permission(
    principal: AuthenticatedPrincipal | None,
    validator: TokenValidator | None,
    required_permission: str,
) -> AuthenticatedPrincipal | None:
    """Require ``required_permission`` after authentication."""
    if validator is None:
        return None

    if principal is None:
        logger.warning("authentication_failed", reason="missing_token")
        raise HTTPException(
            status_code=401,
            detail=_AUTHENTICATE_DETAIL,
            headers=_WWW_AUTHENTICATE,
        )

    try:
        validator.authorize(principal, required_permission)
    except AuthorizationFailedError as exc:
        logger.warning(
            "authorization_failed",
            reason=exc.reason,
            required_permission=required_permission,
        )
        raise HTTPException(
            status_code=403,
            detail=_AUTHORIZE_DETAIL,
        ) from None

    return principal


def require_permission(
    required_permission: str,
) -> Callable[..., AuthenticatedPrincipal | None]:
    """Return a dependency that authenticates and requires a specific permission."""
    if not required_permission.strip():
        raise ValueError("required_permission must not be empty")

    def require_named_permission(
        principal: Annotated[
            AuthenticatedPrincipal | None,
            Depends(authenticate_caller),
        ],
        validator: Annotated[TokenValidator | None, Depends(get_token_validator)],
    ) -> AuthenticatedPrincipal | None:
        return _enforce_permission(principal, validator, required_permission)

    require_named_permission.__name__ = (
        f"require_permission_{required_permission.replace(':', '_')}"
    )
    require_named_permission.__doc__ = (
        f"Authenticate the caller and require ``{required_permission}``."
    )
    return require_named_permission


def require_communications_analyze(
    principal: Annotated[
        AuthenticatedPrincipal | None,
        Depends(authenticate_caller),
    ],
    validator: Annotated[TokenValidator | None, Depends(get_token_validator)],
) -> AuthenticatedPrincipal | None:
    """Authenticate the caller and require ``communications:analyze``.

    When ``AUTH_MODE=disabled`` this returns ``None`` without contacting an
    identity provider. When ``AUTH_MODE=oidc``, a valid bearer token with the
    configured permission (``OIDC_REQUIRED_PERMISSION``) is required before
    analysis dependencies run.
    """
    return _enforce_permission(
        principal,
        validator,
        get_settings().oidc_required_permission,
    )


require_communications_workflow = require_permission(COMMUNICATIONS_WORKFLOW_PERMISSION)


def require_authenticated_communications_analyze(
    principal: Annotated[
        AuthenticatedPrincipal | None,
        Depends(require_communications_analyze),
    ],
) -> AuthenticatedPrincipal:
    """Require a real authenticated principal for history endpoints.

    ``AUTH_MODE=disabled`` yields 401. Missing/invalid tokens remain 401.
    Missing permission remains 403.
    """
    if principal is None:
        logger.warning("authentication_failed", reason="missing_token")
        raise HTTPException(
            status_code=401,
            detail=_AUTHENTICATE_DETAIL,
            headers=_WWW_AUTHENTICATE,
        )
    return principal


def get_unit_of_work_factory() -> UnitOfWorkFactory | None:
    """Return a persistence unit-of-work factory when DATABASE_URL is configured."""
    settings = get_settings()
    if not settings.database_url:
        return None
    from app.infrastructure.storage.runtime import get_unit_of_work_factory as build_factory

    return build_factory(settings.database_url)


def get_database_readiness_probe() -> Callable[[], bool] | None:
    """Return a SQLAlchemy-free database probe when persistence is configured."""
    settings = get_settings()
    if not settings.database_url:
        return None
    from app.infrastructure.storage.runtime import probe_database_readiness

    url = settings.database_url

    def _probe() -> bool:
        return probe_database_readiness(url)

    return _probe


def require_unit_of_work_factory(
    factory: Annotated[UnitOfWorkFactory | None, Depends(get_unit_of_work_factory)],
) -> UnitOfWorkFactory:
    """Require persistence for history endpoints."""
    if factory is None:
        logger.warning("persistence_unavailable", operation="history")
        raise ServiceUnavailableError(_UNAVAILABLE)
    return factory


def get_communication_analysis_service(
    provider: AIProvider = Depends(get_ai_provider),
) -> CommunicationAnalysisService:
    """Build the AI-only analysis service from the configured provider."""
    return CommunicationAnalysisService(provider)


def get_communication_analysis_workflow_service(
    principal: Annotated[
        AuthenticatedPrincipal | None,
        Depends(require_communications_analyze),
    ],
    analysis_service: Annotated[
        CommunicationAnalysisService,
        Depends(get_communication_analysis_service),
    ],
    uow_factory: Annotated[UnitOfWorkFactory | None, Depends(get_unit_of_work_factory)],
) -> CommunicationAnalysisWorkflowService:
    """Build persistence-aware analysis orchestration after authorization."""
    identity_resolver = IdentityResolver(uow_factory) if uow_factory is not None else None
    history_service = AnalysisHistoryService(uow_factory) if uow_factory is not None else None
    return CommunicationAnalysisWorkflowService(
        analysis_service,
        principal=principal,
        identity_resolver=identity_resolver,
        history_service=history_service,
    )


def get_identity_resolver(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(require_unit_of_work_factory)],
) -> IdentityResolver:
    """Build an identity resolver for history endpoints."""
    return IdentityResolver(uow_factory)


def get_analysis_history_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(require_unit_of_work_factory)],
) -> AnalysisHistoryService:
    """Build the analysis history service for authenticated history endpoints."""
    return AnalysisHistoryService(uow_factory)
