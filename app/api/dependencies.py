"""FastAPI dependency providers."""

from collections.abc import Callable, Iterator
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.gmail_mailbox_oauth import GmailMailboxOAuthService
from app.application.services.identity import IdentityResolver
from app.application.services.microsoft_mailbox_oauth import MicrosoftMailboxOAuthService
from app.application.services.workflow_action_execution import WorkflowActionExecutionService
from app.application.services.workflow_actions import WorkflowActionService
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import (
    COMMUNICATIONS_CONNECT_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticatedPrincipal,
    AuthenticationFailedError,
    AuthorizationFailedError,
    TokenValidator,
)
from app.domain.interfaces import (
    AIProvider,
    CommunicationActionExecutorFactory,
    CommunicationCredentialResolver,
    PersistenceUnitOfWork,
)
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
require_communications_send = require_permission(COMMUNICATIONS_SEND_PERMISSION)
require_communications_connect = require_permission(COMMUNICATIONS_CONNECT_PERMISSION)


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


def require_authenticated_communications_workflow(
    principal: Annotated[
        AuthenticatedPrincipal | None,
        Depends(require_communications_workflow),
    ],
) -> AuthenticatedPrincipal:
    """Require a real authenticated principal for workflow endpoints.

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


def require_authenticated_communications_send(
    principal: Annotated[
        AuthenticatedPrincipal | None,
        Depends(require_communications_send),
    ],
) -> AuthenticatedPrincipal:
    """Require a real authenticated principal for the execute endpoint.

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


def require_authenticated_communications_connect(
    principal: Annotated[
        AuthenticatedPrincipal | None,
        Depends(require_communications_connect),
    ],
) -> AuthenticatedPrincipal:
    """Require a real authenticated principal for mailbox connect operations.

    ``AUTH_MODE=disabled`` yields 401. Missing/invalid tokens remain 401.
    Missing permission remains 403. This permission is distinct from
    ``communications:analyze``, ``communications:workflow``, and
    ``communications:send``.
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


def get_execution_unit_of_work_factory(
    _principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_send),
    ],
) -> UnitOfWorkFactory:
    """Resolve execute persistence only after communications:send succeeds.

    Persistence lookup is performed in this function body so it is not a
    FastAPI sibling of send authorization. Unauthorized requests never
    construct a unit-of-work factory.
    """
    return require_unit_of_work_factory(get_unit_of_work_factory())


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


def get_workflow_action_service(
    identity_resolver: Annotated[IdentityResolver, Depends(get_identity_resolver)],
    uow_factory: Annotated[UnitOfWorkFactory, Depends(require_unit_of_work_factory)],
) -> WorkflowActionService:
    """Build the workflow action service for authenticated workflow endpoints."""
    return WorkflowActionService(identity_resolver, uow_factory)


def get_communication_http_client(
    _principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_send),
    ],
) -> Iterator[httpx.Client]:
    """Yield a request-scoped HTTP client for production write adapters.

    Tests may override this dependency with ``httpx.MockTransport``. The client
    is closed after the request. Construction is gated by send authorization.
    """
    client = httpx.Client(timeout=30.0, follow_redirects=False)
    try:
        yield client
    finally:
        client.close()


def get_communication_credential_resolver(
    _principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_send),
    ],
) -> CommunicationCredentialResolver:
    """Return the execute credential resolver after send authorization.

    Legacy locators use the environment resolver. When mailbox OAuth is enabled
    in a non-production process, ``oauth-`` locators use the shared in-memory
    store. Production does not use the memory store.
    """
    settings = get_settings()
    from app.infrastructure.oauth.runtime import (
        build_runtime_communication_credential_resolver,
        mailbox_oauth_store_available,
    )

    if mailbox_oauth_store_available(settings):
        return build_runtime_communication_credential_resolver(settings)
    from app.infrastructure.credentials.environment import (
        EnvironmentCommunicationCredentialResolver,
    )

    return EnvironmentCommunicationCredentialResolver()


def get_communication_action_executor_factory(
    _principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_send),
    ],
    http_client: Annotated[httpx.Client, Depends(get_communication_http_client)],
    credential_resolver: Annotated[
        CommunicationCredentialResolver,
        Depends(get_communication_credential_resolver),
    ],
) -> CommunicationActionExecutorFactory:
    """Build the account-driven production executor factory after send authorization."""
    from app.infrastructure.executors.factory import ProviderCommunicationActionExecutorFactory

    return ProviderCommunicationActionExecutorFactory(
        credential_resolver=credential_resolver,
        http_client=http_client,
    )


def get_workflow_action_execution_service(
    _principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_send),
    ],
    uow_factory: Annotated[
        UnitOfWorkFactory,
        Depends(get_execution_unit_of_work_factory),
    ],
    executor_factory: Annotated[
        CommunicationActionExecutorFactory,
        Depends(get_communication_action_executor_factory),
    ],
) -> WorkflowActionExecutionService:
    """Build execution orchestration after communications:send authorization."""
    return WorkflowActionExecutionService(
        IdentityResolver(uow_factory),
        uow_factory,
        executor_factory,
    )


def get_gmail_mailbox_oauth_service(
    _principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_connect),
    ],
) -> GmailMailboxOAuthService:
    """Build Gmail OAuth start orchestration after communications:connect.

    Persistence, OAuth adapter, and credential-store construction run in this
    function body so unauthorized requests never reach them.
    """
    return _build_gmail_mailbox_oauth_service()


def get_gmail_mailbox_oauth_callback_service() -> GmailMailboxOAuthService:
    """Build Gmail OAuth callback orchestration without an ECI bearer token."""
    return _build_gmail_mailbox_oauth_service()


def _build_gmail_mailbox_oauth_service() -> GmailMailboxOAuthService:
    settings = get_settings()
    from app.domain.interfaces.communication_credential_store import (
        CommunicationCredentialRecord,
    )
    from app.infrastructure.credentials.locators import create_communication_credential
    from app.infrastructure.oauth.runtime import (
        build_gmail_oauth_client,
        gmail_oauth_connect_available,
        require_shared_oauth_store,
    )

    if not gmail_oauth_connect_available(settings):
        raise ServiceUnavailableError("Gmail mailbox authorization is unavailable.")
    uow_factory = require_unit_of_work_factory(get_unit_of_work_factory())
    store = require_shared_oauth_store(settings)
    oauth_client = build_gmail_oauth_client(settings)

    def create_stored_credential(
        secret_material: bytes,
    ) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="gmail",
            secret_material=secret_material,
        )

    return GmailMailboxOAuthService(
        IdentityResolver(uow_factory),
        uow_factory,
        oauth_client,
        store,
        create_stored_credential,
        session_ttl_seconds=settings.oauth_authorization_session_ttl_seconds,
    )


def get_microsoft_mailbox_oauth_service(
    _principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_communications_connect),
    ],
) -> MicrosoftMailboxOAuthService:
    """Build Microsoft OAuth start orchestration after communications:connect.

    Persistence, OAuth adapter, and credential-store construction run in this
    function body so unauthorized requests never reach them.
    """
    return _build_microsoft_mailbox_oauth_service()


def get_microsoft_mailbox_oauth_callback_service() -> MicrosoftMailboxOAuthService:
    """Build Microsoft OAuth callback orchestration without an ECI bearer token."""
    return _build_microsoft_mailbox_oauth_service()


def _build_microsoft_mailbox_oauth_service() -> MicrosoftMailboxOAuthService:
    settings = get_settings()
    from app.domain.interfaces.communication_credential_store import (
        CommunicationCredentialRecord,
    )
    from app.infrastructure.credentials.locators import create_communication_credential
    from app.infrastructure.oauth.runtime import (
        build_microsoft_oauth_client,
        microsoft_oauth_connect_available,
        require_shared_oauth_store,
    )

    if not microsoft_oauth_connect_available(settings):
        raise ServiceUnavailableError("Microsoft mailbox authorization is unavailable.")
    uow_factory = require_unit_of_work_factory(get_unit_of_work_factory())
    store = require_shared_oauth_store(settings)
    oauth_client = build_microsoft_oauth_client(settings)

    def create_stored_credential(
        secret_material: bytes,
    ) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="microsoft_graph",
            secret_material=secret_material,
        )

    return MicrosoftMailboxOAuthService(
        IdentityResolver(uow_factory),
        uow_factory,
        oauth_client,
        store,
        create_stored_credential,
        session_ttl_seconds=settings.oauth_authorization_session_ttl_seconds,
    )
