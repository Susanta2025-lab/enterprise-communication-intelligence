"""Deterministic offline CommunicationActionExecutor for architecture and tests."""

from app.core.exceptions import CommunicationActionExecutionError
from app.domain.interfaces import CommunicationActionExecution, CommunicationActionExecutor


class FakeCommunicationActionExecutor(CommunicationActionExecutor):
    """In-memory executor that records commands and never performs I/O.

    Failure is controlled only by constructor configuration. Reply-body content
    never triggers failure.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.calls: list[CommunicationActionExecution] = []

    def execute(self, command: CommunicationActionExecution) -> None:
        """Record ``command`` and optionally raise a generic execution error."""
        self.calls.append(command)
        if self._fail:
            raise CommunicationActionExecutionError()
