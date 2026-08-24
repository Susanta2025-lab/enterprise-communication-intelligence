"""Provider-neutral factory that configures a read connector from an owned account.

The factory does not load accounts, check ownership, retrieve tokens, or call
provider HTTP. The application supplies an already-owned ConnectorAccountRecord.
Unroutable providers and missing locators fail through a typed provider-neutral
error. The returned connector remains read-only.
"""

from abc import ABC, abstractmethod

from app.domain.interfaces.communication_connector import CommunicationConnector
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord


class CommunicationConnectorFactory(ABC):
    """Create a provider-specific read connector from an owned connector account.

    Implementations must not invoke the returned access-token callable or call
    mailbox HTTP. Ownership, ACTIVE status, and ``mail.read`` stay in the
    application layer.
    """

    @abstractmethod
    def create_for_account(
        self,
        account: ConnectorAccountRecord,
    ) -> CommunicationConnector:
        """Return a configured read connector for a technically routable account."""
