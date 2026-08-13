"""Shared error response schema for API endpoints."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Generic error payload returned by centralized exception handlers."""

    detail: str = Field(
        examples=["Unsupported AI provider 'azure'. Supported providers: mock, microsoft_foundry"]
    )
