"""Shared pytest fixtures for ECI Platform tests."""

from collections.abc import Iterator
from typing import Any

import pytest
import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging


@pytest.fixture(autouse=True)
def ignore_developer_dotenv(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep offline tests deterministic when a live developer ``.env`` exists.

    Phase 13 mailbox OAuth and OIDC live validation populate ``.env``. Tests that
    clear process environment variables would otherwise still inherit those
    values through pydantic-settings ``env_file=".env"``. Explicit
    ``monkeypatch.setenv`` values continue to apply.
    """
    original_init = Settings.__init__

    def init_without_dotenv(self: Settings, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("_env_file", None)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(Settings, "__init__", init_without_dotenv)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
