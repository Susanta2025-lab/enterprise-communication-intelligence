"""Test double that always returns a preconfigured read connector."""

from __future__ import annotations

from app.domain.interfaces.communication_connector import CommunicationConnector
from app.domain.interfaces.communication_connector_factory import (
    CommunicationConnectorFactory,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord


class StaticCommunicationConnectorFactory(CommunicationConnectorFactory):
    """Return one injected connector for application tests.

    Production routing is not performed.
    """

    def __init__(self, connector: CommunicationConnector) -> None:
        self._connector = connector
        self.calls = 0
        self.accounts: list[ConnectorAccountRecord] = []

    def create_for_account(
        self,
        account: ConnectorAccountRecord,
    ) -> CommunicationConnector:
        self.calls += 1
        self.accounts.append(account)
        return self._connector
