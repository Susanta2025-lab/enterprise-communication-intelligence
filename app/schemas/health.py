"""Response schemas for health and readiness endpoints."""

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Lightweight platform liveness payload."""

    status: str = Field(examples=["healthy"])


class HealthResponse(BaseModel):
    """Versioned application health metadata.

    ``attachment_scanner`` reports configuration capability only. It does not
    probe the scanner network and never includes host or port.

    ``ai_image_input`` reports whether the configured AI provider currently
    accepts image attachment input (``available`` / ``unavailable``). It does
    not probe Foundry or Bedrock networks.
    """

    status: str = Field(examples=["healthy"])
    service: str = Field(examples=["Enterprise Communication Intelligence Platform"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["development"])
    attachment_scanner: str = Field(examples=["unavailable"])
    ai_image_input: str = Field(examples=["unavailable"])


class ReadinessResponse(BaseModel):
    """Application readiness payload."""

    status: str = Field(examples=["ready"])
