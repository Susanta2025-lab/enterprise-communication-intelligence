"""Shared pytest fixtures for ECI Platform tests."""

from collections.abc import Iterator
from typing import Any

import pytest
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Ensure each test observes a fresh settings cache."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def log_events(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    """Capture structured log event dictionaries, including bound contextvars."""
    events: list[dict[str, Any]] = []

    def capture(
        _logger: object,
        _method_name: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        events.append(dict(event_dict))
        return event_dict

    def configure_with_capture(log_level: str, environment: str) -> None:
        configure_logging(log_level, environment)
        config = structlog.get_config()
        processors = list(config["processors"])
        if capture not in processors:
            insert_at = max(len(processors) - 1, 0)
            processors.insert(insert_at, capture)
        structlog.configure(
            processors=processors,
            wrapper_class=config["wrapper_class"],
            logger_factory=config["logger_factory"],
            cache_logger_on_first_use=False,
        )

    monkeypatch.setattr("app.main.configure_logging", configure_with_capture)
    configure_with_capture("INFO", "production")
    yield events
