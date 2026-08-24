"""Unit tests for MailboxAuthorizationSessionService."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    ConnectorAccountConflictError,
    ConnectorAccountNotFoundError,
    MailboxAuthorizationSessionInvalidError,
    UnsupportedMailboxAuthorizationProviderError,
)
from app.application.services.identity import IdentityResolver
from app.application.services.mailbox_authorization_sessions import (
    DEFAULT_MAILBOX_AUTHORIZATION_CAPABILITIES,
    MailboxAuthorizationSessionService,
)
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.oauth_state import hash_oauth_state, is_oauth_state_hash
from app.core.pkce import PkceS256
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import (
    CommunicationCapability,
    ConnectorAccountStatus,
    MailboxAuthorizationProvider,
    MailboxAuthorizationPurpose,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from tests.support.in_memory_persistence import InMemoryUnitOfWork, UnitOfWorkFactory
from tests.support.jwt_tokens import TEST_PERMISSION

_ISSUER_A = "https://issuer-a.example.invalid/"
_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_A = "subject-a"
_SUBJECT_B = "subject-b"


def _principal(
    *,
    issuer: str = _ISSUER_A,
    subject: str = _SUBJECT_A,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=issuer,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _service(
    *units: InMemoryUnitOfWork,
    session_ttl_seconds: int = 600,
    clock: object | None = None,
) -> tuple[MailboxAuthorizationSessionService, tuple[InMemoryUnitOfWork, ...]]:
    factory = UnitOfWorkFactory(*units) if units else UnitOfWorkFactory()
    stored = units if units else (factory._units[0],)
    kwargs: dict[str, object] = {"session_ttl_seconds": session_ttl_seconds}
    if clock is not None:
        kwargs["clock"] = clock
    service = MailboxAuthorizationSessionService(
        IdentityResolver(factory),
        factory,
        **kwargs,  # type: ignore[arg-type]
    )
    return service, stored


def _owned_gmail_account(user_id: UUID) -> ConnectorAccountRecord:
    now = datetime.now(UTC)
    return ConnectorAccountRecord(
        id=uuid4(),
        user_id=user_id,
        provider="gmail",
        external_account_id="mailbox-001",
        credential_ref="demo-account",
        status=ConnectorAccountStatus.DISCONNECTED,
        created_at=now,
        updated_at=now,
        granted_capabilities=None,
    )


def test_start_connect_session_persists_hash_not_raw_state(
    log_events: list[dict],
) -> None:
    """Connect sessions bind the user and persist only the state hash."""
    service, units = _service()
    unit = units[0]
    result = service.start_authorization(
        _principal(),
        provider="gmail",
        purpose="connect",
    )

    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert result.provider is MailboxAuthorizationProvider.GMAIL
    assert result.code_challenge_method == "S256"
    assert result.code_challenge == PkceS256.code_challenge(stored.pkce_verifier or "")
    assert result.requested_capabilities == DEFAULT_MAILBOX_AUTHORIZATION_CAPABILITIES
    assert result.state != stored.state_hash
    assert stored.state_hash == hash_oauth_state(result.state)
    assert is_oauth_state_hash(stored.state_hash)
    assert stored.pkce_verifier is not None
    assert stored.user_id == unit.identities[(_ISSUER_A, _SUBJECT_A)]
    assert stored.purpose is MailboxAuthorizationPurpose.CONNECT
    assert stored.connector_account_id is None
    assert "pkce_verifier" not in asdict(result)
    assert "user_id" not in asdict(result)
    assert "credential_ref" not in asdict(result)
    serialized_logs = repr(log_events)
    assert result.state not in serialized_logs
    assert stored.state_hash not in serialized_logs
    assert stored.pkce_verifier not in serialized_logs


def test_start_reauthorize_requires_owned_matching_account() -> None:
    """Reauthorize binds an owned connector account of the same provider."""
    user_id = uuid4()
    account = _owned_gmail_account(user_id)
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts={account.id: account},
    )
    service, _units = _service(unit)
    result = service.start_authorization(
        _principal(),
        provider="gmail",
        purpose="reauthorize",
        connector_account_id=account.id,
    )
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert result.authorization_session_id == stored.id
    assert stored.connector_account_id == account.id
    assert stored.purpose is MailboxAuthorizationPurpose.REAUTHORIZE


def test_start_reauthorize_active_account_conflicts() -> None:
    """ACTIVE accounts cannot start a reauthorize session."""
    user_id = uuid4()
    now = datetime.now(UTC)
    account = ConnectorAccountRecord(
        id=uuid4(),
        user_id=user_id,
        provider="gmail",
        external_account_id="mailbox-001",
        credential_ref="oauth-active-locator-01",
        status=ConnectorAccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts={account.id: account},
    )
    service, _units = _service(unit)
    with pytest.raises(ConnectorAccountConflictError):
        service.start_authorization(
            _principal(),
            provider="gmail",
            purpose="reauthorize",
            connector_account_id=account.id,
        )
    assert unit.mailbox_authorization_session_store == {}


def test_start_reauthorize_reauth_required_account_is_accepted() -> None:
    """REAUTH_REQUIRED accounts may start a reauthorize session."""
    user_id = uuid4()
    now = datetime.now(UTC)
    account = ConnectorAccountRecord(
        id=uuid4(),
        user_id=user_id,
        provider="gmail",
        external_account_id="mailbox-001",
        credential_ref="oauth-stale-locator-01",
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
        created_at=now,
        updated_at=now,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts={account.id: account},
    )
    service, _units = _service(unit)
    result = service.start_authorization(
        _principal(),
        provider="gmail",
        purpose="reauthorize",
        connector_account_id=account.id,
    )
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.purpose is MailboxAuthorizationPurpose.REAUTHORIZE
    assert stored.connector_account_id == account.id
    assert result.authorization_session_id == stored.id


def test_cross_user_reauthorize_is_not_found() -> None:
    """Unknown and cross-user accounts use the same not-found error."""
    owner = uuid4()
    other = uuid4()
    account = _owned_gmail_account(owner)
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): other},
        connector_accounts={account.id: account},
    )
    service, _units = _service(unit)
    with pytest.raises(ConnectorAccountNotFoundError) as exc_info:
        service.start_authorization(
            _principal(),
            provider="gmail",
            purpose="reauthorize",
            connector_account_id=account.id,
        )
    assert str(account.id) not in exc_info.value.message
    assert str(owner) not in exc_info.value.message
    assert unit.mailbox_authorization_session_store == {}


def test_unknown_connector_account_reauthorize_is_not_found() -> None:
    """Reauthorize of a missing account does not leak existence."""
    service, units = _service()
    missing = uuid4()
    with pytest.raises(ConnectorAccountNotFoundError) as exc_info:
        service.start_authorization(
            _principal(),
            provider="gmail",
            purpose="reauthorize",
            connector_account_id=missing,
        )
    assert str(missing) not in exc_info.value.message
    assert units[0].mailbox_authorization_session_store == {}


def test_reauthorize_provider_mismatch_is_not_found() -> None:
    """An owned Graph account cannot start a Gmail reauthorize session."""
    user_id = uuid4()
    now = datetime.now(UTC)
    account = ConnectorAccountRecord(
        id=uuid4(),
        user_id=user_id,
        provider="microsoft_graph",
        external_account_id="mailbox-001",
        credential_ref="demo-account",
        status=ConnectorAccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts={account.id: account},
    )
    service, _units = _service(unit)
    with pytest.raises(ConnectorAccountNotFoundError):
        service.start_authorization(
            _principal(),
            provider="gmail",
            purpose="reauthorize",
            connector_account_id=account.id,
        )


def test_unsupported_provider_is_rejected() -> None:
    """Authorization sessions allow gmail and microsoft_graph only."""
    service, units = _service()
    for provider in ("fake", "google", "graph", "microsoft", "gmail.com", "Gmail"):
        with pytest.raises(UnsupportedMailboxAuthorizationProviderError) as exc_info:
            service.start_authorization(
                _principal(),
                provider=provider,
                purpose="connect",
            )
        assert provider not in exc_info.value.message
        assert units[0].mailbox_authorization_session_store == {}


def test_consume_unsupported_provider_does_not_enumerate_sessions() -> None:
    """An unsupported consume provider is rejected before session lookup."""
    service, units = _service()
    started = service.start_authorization(_principal(), provider="gmail", purpose="connect")
    with pytest.raises(UnsupportedMailboxAuthorizationProviderError):
        service.consume_authorization_state(provider="google", state=started.state)
    stored = next(iter(units[0].mailbox_authorization_session_store.values()))
    assert stored.consumed_at is None
    assert stored.pkce_verifier is not None


def test_consume_succeeds_once_and_clears_verifier(
    log_events: list[dict],
) -> None:
    """The first consume returns the verifier in memory and clears storage."""
    service, units = _service()
    unit = units[0]
    started = service.start_authorization(
        _principal(),
        provider="microsoft_graph",
        purpose="connect",
    )
    stored_before = next(iter(unit.mailbox_authorization_session_store.values()))
    verifier = stored_before.pkce_verifier
    consumed = service.consume_authorization_state(
        provider="microsoft_graph",
        state=started.state,
    )
    stored = unit.mailbox_authorization_session_store[consumed.authorization_session_id]
    assert consumed.pkce_verifier == verifier
    assert consumed.user_id == stored.user_id
    assert consumed.provider is MailboxAuthorizationProvider.MICROSOFT_GRAPH
    assert consumed.purpose is MailboxAuthorizationPurpose.CONNECT
    assert consumed.requested_capabilities == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )
    assert stored.consumed_at is not None
    assert stored.pkce_verifier is None
    serialized = repr(log_events)
    assert started.state not in serialized
    assert verifier not in serialized
    assert "user_id" not in MailboxAuthorizationSessionInvalidError().message


def test_second_consume_fails_with_generic_invalid_error() -> None:
    """Already-consumed state cannot be reused."""
    service, _units = _service()
    started = service.start_authorization(
        _principal(),
        provider="gmail",
        purpose="connect",
    )
    service.consume_authorization_state(provider="gmail", state=started.state)
    with pytest.raises(MailboxAuthorizationSessionInvalidError) as exc_info:
        service.consume_authorization_state(provider="gmail", state=started.state)
    assert started.state not in str(exc_info.value)
    assert started.authorization_session_id.hex not in exc_info.value.message


def test_expired_session_cannot_be_consumed() -> None:
    """expires_at <= now is a generic invalid session."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)

    def _clock() -> datetime:
        return now

    service, units = _service(session_ttl_seconds=60, clock=_clock)
    started = service.start_authorization(
        _principal(),
        provider="gmail",
        purpose="connect",
    )
    stored = next(iter(units[0].mailbox_authorization_session_store.values()))
    units[0].mailbox_authorization_session_store[stored.id] = stored.__class__(
        id=stored.id,
        user_id=stored.user_id,
        provider=stored.provider,
        purpose=stored.purpose,
        connector_account_id=stored.connector_account_id,
        state_hash=stored.state_hash,
        pkce_verifier=stored.pkce_verifier,
        requested_capabilities=stored.requested_capabilities,
        created_at=stored.created_at,
        expires_at=now,
        consumed_at=None,
    )
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        service.consume_authorization_state(provider="gmail", state=started.state)


def test_provider_mismatch_on_consume_is_generic_invalid() -> None:
    """A Gmail session cannot be consumed as Microsoft Graph."""
    service, _units = _service()
    started = service.start_authorization(
        _principal(),
        provider="gmail",
        purpose="connect",
    )
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        service.consume_authorization_state(
            provider="microsoft_graph",
            state=started.state,
        )


def test_malformed_state_is_generic_invalid() -> None:
    """Empty or missing state does not enumerate session existence."""
    service, _units = _service()
    service.start_authorization(_principal(), provider="gmail", purpose="connect")
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        service.consume_authorization_state(provider="gmail", state="")
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        service.consume_authorization_state(provider="gmail", state="not-a-real-state")


def test_connect_rejects_connector_account_id() -> None:
    """Connect sessions must not bind a connector account."""
    service, _units = _service()
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        service.start_authorization(
            _principal(),
            provider="gmail",
            purpose="connect",
            connector_account_id=uuid4(),
        )


def test_delete_expired_removes_elapsed_sessions() -> None:
    """Expired rows can be purged without a scheduled worker in 13A."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    service, units = _service(clock=lambda: now)
    started = service.start_authorization(
        _principal(),
        provider="gmail",
        purpose="connect",
    )
    stored = next(iter(units[0].mailbox_authorization_session_store.values()))
    units[0].mailbox_authorization_session_store[stored.id] = stored.__class__(
        id=stored.id,
        user_id=stored.user_id,
        provider=stored.provider,
        purpose=stored.purpose,
        connector_account_id=stored.connector_account_id,
        state_hash=stored.state_hash,
        pkce_verifier=stored.pkce_verifier,
        requested_capabilities=stored.requested_capabilities,
        created_at=stored.created_at,
        expires_at=now - timedelta(seconds=1),
        consumed_at=None,
    )
    deleted = service.delete_expired(before=now)
    assert deleted == 1
    assert units[0].mailbox_authorization_session_store == {}
    assert started.authorization_session_id not in units[0].mailbox_authorization_session_store


def test_persistence_failure_on_start_is_unavailable() -> None:
    """Repository failures become a generic availability error."""
    unit = InMemoryUnitOfWork(fail_commit=True)
    service, _units = _service(unit)
    with pytest.raises(ServiceUnavailableError):
        service.start_authorization(_principal(), provider="gmail", purpose="connect")


def test_ttl_out_of_range_is_rejected() -> None:
    """The service does not accept unbounded session lifetimes."""
    with pytest.raises(ValueError, match="TTL"):
        MailboxAuthorizationSessionService(
            IdentityResolver(UnitOfWorkFactory()),
            UnitOfWorkFactory(),
            session_ttl_seconds=59,
        )
    with pytest.raises(ValueError, match="TTL"):
        MailboxAuthorizationSessionService(
            IdentityResolver(UnitOfWorkFactory()),
            UnitOfWorkFactory(),
            session_ttl_seconds=1801,
        )


def test_consume_persistence_failure_is_unavailable() -> None:
    """Consume database failures are not turned into invalid-session errors."""
    start_unit = InMemoryUnitOfWork()
    start_service, _units = _service(start_unit)
    started = start_service.start_authorization(
        _principal(),
        provider="gmail",
        purpose="connect",
    )
    failing = InMemoryUnitOfWork(
        identities=start_unit.identities,
        mailbox_authorization_sessions=start_unit.mailbox_authorization_session_store,
        commit_error=PersistenceError("Could not commit persistence changes."),
    )
    consume_service, _consume_units = _service(failing)
    with pytest.raises(ServiceUnavailableError):
        consume_service.consume_authorization_state(provider="gmail", state=started.state)
