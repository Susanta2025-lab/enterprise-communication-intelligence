"""Provider-neutral factory that configures a write executor from an owned account.

The factory does not load accounts, check ownership, retrieve tokens, or call
provider HTTP. The application supplies an already-owned ConnectorAccountRecord.
"""

from abc import ABC, abstractmethod

from app.domain.interfaces.communication_action_executor import CommunicationActionExecutor
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord


class CommunicationActionExecutorFactory(ABC):
    """Create a provider-specific executor from an owned connector account.

    ``None`` means the account cannot be executed through a production writer.
    The application maps that to a generic not-executable outcome.
    """

    @abstractmethod
    def create_for_account(
        self,
        account: ConnectorAccountRecord,
    ) -> CommunicationActionExecutor | None:
        """Return a configured executor, or ``None`` when routing is not possible."""
