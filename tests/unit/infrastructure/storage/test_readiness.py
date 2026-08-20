"""Unit tests for the persistence readiness probe. No PostgreSQL required."""

from collections.abc import Iterator

import pytest
from sqlalchemy.exc import OperationalError

from app.infrastructure.storage.runtime import (
    dispose_persistence_runtime,
    probe_database_readiness,
)


@pytest.fixture(autouse=True)
def _reset_runtime() -> Iterator[None]:
    dispose_persistence_runtime()
    yield
    dispose_persistence_runtime()


class _FailingEngine:
    def connect(self) -> object:
        raise OperationalError(
            "SELECT 1",
            {},
            Exception("password=supersecret host=db.internal.sqlalchemy-test"),
        )

    def dispose(self) -> None:
        return None


class _SuccessfulConnection:
    def __enter__(self) -> "_SuccessfulConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _statement: object) -> None:
        return None


class _SuccessfulEngine:
    def connect(self) -> _SuccessfulConnection:
        return _SuccessfulConnection()

    def dispose(self) -> None:
        return None


def test_probe_returns_true_when_select_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful SELECT 1 probe reports ready."""
    monkeypatch.setattr(
        "app.infrastructure.storage.runtime.create_database_engine",
        lambda _url: _SuccessfulEngine(),
    )
    assert probe_database_readiness("postgresql+psycopg://eci_test:eci_test@localhost:5432/eci_test")


def test_probe_returns_false_on_driver_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Driver failures become not-ready without leaking connection details."""
    events: list[tuple[str, dict[str, object]]] = []

    def _warning(event: str, **kwargs: object) -> None:
        events.append((event, kwargs))

    monkeypatch.setattr(
        "app.infrastructure.storage.runtime.create_database_engine",
        lambda _url: _FailingEngine(),
    )
    monkeypatch.setattr("app.infrastructure.storage.runtime.logger.warning", _warning)

    url = "postgresql+psycopg://eci_test:supersecret@db.internal:5432/eci_test"
    assert probe_database_readiness(url) is False
    assert events
    event, payload = events[0]
    assert event == "database_readiness_failed"
    assert payload["component"] == "database"
    assert payload["error_class"] == "OperationalError"
    serialized = repr(events)
    assert "supersecret" not in serialized
    assert "db.internal" not in serialized
    assert url not in serialized
    assert "exc_info" not in payload
    assert "password" not in serialized
