"""Disconnect lifecycle: store-first cleanup, idempotency, and Google revoke."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.exceptions import ConnectorAccountNotFoundError
from app.application.services.connector_accounts import ConnectorAccountService
from app.application.services.identity import IdentityResolver
from app.core.exceptions import (
    CommunicationCredentialUnavailableError,
    ServiceUnavailableError,
)
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.communication_credential_store import NewCommunicationCredential
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.oauth import OAuthCommunicationCredentialResolver
from app.infrastructure.oauth.google import (
    GMAIL_READONLY_SCOPE,
    serialize_google_mailbox_secret,
)
from tests.support.in_memory_persistence import InMemoryUnitOfWork, UnitOfWorkFactory
from tests.support.jwt_tokens import TEST_PERMISSION
from tests.unit.infrastructure.credentials.conftest import FakeRefreshAdapter

_ISSUER = "https://issuer-a.example.invalid/"
_SUBJECT = "subject-a"
_PROVIDER = "gmail"
_ACCOUNT = "google-oidc-sub-001"
_LOCATOR = "oauth-disconnectloc0001"
_REFRESH = "REFRESH_TOKEN_SENTINEL_DISCONNECT_111"


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _seed_account(
    *,
    status: ConnectorAccountStatus = ConnectorAccountStatus.ACTIVE,
    credential_ref: str | None = _LOCATOR,
    granted_capabilities: tuple[CommunicationCapability, ...] | None = (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    ),
    user_id: UUID | None = None,
) -> tuple[UUID, ConnectorAccountRecord, InMemoryUnitOfWork]:
    owner = user_id or uuid4()
    now = datetime.now(UTC)
    account = ConnectorAccountRecord(
        id=uuid4(),
        user_id=owner,
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=credential_ref,
        status=status,
        created_at=now,
        updated_at=now,
        granted_capabilities=granted_capabilities,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): owner},
        connector_accounts={account.id: account},
    )
    return owner, account, unit


def _service(
    unit: InMemoryUnitOfWork,
    store: InMemoryCommunicationCredentialStore | None = None,
    revokers: dict | None = None,
) -> tuple[ConnectorAccountService, InMemoryCommunicationCredentialStore]:
    store = store or InMemoryCommunicationCredentialStore()
    factory = UnitOfWorkFactory(unit)
    service = ConnectorAccountService(
        IdentityResolver(factory),
        factory,
        credential_store=store,
        token_revokers=revokers,
    )
    return service, store


def test_owned_active_disconnect_clears_locator_grants_and_secret() -> None:
    _owner, account, unit = _seed_account()
    store = InMemoryCommunicationCredentialStore()
    store.create(
        NewCommunicationCredential(
            _LOCATOR,
            _PROVIDER,
            serialize_google_mailbox_secret(
                refresh_token=_REFRESH,
                scopes=(GMAIL_READONLY_SCOPE,),
                subject=_ACCOUNT,
            ),
        )
    )
    service, store = _service(unit, store=store)
    result = service.disconnect_owned(_principal(), account.id)
    assert result.status is ConnectorAccountStatus.DISCONNECTED
    assert result.granted_capabilities is None
    assert "credential_ref" not in asdict(result)
    stored = unit.connector_account_store[account.id]
    assert stored.credential_ref is None
    assert stored.granted_capabilities is None
    assert store.get(_LOCATOR) is None


def test_disconnect_invalidates_cached_access_token() -> None:
    _owner, account, unit = _seed_account()
    store = InMemoryCommunicationCredentialStore()
    material = serialize_google_mailbox_secret(
        refresh_token=_REFRESH,
        scopes=(GMAIL_READONLY_SCOPE,),
        subject=_ACCOUNT,
    )
    store.create(NewCommunicationCredential(_LOCATOR, _PROVIDER, material))
    adapter = FakeRefreshAdapter(token="cached-access-token")
    resolver = OAuthCommunicationCredentialResolver(store, {_PROVIDER: adapter})
    token_provider = resolver.resolve(credential_ref=_LOCATOR, provider=_PROVIDER)
    assert token_provider() == "cached-access-token"
    service, _store = _service(unit, store=store)
    service.disconnect_owned(_principal(), account.id)
    with pytest.raises(CommunicationCredentialUnavailableError):
        token_provider()


def test_repeated_disconnect_is_idempotent() -> None:
    _owner, account, unit = _seed_account()
    service, store = _service(unit)
    first = service.disconnect_owned(_principal(), account.id)
    second = service.disconnect_owned(_principal(), account.id)
    assert first.status is ConnectorAccountStatus.DISCONNECTED
    assert second.status is ConnectorAccountStatus.DISCONNECTED
    assert unit.connector_account_store[account.id].credential_ref is None
    assert store.get(_LOCATOR) is None


def test_unknown_and_cross_user_disconnect_are_indistinguishable() -> None:
    owner = uuid4()
    other = uuid4()
    _owner, account, unit = _seed_account(user_id=owner)
    unit.identities[(_ISSUER, _SUBJECT)] = other
    service, _store = _service(unit)
    with pytest.raises(ConnectorAccountNotFoundError) as cross:
        service.disconnect_owned(_principal(), account.id)
    missing = uuid4()
    with pytest.raises(ConnectorAccountNotFoundError) as unknown:
        service.disconnect_owned(_principal(), missing)
    assert cross.value.message == unknown.value.message
    assert str(account.id) not in cross.value.message
    assert str(missing) not in unknown.value.message
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE


def test_credential_store_failure_fails_closed_without_clearing_locator() -> None:
    class _BoomStore(InMemoryCommunicationCredentialStore):
        def delete(self, credential_ref: str) -> None:
            raise CommunicationCredentialUnavailableError()

    _owner, account, unit = _seed_account()
    store = _BoomStore()
    store.create(NewCommunicationCredential(_LOCATOR, _PROVIDER, b"opaque-secret-v1"))
    service, _store = _service(unit, store=store)
    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.disconnect_owned(_principal(), account.id)
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE
    assert unit.connector_account_store[account.id].credential_ref == _LOCATOR
    assert _LOCATOR not in exc_info.value.message
    assert _REFRESH not in str(exc_info.value)


def test_google_revoke_is_best_effort_after_local_disconnect() -> None:
    class _Revoker:
        def __init__(self) -> None:
            self.calls = 0
            self.fail = False

        def revoke(self, secret_material: bytes) -> None:
            self.calls += 1
            if self.fail:
                raise RuntimeError("remote revoke failed")

    _owner, account, unit = _seed_account()
    store = InMemoryCommunicationCredentialStore()
    material = serialize_google_mailbox_secret(
        refresh_token=_REFRESH,
        scopes=(GMAIL_READONLY_SCOPE,),
        subject=_ACCOUNT,
    )
    store.create(NewCommunicationCredential(_LOCATOR, _PROVIDER, material))
    revoker = _Revoker()
    revoker.fail = True
    service, _store = _service(unit, store=store, revokers={_PROVIDER: revoker})
    result = service.disconnect_owned(_principal(), account.id)
    assert result.status is ConnectorAccountStatus.DISCONNECTED
    assert store.get(_LOCATOR) is None
    assert revoker.calls == 1


def test_microsoft_disconnect_does_not_require_a_revoker() -> None:
    user_id = uuid4()
    now = datetime.now(UTC)
    account = ConnectorAccountRecord(
        id=uuid4(),
        user_id=user_id,
        provider="microsoft_graph",
        external_account_id="tid:oid",
        credential_ref=_LOCATOR,
        status=ConnectorAccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    store = InMemoryCommunicationCredentialStore()
    store.create(NewCommunicationCredential(_LOCATOR, "microsoft_graph", b"opaque-secret-v1"))
    service, _store = _service(unit, store=store)
    result = service.disconnect_owned(_principal(), account.id)
    assert result.status is ConnectorAccountStatus.DISCONNECTED
    assert store.get(_LOCATOR) is None
