"""Small helpers for provider-independent operational telemetry."""

from __future__ import annotations

import time
from typing import Any


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
