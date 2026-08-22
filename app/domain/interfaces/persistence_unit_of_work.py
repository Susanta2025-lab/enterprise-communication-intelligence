"""SQLAlchemy-free persistence unit of work contract."""

from abc import ABC, abstractmethod
from types import TracebackType

from app.domain.interfaces.analysis_repository import AnalysisRepository
from app.domain.interfaces.connector_account_repository import ConnectorAccountRepository
from app.domain.interfaces.identity_repository import IdentityRepository
from app.domain.interfaces.mailbox_authorization_session_repository import (
    MailboxAuthorizationSessionRepository,
)
from app.domain.interfaces.workflow_action_repository import WorkflowActionRepository


class PersistenceUnitOfWork(ABC):
    """Caller-owned transaction boundary around persistence repositories.

    Implementations create one session per unit of work. Repositories do not commit.
    """

    @property
    @abstractmethod
    def identity_repository(self) -> IdentityRepository:
        """Identity mapping repository bound to this unit of work."""

    @property
    @abstractmethod
    def analysis_repository(self) -> AnalysisRepository:
        """Analysis history repository bound to this unit of work."""

    @property
    @abstractmethod
    def connector_accounts(self) -> ConnectorAccountRepository:
        """Connector account repository bound to this unit of work."""

    @property
    @abstractmethod
    def workflow_actions(self) -> WorkflowActionRepository:
        """Workflow action repository bound to this unit of work."""

    @property
    @abstractmethod
    def mailbox_authorization_sessions(self) -> MailboxAuthorizationSessionRepository:
        """Mailbox authorization session repository bound to this unit of work."""

    @abstractmethod
    def commit(self) -> None:
        """Commit the current unit of work."""

    @abstractmethod
    def rollback(self) -> None:
        """Roll back uncommitted work."""

    @abstractmethod
    def __enter__(self) -> "PersistenceUnitOfWork":
        """Open the unit of work and bind repositories."""

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Roll back on failure and always close the underlying session."""
