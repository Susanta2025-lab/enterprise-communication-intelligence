"""Main API router assembly."""

from fastapi import APIRouter

from app.api.routes import communications, health
from app.core.config import get_settings


def create_api_router() -> APIRouter:
    """Create the versioned API router using the configured prefix."""
    settings = get_settings()
    api_router = APIRouter()
    api_router.include_router(health.router, prefix=settings.api_v1_prefix)
    api_router.include_router(communications.router, prefix=settings.api_v1_prefix)
    return api_router
