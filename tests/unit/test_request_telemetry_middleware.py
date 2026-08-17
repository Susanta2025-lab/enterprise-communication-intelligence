"""Unit tests for HTTP request telemetry middleware."""

import asyncio

import pytest

from app.api.middleware import RequestTelemetryMiddleware


def _http_scope(path: str = "/boom") -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"secret=1",
        "headers": [],
        "client": None,
        "server": None,
        "scheme": "http",
    }


def test_http_request_failed_logs_error_class_not_message(
    log_events: list[dict],
) -> None:
    """Unhandled ASGI exceptions emit http_request_failed without exception text."""

    async def boom(_scope: object, _receive: object, _send: object) -> None:
        raise RuntimeError("ECI_PRIVATE_ERROR_SENTINEL")

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: dict) -> None:
        return None

    middleware = RequestTelemetryMiddleware(boom)

    with pytest.raises(RuntimeError, match="ECI_PRIVATE_ERROR_SENTINEL"):
        asyncio.run(middleware(_http_scope(), receive, send))

    failed = [event for event in log_events if event.get("event") == "http_request_failed"]
    assert len(failed) == 1
    assert failed[0]["error_class"] == "RuntimeError"
    assert failed[0]["method"] == "GET"
    assert failed[0]["path"] == "/boom"
    assert isinstance(failed[0]["duration_ms"], float)
    assert failed[0]["duration_ms"] >= 0
    assert "secret=1" not in str(failed[0])
    assert "ECI_PRIVATE_ERROR_SENTINEL" not in str(failed[0])
