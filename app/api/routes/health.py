"""Health, liveness, and readiness endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_database_readiness_probe
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse

liveness_router = APIRouter(tags=["health"])
router = APIRouter(tags=["health"])

_UNAVAILABLE = "Persistence is currently unavailable."


@liveness_router.get("/health", response_model=LivenessResponse)
def get_liveness() -> LivenessResponse:
    """Return a lightweight platform-level liveness signal."""
    return LivenessResponse(status="healthy")


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return structured application health metadata."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get("/readiness", response_model=ReadinessResponse)
def get_readiness(
    database_probe: Annotated[
        Callable[[], bool] | None,
        Depends(get_database_readiness_probe),
    ],
) -> ReadinessResponse:
    """Confirm that configuration loaded and, when configured, the database responds."""
    settings = get_settings()
    # Touch required settings to confirm the cached configuration is usable.
    _ = (settings.app_name, settings.app_version, settings.app_env, settings.api_v1_prefix)
    if database_probe is not None and not database_probe():
        raise ServiceUnavailableError(_UNAVAILABLE)
    return ReadinessResponse(status="ready")
