"""Response schemas for health and readiness endpoints."""

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Lightweight platform liveness payload."""

    status: str = Field(examples=["healthy"])


class HealthResponse(BaseModel):
    """Versioned application health metadata."""

    status: str = Field(examples=["healthy"])
    service: str = Field(examples=["Enterprise Communication Intelligence Platform"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["development"])


class ReadinessResponse(BaseModel):
    """Application readiness payload."""

    status: str = Field(examples=["ready"])
