"""Health, liveness, and readiness endpoints."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse

liveness_router = APIRouter(tags=["health"])
router = APIRouter(tags=["health"])


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
def get_readiness() -> ReadinessResponse:
    """Confirm that application configuration loaded successfully."""
    settings = get_settings()
    # Touch required settings to confirm the cached configuration is usable.
    _ = (settings.app_name, settings.app_version, settings.app_env, settings.api_v1_prefix)
    return ReadinessResponse(status="ready")
