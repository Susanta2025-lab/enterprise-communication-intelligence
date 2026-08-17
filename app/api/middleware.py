"""HTTP request telemetry middleware."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class

logger = get_logger(__name__)

_REQUEST_ID_HEADER = b"x-request-id"


class RequestTelemetryMiddleware:
    """Bind a server-generated request ID and emit HTTP lifecycle events.

    Uses a raw ASGI wrapper so ``structlog.contextvars`` stay request-local
    and are not affected by BaseHTTPMiddleware task isolation.
    Incoming ``X-Request-ID`` values are ignored.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        method = scope["method"]
        path = scope["path"]
        started_at = time.perf_counter()
        status_code = 500

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        logger.info("http_request_started", method=method, path=path)

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != _REQUEST_ID_HEADER
                ]
                headers.append((_REQUEST_ID_HEADER, request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            logger.error(
                "http_request_failed",
                method=method,
                path=path,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise
        else:
            logger.info(
                "http_request_completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=elapsed_ms(started_at),
            )
        finally:
            structlog.contextvars.clear_contextvars()
