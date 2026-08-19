"""FastAPI application entrypoint for ECI Platform."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.middleware import RequestTelemetryMiddleware
from app.api.router import create_api_router
from app.api.routes import health
from app.application.exceptions import AnalysisNotFoundError
from app.core.config import get_settings
from app.core.exceptions import ECIPlatformError, PersistenceError, ServiceUnavailableError
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import error_class
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
    application.include_router(health.liveness_router)
    application.include_router(create_api_router())
    return application


app = create_app()
