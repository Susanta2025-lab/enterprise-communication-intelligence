"""Shared pytest fixtures for ContextMesh tests."""

from collections.abc import Iterator

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Ensure each test observes a fresh settings cache."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
