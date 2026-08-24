"""Provider-independent domain interfaces."""

from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.analysis_repository import (
    AnalysisRecord,
    AnalysisRepository,
    NewAnalysis,
)
from app.domain.interfaces.communication_action_executor import (
    CommunicationActionExecution,
    CommunicationActionExecutor,
)
from app.domain.interfaces.communication_action_executor_factory import (
    CommunicationActionExecutorFactory,
)
from app.domain.interfaces.communication_connector import (
    CommunicationConnector,
    ConnectorMessageQuery,
    MessagePage,
)
from app.domain.interfaces.communication_credential_resolver import (
    AccessTokenProvider,
    CommunicationCredentialResolver,
)
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    CommunicationCredentialStore,
    NewCommunicationCredential,
)
from app.domain.interfaces.connector_account_repository import (
    ConnectorAccountRecord,
    ConnectorAccountRepository,
    NewConnectorAccount,
)
from app.domain.interfaces.identity_repository import IdentityRepository
from app.domain.interfaces.mailbox_authorization_session_repository import (
    ConsumedMailboxAuthorizationSession,
    MailboxAuthorizationSessionRecord,
    MailboxAuthorizationSessionRepository,
    NewMailboxAuthorizationSession,
)
from app.domain.interfaces.mailbox_oauth_client import (
    MailboxOAuthAuthorizationResult,
    MailboxOAuthClient,
)
from app.domain.interfaces.mailbox_token_revoker import MailboxTokenRevoker
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.interfaces.workflow_action_repository import (
    WorkflowActionRepository,
    WorkflowActionSaveOutcome,
    WorkflowActionSaveResult,
)

__all__ = [
    "AIProvider",
    "AccessTokenProvider",
    "AnalysisRecord",
    "AnalysisRepository",
    "CommunicationActionExecution",
    "CommunicationActionExecutor",
    "CommunicationActionExecutorFactory",
    "CommunicationConnector",
    "CommunicationCredentialRecord",
    "CommunicationCredentialResolver",
    "CommunicationCredentialStore",
    "ConnectorAccountRecord",
    "ConnectorAccountRepository",
    "ConnectorMessageQuery",
    "ConsumedMailboxAuthorizationSession",
    "IdentityRepository",
    "MailboxAuthorizationSessionRecord",
    "MailboxAuthorizationSessionRepository",
    "MailboxOAuthAuthorizationResult",
    "MailboxOAuthClient",
    "MailboxTokenRevoker",
    "NewMailboxAuthorizationSession",
    "MessagePage",
    "NewAnalysis",
    "NewCommunicationCredential",
    "NewConnectorAccount",
    "PersistenceUnitOfWork",
    "WorkflowActionRepository",
    "WorkflowActionSaveOutcome",
    "WorkflowActionSaveResult",
]
