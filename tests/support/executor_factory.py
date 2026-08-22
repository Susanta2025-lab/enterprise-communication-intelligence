"""Test double that always returns a preconfigured write executor."""

from __future__ import annotations

from app.domain.interfaces.communication_action_executor import CommunicationActionExecutor
from app.domain.interfaces.communication_action_executor_factory import (
    CommunicationActionExecutorFactory,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord


class StaticCommunicationActionExecutorFactory(CommunicationActionExecutorFactory):
    """Return one injected executor for workflow unit tests.

    Production routing is not performed. ``None`` can be supplied to prove the
    not-executable path before ``APPROVED`` → ``EXECUTING``.
    """

    def __init__(self, executor: CommunicationActionExecutor | None) -> None:
        self._executor = executor
        self.calls = 0
        self.accounts: list[ConnectorAccountRecord] = []

    def create_for_account(
        self,
        account: ConnectorAccountRecord,
    ) -> CommunicationActionExecutor | None:
        self.calls += 1
        self.accounts.append(account)
        return self._executor
