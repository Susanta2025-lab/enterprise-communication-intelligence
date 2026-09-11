"""Response schemas for platform admin probe endpoints."""

from pydantic import BaseModel, Field


class AdminPingResponse(BaseModel):
    """Non-sensitive owner-authorization probe payload."""

    status: str = Field(examples=["ok"])
