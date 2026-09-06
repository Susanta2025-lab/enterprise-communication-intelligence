"""Shared error response schema for API endpoints."""

from pydantic import BaseModel, Field

from app.core.exceptions import ECIPlatformError


class ErrorResponse(BaseModel):
    """Generic error payload returned by centralized exception handlers.

    ``code`` is optional and currently used only for attachment-analysis
    failures so clients can distinguish security, parser, and scanner cases
    without matching message text. Other routes omit it.
    """

    detail: str = Field(
        examples=["Unsupported AI provider 'azure'. Supported providers: mock, microsoft_foundry"]
    )
    code: str | None = Field(default=None, examples=["attachment_security_blocked"])


def error_payload(exc: ECIPlatformError) -> dict[str, str]:
    """Return a public error body. Include ``code`` only when the type defines one."""
    payload = {"detail": exc.message}
    code = getattr(type(exc), "code", None)
    if isinstance(code, str) and code:
        payload["code"] = code
    return payload
