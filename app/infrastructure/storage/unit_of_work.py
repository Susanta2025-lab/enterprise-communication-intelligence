"""SQLAlchemy persistence unit of work.

One Session is created per unit of work. Repositories never commit. SQLAlchemy
exceptions are translated to PersistenceError without exposing driver details.
"""

from types import TracebackType

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import PersistenceError
from app.domain.interfaces.analysis_repository import AnalysisRepository
from app.domain.interfaces.connector_account_repository import ConnectorAccountRepository
from app.domain.interfaces.identity_repository import IdentityRepository
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.interfaces.workflow_action_repository import WorkflowActionRepository
from app.infrastructure.storage.repositories.analysis import SqlAlchemyAnalysisRepository
from app.infrastructure.storage.repositories.connector_account import (
    SqlAlchemyConnectorAccountRepository,
)
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository
from app.infrastructure.storage.repositories.workflow_action import (
    SqlAlchemyWorkflowActionRepository,
)

_GENERIC_COMMIT_FAILURE = "Could not commit persistence changes."
_GENERIC_OPERATION_FAILURE = "Could not complete persistence operation."
_INACTIVE = "Persistence unit of work is not active."


class SqlAlchemyPersistenceUnitOfWork(PersistenceUnitOfWork):
    """Bind persistence repositories to a single SQLAlchemy Session."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._identity_repository: IdentityRepository | None = None
        self._analysis_repository: AnalysisRepository | None = None
        self._connector_accounts: ConnectorAccountRepository | None = None
        self._workflow_actions: WorkflowActionRepository | None = None

    @property
    def identity_repository(self) -> IdentityRepository:
        """Identity mapping repository bound to this unit of work."""
        if self._identity_repository is None:
            raise PersistenceError(_INACTIVE)
        return self._identity_repository

    @property
    def analysis_repository(self) -> AnalysisRepository:
        """Analysis history repository bound to this unit of work."""
        if self._analysis_repository is None:
            raise PersistenceError(_INACTIVE)
        return self._analysis_repository

    @property
    def connector_accounts(self) -> ConnectorAccountRepository:
        """Connector account repository bound to this unit of work."""
        if self._connector_accounts is None:
            raise PersistenceError(_INACTIVE)
        return self._connector_accounts

    @property
    def workflow_actions(self) -> WorkflowActionRepository:
        """Workflow action repository bound to this unit of work."""
        if self._workflow_actions is None:
            raise PersistenceError(_INACTIVE)
        return self._workflow_actions

    def commit(self) -> None:
        """Commit the current unit of work."""
        session = self._require_session()
        try:
            session.commit()
        except SQLAlchemyError:
            self.rollback()
            raise PersistenceError(_GENERIC_COMMIT_FAILURE) from None

    def rollback(self) -> None:
        """Roll back uncommitted work."""
        session = self._session
        if session is None:
            return
        try:
            session.rollback()
        except SQLAlchemyError:
            return

    def __enter__(self) -> PersistenceUnitOfWork:
        """Open a Session, start the outer transaction, and construct repositories."""
        session: Session | None = None
        try:
            session = self._session_factory()
            if not session.in_transaction():
                session.begin()
            self._session = session
            self._identity_repository = SqlAlchemyIdentityRepository(session)
            self._analysis_repository = SqlAlchemyAnalysisRepository(session)
            self._connector_accounts = SqlAlchemyConnectorAccountRepository(session)
            self._workflow_actions = SqlAlchemyWorkflowActionRepository(session)
            return self
        except SQLAlchemyError:
            if session is not None:
                try:
                    session.close()
                except SQLAlchemyError:
                    pass
            self._session = None
            self._identity_repository = None
            self._analysis_repository = None
            self._connector_accounts = None
            self._workflow_actions = None
            raise PersistenceError(_GENERIC_OPERATION_FAILURE) from None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Roll back uncommitted work, always close the Session, and hide driver errors."""
        try:
            if exc_type is not None:
                self.rollback()
            elif self._session is not None and self._session.in_transaction():
                self.rollback()
        finally:
            self.close()

        if isinstance(exc, SQLAlchemyError):
            raise PersistenceError(_GENERIC_OPERATION_FAILURE) from None

    def close(self) -> None:
        """Close the Session if one is open."""
        session = self._session
        self._session = None
        self._identity_repository = None
        self._analysis_repository = None
        self._connector_accounts = None
        self._workflow_actions = None
        if session is None:
            return
        session.close()

    def _require_session(self) -> Session:
        session = self._session
        if session is None:
            raise PersistenceError(_INACTIVE)
        return session
