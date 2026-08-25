"""FastAPI application entrypoint for ECI Platform."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middleware import RequestTelemetryMiddleware
from app.api.router import create_api_router
from app.api.routes import health
from app.application.exceptions import (
    AnalysisHasNoDraftReplyError,
    AnalysisNotFoundError,
    ConnectedMailboxNotAvailableError,
    ConnectorAccountConflictError,
    ConnectorAccountNotFoundError,
    MailboxAuthorizationSessionInvalidError,
    MailboxMessageNotFoundError,
    MailboxOAuthAuthorizationDeniedError,
    MailboxPaginationCursorInvalidError,
    WorkflowActionConflictError,
    WorkflowActionNotExecutableError,
    WorkflowActionNotFoundError,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ECIPlatformError,
    MailboxOAuthAuthorizationFailedError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import error_class
from app.domain.exceptions import InvalidWorkflowTransitionError
from app.infrastructure.storage.runtime import dispose_persistence_runtime


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and emit startup/shutdown lifecycle events."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.app_env)
    logger = get_logger(__name__)
    logger.info(
        "application_startup",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )
    yield
    dispose_persistence_runtime()
    logger.info(
        "application_shutdown",
        service=settings.app_name,
        version=settings.app_version,
    )


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    docs_enabled = settings.app_env != "production"

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Enterprise Communication Intelligence Platform with "
            "provider-independent AI architecture."
        ),
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    @application.exception_handler(AnalysisNotFoundError)
    async def analysis_not_found_handler(
        _request: Request,
        exc: AnalysisNotFoundError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("analysis_not_found", error_class=error_class(exc))
        return JSONResponse(status_code=404, content={"detail": exc.message})

    @application.exception_handler(WorkflowActionNotFoundError)
    async def workflow_action_not_found_handler(
        _request: Request,
        exc: WorkflowActionNotFoundError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("workflow_action_not_found", error_class=error_class(exc))
        return JSONResponse(status_code=404, content={"detail": exc.message})

    @application.exception_handler(ConnectorAccountNotFoundError)
    async def connector_account_not_found_handler(
        _request: Request,
        exc: ConnectorAccountNotFoundError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("connector_account_not_found", error_class=error_class(exc))
        return JSONResponse(status_code=404, content={"detail": exc.message})

    @application.exception_handler(ConnectorAccountConflictError)
    async def connector_account_conflict_handler(
        _request: Request,
        exc: ConnectorAccountConflictError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("connector_account_conflict", error_class=error_class(exc))
        return JSONResponse(status_code=409, content={"detail": exc.message})

    @application.exception_handler(ConnectedMailboxNotAvailableError)
    async def connected_mailbox_not_available_handler(
        _request: Request,
        exc: ConnectedMailboxNotAvailableError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("connected_mailbox_not_available", error_class=error_class(exc))
        return JSONResponse(status_code=409, content={"detail": exc.message})

    @application.exception_handler(MailboxMessageNotFoundError)
    async def mailbox_message_not_found_handler(
        _request: Request,
        exc: MailboxMessageNotFoundError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("mailbox_message_not_found", error_class=error_class(exc))
        return JSONResponse(status_code=404, content={"detail": exc.message})

    @application.exception_handler(MailboxPaginationCursorInvalidError)
    async def mailbox_pagination_cursor_invalid_handler(
        _request: Request,
        exc: MailboxPaginationCursorInvalidError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("mailbox_pagination_cursor_invalid", error_class=error_class(exc))
        return JSONResponse(status_code=400, content={"detail": exc.message})

    @application.exception_handler(AnalysisHasNoDraftReplyError)
    async def analysis_has_no_draft_reply_handler(
        _request: Request,
        exc: AnalysisHasNoDraftReplyError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("analysis_has_no_draft_reply", error_class=error_class(exc))
        return JSONResponse(status_code=409, content={"detail": exc.message})

    @application.exception_handler(InvalidWorkflowTransitionError)
    async def invalid_workflow_transition_handler(
        _request: Request,
        exc: InvalidWorkflowTransitionError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("invalid_workflow_transition", error_class=error_class(exc))
        return JSONResponse(status_code=409, content={"detail": exc.message})

    @application.exception_handler(WorkflowActionConflictError)
    async def workflow_action_conflict_handler(
        _request: Request,
        exc: WorkflowActionConflictError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.warning("workflow_action_conflict", error_class=error_class(exc))
        return JSONResponse(status_code=409, content={"detail": exc.message})

    @application.exception_handler(WorkflowActionNotExecutableError)
    async def workflow_action_not_executable_handler(
        _request: Request,
        exc: WorkflowActionNotExecutableError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("workflow_action_not_executable", error_class=error_class(exc))
        return JSONResponse(status_code=409, content={"detail": exc.message})

    @application.exception_handler(MailboxAuthorizationSessionInvalidError)
    async def mailbox_authorization_session_invalid_handler(
        _request: Request,
        exc: MailboxAuthorizationSessionInvalidError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("mailbox_authorization_session_invalid", error_class=error_class(exc))
        return JSONResponse(status_code=400, content={"detail": exc.message})

    @application.exception_handler(MailboxOAuthAuthorizationDeniedError)
    async def mailbox_oauth_authorization_denied_handler(
        _request: Request,
        exc: MailboxOAuthAuthorizationDeniedError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("mailbox_oauth_authorization_denied", error_class=error_class(exc))
        return JSONResponse(status_code=400, content={"detail": exc.message})

    @application.exception_handler(MailboxOAuthAuthorizationFailedError)
    async def mailbox_oauth_authorization_failed_handler(
        _request: Request,
        exc: MailboxOAuthAuthorizationFailedError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.info("mailbox_oauth_authorization_failed", error_class=error_class(exc))
        return JSONResponse(status_code=400, content={"detail": exc.message})

    @application.exception_handler(PersistenceError)
    async def persistence_error_handler(
        _request: Request,
        exc: PersistenceError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.warning("persistence_unavailable", error_class=error_class(exc))
        return JSONResponse(
            status_code=503,
            content={"detail": "Persistence is currently unavailable."},
        )

    @application.exception_handler(ServiceUnavailableError)
    async def service_unavailable_handler(
        _request: Request,
        exc: ServiceUnavailableError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.warning("service_unavailable", error_class=error_class(exc))
        return JSONResponse(status_code=503, content={"detail": exc.message})

    @application.exception_handler(ECIPlatformError)
    async def eci_platform_error_handler(
        _request: Request,
        exc: ECIPlatformError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.error("application_error", error_class=error_class(exc))
        return JSONResponse(status_code=500, content={"detail": exc.message})

    application.add_middleware(RequestTelemetryMiddleware)
    _configure_cors(application, settings)
    application.include_router(health.liveness_router)
    application.include_router(create_api_router())
    return application


def _configure_cors(application: FastAPI, settings: Settings) -> None:
    """Allow only configured browser origins to call the API.

    An empty allowlist keeps the API backend-only. Credentials are never
    enabled; ECI remains a bearer-token API.
    """
    if not settings.cors_allow_origins:
        return
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )


app = create_app()
