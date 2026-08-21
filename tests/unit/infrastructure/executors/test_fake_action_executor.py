"""Unit tests for FakeCommunicationActionExecutor."""

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import CommunicationActionExecutionError
from app.domain.enums import WorkflowActionType
from app.domain.interfaces import CommunicationActionExecution, CommunicationActionExecutor
from app.infrastructure.executors.fake import FakeCommunicationActionExecutor

_FAKE_ROOT = Path(__file__).resolve().parents[4] / "app" / "infrastructure" / "executors"
_REPLY = "Thanks, I will review the report and respond by Friday."
_IO_MARKERS = (
    "httpx",
    "requests",
    "urllib",
    "socket",
    "time.sleep",
    "gmail",
    "graph.microsoft.com",
    "AIProvider",
    "PersistenceUnitOfWork",
    "sqlalchemy",
)


def _command(**overrides: object) -> CommunicationActionExecution:
    payload: dict[str, object] = {
        "action_id": uuid4(),
        "action_type": WorkflowActionType.REPLY,
        "approved_reply_body": _REPLY,
    }
    payload.update(overrides)
    return CommunicationActionExecution.model_validate(payload)


def test_fake_executor_implements_write_port() -> None:
    """The fake is a CommunicationActionExecutor, not a connector."""
    executor = FakeCommunicationActionExecutor()

    assert isinstance(executor, CommunicationActionExecutor)
    assert not hasattr(executor, "list_messages")
    assert not hasattr(executor, "fetch_message")


def test_default_fail_false_succeeds_and_records_command() -> None:
    """Default configuration returns None and captures the exact command."""
    command = _command()
    executor = FakeCommunicationActionExecutor()

    result = executor.execute(command)

    assert result is None
    assert executor.calls == [command]
    assert executor.calls[0].approved_reply_body == _REPLY


def test_fail_true_records_command_then_raises_generic_error() -> None:
    """Configured failure still captures the command before raising."""
    command = _command()
    executor = FakeCommunicationActionExecutor(fail=True)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    assert executor.calls == [command]
    assert exc_info.value.message == "Communication action execution failed."
    assert "gmail" not in exc_info.value.message.lower()
    assert "graph" not in exc_info.value.message.lower()


def test_instances_do_not_share_calls() -> None:
    """Call capture is instance-local; there is no global call list."""
    command = _command()
    first = FakeCommunicationActionExecutor()
    second = FakeCommunicationActionExecutor()

    first.execute(command)

    assert first.calls == [command]
    assert second.calls == []


def test_multiple_calls_preserve_order() -> None:
    """Repeated execute calls append commands in invocation order."""
    first = _command()
    second = _command()
    executor = FakeCommunicationActionExecutor()

    executor.execute(first)
    executor.execute(second)

    assert executor.calls == [first, second]


def test_execute_does_not_mutate_command() -> None:
    """The recorded command remains the original frozen snapshot."""
    command = _command()
    snapshot = command.model_dump()
    executor = FakeCommunicationActionExecutor()

    executor.execute(command)

    assert command.model_dump() == snapshot
    assert executor.calls[0].model_dump() == snapshot
    with pytest.raises(ValidationError):
        command.approved_reply_body = "mutated"  # type: ignore[misc]


def test_reply_body_does_not_control_failure() -> None:
    """Magic reply strings must not trigger failure; only fail=True does."""
    command = _command(approved_reply_body="FAIL")
    executor = FakeCommunicationActionExecutor()

    assert executor.execute(command) is None
    assert executor.calls[0].approved_reply_body == "FAIL"


def test_fake_executor_source_has_no_external_io() -> None:
    """The fake must not network, sleep, touch persistence, or call providers."""
    source = (_FAKE_ROOT / "fake.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for marker in _IO_MARKERS:
        assert marker.lower() not in lowered, f"fake executor must not use {marker}"
    assert "open(" not in source
    assert "Path(" not in source
    assert "message_id" not in source
    assert "thread_id" not in source
    assert "provider_response_id" not in source
