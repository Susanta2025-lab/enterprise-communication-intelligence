"""Unit tests for shared telemetry helpers."""

import pytest

from app.core.telemetry import elapsed_ms, error_class, resolve_provider_name
from app.providers.mock.provider import MockAIProvider


class _AnonymousProvider:
    """Test double without PROVIDER_NAME."""


def test_elapsed_ms_is_non_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    """elapsed_ms should return milliseconds from a perf_counter start mark."""
    monkeypatch.setattr("app.core.telemetry.time.perf_counter", lambda: 12.5)

    value = elapsed_ms(12.25)

    assert isinstance(value, float)
    assert value == 250.0


def test_elapsed_ms_never_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clock skew must not produce a negative duration."""
    monkeypatch.setattr("app.core.telemetry.time.perf_counter", lambda: 1.0)

    assert elapsed_ms(2.0) == 0.0


def test_error_class_uses_exception_type_name() -> None:
    """error_class must be the exception class name, not the message."""
    assert error_class(RuntimeError("ECI_PRIVATE_ERROR_SENTINEL")) == "RuntimeError"


def test_resolve_provider_name_prefers_stable_constant() -> None:
    """Known providers should log PROVIDER_NAME rather than the class name."""
    assert resolve_provider_name(MockAIProvider()) == "mock"


def test_resolve_provider_name_falls_back_to_class_name() -> None:
    """Providers without PROVIDER_NAME still have a bounded identifier."""
    assert resolve_provider_name(_AnonymousProvider()) == "_AnonymousProvider"
