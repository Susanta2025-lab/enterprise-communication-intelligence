"""FastAPI application entrypoint for ContextMesh."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import create_api_router
from app.api.routes import health
from app.core.config import get_settings
from app.core.exceptions import ContextMeshError, ServiceUnavailableError
from app.core.logging import configure_logging, get_logger


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
    logger.info(
        "application_shutdown",
        service=settings.app_name,
        version=settings.app_version,
    )


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Enterprise Communication Intelligence Platform with "
            "provider-independent AI architecture."
        ),
        lifespan=lifespan,
    )

    @application.exception_handler(ServiceUnavailableError)
    async def service_unavailable_handler(
        _request: Request,
        exc: ServiceUnavailableError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.warning("service_unavailable", error=exc.message)
        return JSONResponse(status_code=503, content={"detail": exc.message})

    @application.exception_handler(ContextMeshError)
    async def contextmesh_error_handler(
        _request: Request,
        exc: ContextMeshError,
    ) -> JSONResponse:
        logger = get_logger(__name__)
        logger.error("application_error", error=exc.message)
        return JSONResponse(status_code=500, content={"detail": exc.message})

    application.include_router(health.liveness_router)
    application.include_router(create_api_router())
    return application


app = create_app()
