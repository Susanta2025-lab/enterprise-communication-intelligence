"""Unit tests for structured logging configuration."""

import logging

from app.core.logging import configure_logging, get_logger


def test_configure_logging_sets_level_and_avoids_duplicate_handlers() -> None:
    """configure_logging should set the root level and replace handlers."""
    configure_logging("WARNING", "development")
    root_logger = logging.getLogger()
    assert root_logger.level == logging.WARNING
    handler_count = len(root_logger.handlers)

    configure_logging("INFO", "development")
    assert logging.getLogger().level == logging.INFO
    assert len(logging.getLogger().handlers) == handler_count


def test_get_logger_returns_bound_logger() -> None:
    """get_logger should return a usable structlog bound logger."""
    configure_logging("INFO", "development")
    logger = get_logger("tests.logging")
    assert logger is not None
    logger.info("logging_smoke_test")
