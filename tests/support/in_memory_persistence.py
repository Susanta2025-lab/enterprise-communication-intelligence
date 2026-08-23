"""In-memory persistence doubles for Phase 9B application tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

from app.core.exceptions import PersistenceError
from app.domain.enums import (
    ConnectorAccountStatus,
    MailboxAuthorizationProvider,
    WorkflowActionStatus,
)
from app.domain.interfaces.analysis_repository import AnalysisRecord, NewAnalysis
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
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.interfaces.workflow_action_repository import (
    WorkflowActionRepository,
    WorkflowActionSaveOutcome,
    WorkflowActionSaveResult,
)
from app.domain.models.workflow import WorkflowAction

_DUPLICATE_IDENTITY = "External identity is already registered."
_DUPLICATE_CONNECTOR_ACCOUNT = "Connector account is already registered."


class InMemoryIdentityRepository(IdentityRepository):
    """Dict-backed identity mapping used by unit tests."""

    def __init__(self, identities: dict[tuple[str, str], UUID]) -> None:
        self._identities = identities
        self.create_calls = 0

    def get_user_id_by_external_identity(self, issuer: str, subject: str) -> UUID | None:
        return self._identities.get((issuer, subject))

    def create_user_with_external_identity(self, issuer: str, subject: str) -> UUID:
        self.create_calls += 1
        key = (issuer, subject)
        if key in self._identities:
            raise PersistenceError(_DUPLICATE_IDENTITY)
        user_id = uuid4()
        self._identities[key] = user_id
        return user_id


class InMemoryAnalysisRepository:
    """Dict-backed analysis store used by unit tests."""

    def __init__(self, analyses: dict[UUID, AnalysisRecord]) -> None:
        self._analyses = analyses
        self.save_calls = 0
        self.get_calls = 0

    def save(self, analysis: NewAnalysis) -> AnalysisRecord:
        self.save_calls += 1
        now = datetime.now(UTC)
        record = AnalysisRecord(
            id=analysis.analysis_id or uuid4(),
            user_id=analysis.user_id,
            created_at=now,
            updated_at=now,
            request_id=analysis.request_id,
            provider=analysis.provider,
            priority=analysis.priority,
            category=analysis.category,
            source_type=analysis.source_type,
            message_id=analysis.message_id,
            summary_text=analysis.summary_text,
            summary_confidence=analysis.summary_confidence,
            action_items=list(analysis.action_items),
            draft_reply=None if analysis.draft_reply is None else dict(analysis.draft_reply),
            connector_account_id=analysis.connector_account_id,
        )
        self._analyses[record.id] = record
        return record

    def get_by_id_for_user(self, analysis_id: UUID, user_id: UUID) -> AnalysisRecord | None:
        self.get_calls += 1
        record = self._analyses.get(analysis_id)
        if record is None or record.user_id != user_id:
            return None
        return record

    def list_for_user(self, user_id: UUID, limit: int, offset: int) -> list[AnalysisRecord]:
        owned = [item for item in self._analyses.values() if item.user_id == user_id]
        owned.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        if limit < 1 or offset < 0:
            return []
        return owned[offset : offset + min(limit, 100)]

    def delete_for_user(self, analysis_id: UUID, user_id: UUID) -> bool:
        record = self._analyses.get(analysis_id)
        if record is None or record.user_id != user_id:
            return False
        del self._analyses[analysis_id]
        return True


class InMemoryConnectorAccountRepository(ConnectorAccountRepository):
    """Dict-backed connector account store used by unit tests."""

    def __init__(self, accounts: dict[UUID, ConnectorAccountRecord]) -> None:
        self._accounts = accounts
        self.create_calls = 0

    def create(self, account: NewConnectorAccount) -> ConnectorAccountRecord:
        self.create_calls += 1
        if self._find_key(account.user_id, account.provider, account.external_account_id):
            raise PersistenceError(_DUPLICATE_CONNECTOR_ACCOUNT)
        now = datetime.now(UTC)
        record = ConnectorAccountRecord(
            id=uuid4(),
            user_id=account.user_id,
            provider=account.provider,
            external_account_id=account.external_account_id,
            credential_ref=account.credential_ref,
            status=ConnectorAccountStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            granted_capabilities=account.granted_capabilities,
        )
        self._accounts[record.id] = record
        return record

    def find_by_owner_provider_external_account(
        self,
        user_id: UUID,
        provider: str,
        external_account_id: str,
    ) -> ConnectorAccountRecord | None:
        return self._find_key(user_id, provider, external_account_id)

    def get_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
    ) -> ConnectorAccountRecord | None:
        record = self._accounts.get(connector_account_id)
        if record is None or record.user_id != user_id:
            return None
        return record

    def list_owned(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ConnectorAccountRecord]:
        owned = [item for item in self._accounts.values() if item.user_id == user_id]
        owned.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        if limit < 1 or offset < 0:
            return []
        return owned[offset : offset + min(limit, 100)]

    def disconnect_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
    ) -> ConnectorAccountRecord | None:
        record = self.get_owned(connector_account_id, user_id)
        if record is None:
            return None
        updated = ConnectorAccountRecord(
            id=record.id,
            user_id=record.user_id,
            provider=record.provider,
            external_account_id=record.external_account_id,
            credential_ref=None,
            status=ConnectorAccountStatus.DISCONNECTED,
            created_at=record.created_at,
            updated_at=datetime.now(UTC),
            granted_capabilities=None,
        )
        self._accounts[record.id] = updated
        return updated

    def reactivate_owned(
        self,
        connector_account_id: UUID,
        user_id: UUID,
        credential_ref: str | None,
        *,
        granted_capabilities: tuple | None = None,
        replace_granted_capabilities: bool = False,
    ) -> ConnectorAccountRecord | None:
        record = self.get_owned(connector_account_id, user_id)
        if record is None:
            return None
        if record.status not in {
            ConnectorAccountStatus.DISCONNECTED,
            ConnectorAccountStatus.REAUTH_REQUIRED,
        }:
            return None
        capabilities = (
            granted_capabilities
            if replace_granted_capabilities
            else record.granted_capabilities
        )
        updated = ConnectorAccountRecord(
            id=record.id,
            user_id=record.user_id,
            provider=record.provider,
            external_account_id=record.external_account_id,
            credential_ref=credential_ref,
            status=ConnectorAccountStatus.ACTIVE,
            created_at=record.created_at,
            updated_at=datetime.now(UTC),
            granted_capabilities=capabilities,
        )
        self._accounts[record.id] = updated
        return updated

    def _find_key(
        self,
        user_id: UUID,
        provider: str,
        external_account_id: str,
    ) -> ConnectorAccountRecord | None:
        for record in self._accounts.values():
            if (
                record.user_id == user_id
                and record.provider == provider
                and record.external_account_id == external_account_id
            ):
                return record
        return None


class InMemoryMailboxAuthorizationSessionRepository(MailboxAuthorizationSessionRepository):
    """Dict-backed mailbox authorization session store used by unit tests."""

    def __init__(
        self,
        sessions: dict[UUID, MailboxAuthorizationSessionRecord],
    ) -> None:
        self._sessions = sessions
        self.create_calls = 0

    def create(
        self,
        session: NewMailboxAuthorizationSession,
    ) -> MailboxAuthorizationSessionRecord:
        self.create_calls += 1
        for existing in self._sessions.values():
            if existing.state_hash == session.state_hash:
                raise PersistenceError("Could not persist mailbox authorization session.")
        record = MailboxAuthorizationSessionRecord(
            id=uuid4(),
            user_id=session.user_id,
            provider=session.provider,
            purpose=session.purpose,
            connector_account_id=session.connector_account_id,
            state_hash=session.state_hash,
            pkce_verifier=session.pkce_verifier,
            requested_capabilities=session.requested_capabilities,
            created_at=session.created_at,
            expires_at=session.expires_at,
            consumed_at=None,
        )
        self._sessions[record.id] = record
        return record

    def consume_valid(
        self,
        state_hash: str,
        provider: MailboxAuthorizationProvider,
        now: datetime,
    ) -> ConsumedMailboxAuthorizationSession | None:
        matching: MailboxAuthorizationSessionRecord | None = None
        for record in self._sessions.values():
            if (
                record.state_hash == state_hash
                and record.provider == provider
                and record.consumed_at is None
                and record.expires_at > now
                and record.pkce_verifier
            ):
                matching = record
                break
        if matching is None or matching.pkce_verifier is None:
            return None
        consumed = MailboxAuthorizationSessionRecord(
            id=matching.id,
            user_id=matching.user_id,
            provider=matching.provider,
            purpose=matching.purpose,
            connector_account_id=matching.connector_account_id,
            state_hash=matching.state_hash,
            pkce_verifier=None,
            requested_capabilities=matching.requested_capabilities,
            created_at=matching.created_at,
            expires_at=matching.expires_at,
            consumed_at=now,
        )
        self._sessions[matching.id] = consumed
        return ConsumedMailboxAuthorizationSession(
            authorization_session_id=matching.id,
            user_id=matching.user_id,
            provider=matching.provider,
            purpose=matching.purpose,
            connector_account_id=matching.connector_account_id,
            pkce_verifier=matching.pkce_verifier,
            requested_capabilities=matching.requested_capabilities,
        )

    def delete_expired(self, before: datetime) -> int:
        expired = [
            session_id
            for session_id, record in self._sessions.items()
            if record.expires_at <= before
        ]
        for session_id in expired:
            del self._sessions[session_id]
        return len(expired)


class InMemoryWorkflowActionRepository(WorkflowActionRepository):
    """Dict-backed workflow action store used by unit tests."""

    def __init__(self, actions: dict[UUID, WorkflowAction]) -> None:
        self._actions = actions
        self.add_calls = 0
        self.get_calls = 0
        self.save_calls = 0

    def add(self, action: WorkflowAction) -> WorkflowAction:
        self.add_calls += 1
        stored = _copy_workflow_action(action)
        self._actions[stored.id] = stored
        return _copy_workflow_action(stored)

    def get_owned(self, action_id: UUID, user_id: UUID) -> WorkflowAction | None:
        self.get_calls += 1
        stored = self._actions.get(action_id)
        if stored is None or stored.owner_user_id != user_id:
            return None
        return _copy_workflow_action(stored)

    def list_owned(self, user_id: UUID, limit: int, offset: int) -> list[WorkflowAction]:
        owned = [
            _copy_workflow_action(item)
            for item in self._actions.values()
            if item.owner_user_id == user_id
        ]
        owned.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        if limit < 1 or offset < 0:
            return []
        return owned[offset : offset + min(limit, 100)]

    def save_owned(
        self,
        action: WorkflowAction,
        expected_status: WorkflowActionStatus,
    ) -> WorkflowActionSaveResult:
        self.save_calls += 1
        stored = self._actions.get(action.id)
        if stored is None or stored.owner_user_id != action.owner_user_id:
            return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.NOT_FOUND)
        if stored.status is not expected_status:
            return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.CONFLICT)
        saved = _copy_workflow_action(action)
        # Match SQL save_owned: lifecycle fields update, execution target does not.
        saved.connector_account_id = stored.connector_account_id
        saved.provider_message_id = stored.provider_message_id
        self._actions[action.id] = saved
        return WorkflowActionSaveResult(
            outcome=WorkflowActionSaveOutcome.SUCCESS,
            action=_copy_workflow_action(saved),
        )


def _copy_workflow_action(action: WorkflowAction) -> WorkflowAction:
    return WorkflowAction.rehydrate(
        id=action.id,
        action_type=action.action_type,
        analysis_id=action.analysis_id,
        owner_user_id=action.owner_user_id,
        proposed_reply_body=action.proposed_reply_body,
        status=action.status,
        created_at=action.created_at,
        approved_at=action.approved_at,
        rejected_at=action.rejected_at,
        executed_at=action.executed_at,
        failed_at=action.failed_at,
        approved_reply_body=action.approved_reply_body,
        connector_account_id=action.connector_account_id,
        provider_message_id=action.provider_message_id,
    )


class InMemoryUnitOfWork(PersistenceUnitOfWork):
    """Minimal unit of work that records commit/rollback/close."""

    def __init__(
        self,
        *,
        identities: dict[tuple[str, str], UUID] | None = None,
        analyses: dict[UUID, AnalysisRecord] | None = None,
        connector_accounts: dict[UUID, ConnectorAccountRecord] | None = None,
        mailbox_authorization_sessions: (
            dict[UUID, MailboxAuthorizationSessionRecord] | None
        ) = None,
        workflow_actions: dict[UUID, WorkflowAction] | None = None,
        fail_commit: bool = False,
        fail_on_enter: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.identities = identities if identities is not None else {}
        self.analyses = analyses if analyses is not None else {}
        self.connector_account_store = (
            connector_accounts if connector_accounts is not None else {}
        )
        self.mailbox_authorization_session_store = (
            mailbox_authorization_sessions
            if mailbox_authorization_sessions is not None
            else {}
        )
        self.workflow_action_store = (
            workflow_actions if workflow_actions is not None else {}
        )
        self._identity_repository = InMemoryIdentityRepository(self.identities)
        self._analysis_repository = InMemoryAnalysisRepository(self.analyses)
        self._connector_accounts = InMemoryConnectorAccountRepository(
            self.connector_account_store
        )
        self._mailbox_authorization_sessions = (
            InMemoryMailboxAuthorizationSessionRepository(
                self.mailbox_authorization_session_store
            )
        )
        self._workflow_actions = InMemoryWorkflowActionRepository(
            self.workflow_action_store
        )
        self.fail_commit = fail_commit
        self.fail_on_enter = fail_on_enter
        self.commit_error = commit_error
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False
        self.entered = False

    @property
    def identity_repository(self) -> InMemoryIdentityRepository:
        return self._identity_repository

    @property
    def analysis_repository(self) -> InMemoryAnalysisRepository:
        return self._analysis_repository

    @property
    def connector_accounts(self) -> InMemoryConnectorAccountRepository:
        return self._connector_accounts

    @property
    def mailbox_authorization_sessions(
        self,
    ) -> InMemoryMailboxAuthorizationSessionRepository:
        return self._mailbox_authorization_sessions

    @property
    def workflow_actions(self) -> InMemoryWorkflowActionRepository:
        return self._workflow_actions

    def commit(self) -> None:
        self.commit_calls += 1
        if self.fail_commit:
            raise PersistenceError("Could not commit persistence changes.")
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.rollback_calls += 1

    def __enter__(self) -> InMemoryUnitOfWork:
        if self.fail_on_enter is not None:
            raise self.fail_on_enter
        self.entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        self.closed = True

    def close(self) -> None:
        self.closed = True


class UnitOfWorkFactory:
    """Return the same in-memory unit of work, or a sequence of them."""

    def __init__(self, *units: InMemoryUnitOfWork) -> None:
        self._units = list(units) or [InMemoryUnitOfWork()]
        self.calls = 0

    def __call__(self) -> InMemoryUnitOfWork:
        index = min(self.calls, len(self._units) - 1)
        self.calls += 1
        return self._units[index]


def sample_analysis_record(
    user_id: UUID,
    *,
    analysis_id: UUID | None = None,
    summary_text: str = "Status summary",
    extra: dict[str, Any] | None = None,
) -> AnalysisRecord:
    """Build a synthetic analysis record for history tests."""
    now = datetime.now(UTC)
    payload = extra or {}
    return AnalysisRecord(
        id=analysis_id or uuid4(),
        user_id=user_id,
        created_at=now,
        updated_at=now,
        request_id=payload.get("request_id"),
        provider=payload.get("provider", "mock"),
        priority=payload.get("priority", "medium"),
        category=payload.get("category", "general"),
        source_type=payload.get("source_type", "email"),
        message_id=payload.get("message_id", "msg-001"),
        summary_text=summary_text,
        summary_confidence=payload.get("summary_confidence", 1.0),
        action_items=list(payload.get("action_items", [])),
        draft_reply=payload.get("draft_reply"),
        connector_account_id=payload.get("connector_account_id"),
    )


def sample_connector_account(
    user_id: UUID,
    *,
    account_id: UUID | None = None,
    provider: str = "fake",
    external_account_id: str = "mailbox-001",
    credential_ref: str | None = "credential-ref-001",
    status: ConnectorAccountStatus = ConnectorAccountStatus.ACTIVE,
    granted_capabilities: tuple | None = None,
) -> ConnectorAccountRecord:
    """Build a synthetic connector account for execution-target tests."""
    now = datetime.now(UTC)
    return ConnectorAccountRecord(
        id=account_id or uuid4(),
        user_id=user_id,
        provider=provider,
        external_account_id=external_account_id,
        credential_ref=credential_ref,
        status=status,
        created_at=now,
        updated_at=now,
        granted_capabilities=granted_capabilities,
    )
