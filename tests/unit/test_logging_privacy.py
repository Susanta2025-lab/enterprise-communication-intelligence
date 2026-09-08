"""Privacy-safe logging configuration for attachment/AI paths."""

from __future__ import annotations

import logging

from app.core.logging import configure_logging


def test_configure_logging_mutes_http_clients_that_may_emit_provider_urls() -> None:
    """httpx/Azure HTTP loggers must not dump Graph attachment URLs at INFO."""
    configure_logging("INFO", "production")
    for name in (
        "httpx",
        "httpcore",
        "urllib3",
        "azure",
        "azure.core.pipeline.policies.http_logging_policy",
    ):
        assert logging.getLogger(name).level == logging.WARNING
