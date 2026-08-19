"""Small helpers for provider-independent operational telemetry."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import structlog


def elapsed_ms(started_at: float) -> float:
    """Return elapsed milliseconds from a ``time.perf_counter()`` start mark."""
    return max(0.0, (time.perf_counter() - started_at) * 1000)


def error_class(exc: BaseException) -> str:
    """Return a bounded exception class name for structured logs."""
    return type(exc).__name__


def resolve_provider_name(provider: Any) -> str:
    """Return a stable provider identifier when one is available."""
    name = getattr(provider, "PROVIDER_NAME", None)
    if isinstance(name, str) and name.strip():
        return name
    return type(provider).__name__


def bound_request_id_as_uuid() -> UUID | None:
    """Return the bound request ID when it is a UUID, otherwise None.

    Incoming ``X-Request-ID`` values are ignored by middleware. The server
    currently emits UUID request IDs; non-UUID values are stored as null.
    """
    try:
        value = structlog.contextvars.get_contextvars().get("request_id")
    except Exception:
        return None
    if not isinstance(value, str) or not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
