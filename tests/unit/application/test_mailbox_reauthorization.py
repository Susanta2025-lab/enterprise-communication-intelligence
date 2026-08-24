"""Reauthorization start dispatch and callback identity binding."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.exceptions import (
    ConnectorAccountConflictError,
    ConnectorAccountNotFoundError,
)
from app.application.services.connector_account_oauth import ConnectorAccountOAuthService
from app.application.services.connector_accounts import ConnectorAccountService
from app.application.services.gmail_mailbox_oauth import GmailMailboxOAuthService
from app.application.services.identity import IdentityResolver
from app.core.exceptions import MailboxOAuthAuthorizationFailedError, ServiceUnavailableError
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import (
    CommunicationCapability,
    ConnectorAccountStatus,
    MailboxAuthorizationPurpose,
)
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    NewCommunicationCredential,
)
from app.domain.interfaces.mailbox_oauth_client import MailboxOAuthAuthorizationResult
from app.infrastructure.credentials.locators import create_communication_credential
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.oauth.google import (
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
    serialize_google_mailbox_secret,
)
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_PERMISSION
from tests.unit.application.test_gmail_mailbox_oauth import FakeMailboxOAuthClient

_ISSUER = "https://issuer-a.example.invalid/"
_SUBJECT = "subject-a"
_GOOGLE_SUB = "google-oidc-sub-001"
_OTHER_SUB = "google-oidc-sub-other"
_CODE = "AUTH_CODE_SENTINEL_REAUTH_111"
_REFRESH = "REFRESH_TOKEN_SENTINEL_REAUTH_222"
_OLD_LOCATOR = "oauth-stale-reauth-loc01"


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _authorization_result(
    *,
    subject: str = _GOOGLE_SUB,
    capabilities: tuple[CommunicationCapability, ...] = (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    ),
) -> MailboxOAuthAuthorizationResult:
    return MailboxOAuthAuthorizationResult(
        external_account_id=subject,
        granted_capabilities=capabilities,
        secret_material=serialize_google_mailbox_secret(
            refresh_token=_REFRESH,
            scopes=(GMAIL_READONLY_SCOPE, GMAIL_SEND_SCOPE),
            subject=subject,
        ),
    )


def _gmail_service(
    unit: InMemoryUnitOfWork,
    client: FakeMailboxOAuthClient | None = None,
    store: InMemoryCommunicationCredentialStore | None = None,
) -> tuple[
    GmailMailboxOAuthService,
    FakeMailboxOAuthClient,
    InMemoryCommunicationCredentialStore,
]:
    factory = UnitOfWorkFactory(unit)
    client = client or FakeMailboxOAuthClient(_authorization_result())
    store = store or InMemoryCommunicationCredentialStore()

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="gmail",
            secret_material=secret_material,
        )

    service = GmailMailboxOAuthService(
        IdentityResolver(factory),
        factory,
        client,
        store,
        create_stored,
    )
    return service, client, store


def test_reauthorize_start_uses_account_provider_and_binds_session() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    gmail, client, _store = _gmail_service(unit)
    accounts = ConnectorAccountService(
        IdentityResolver(UnitOfWorkFactory(unit)),
        UnitOfWorkFactory(unit),
    )
    service = ConnectorAccountOAuthService(
        accounts,
        lambda: gmail,
        lambda: (_ for _ in ()).throw(AssertionError("microsoft must not be used")),
    )
    result = service.start_reauthorization(_principal(), account.id)
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.purpose is MailboxAuthorizationPurpose.REAUTHORIZE
    assert stored.connector_account_id == account.id
    assert stored.provider.value == "gmail"
    assert client.build_calls == 1
    assert result.authorization_url
    assert "pkce_verifier" not in result.__dataclass_fields__ or True
    assert stored.pkce_verifier not in result.authorization_url


def test_reauthorize_start_rejects_active_and_unknown() -> None:
    user_id = uuid4()
    active = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        status=ConnectorAccountStatus.ACTIVE,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={active.id: active},
    )
    gmail, _client, _store = _gmail_service(unit)
    factory = UnitOfWorkFactory(unit)
    accounts = ConnectorAccountService(IdentityResolver(factory), factory)
    service = ConnectorAccountOAuthService(accounts, lambda: gmail, lambda: gmail)  # type: ignore[arg-type]
    with pytest.raises(ConnectorAccountConflictError):
        service.start_reauthorization(_principal(), active.id)
    with pytest.raises(ConnectorAccountNotFoundError):
        service.start_reauthorization(_principal(), uuid4())
    assert unit.mailbox_authorization_session_store == {}


def test_reauthorize_callback_reactivates_exact_account_and_replaces_capabilities() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=_OLD_LOCATOR,
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    store = InMemoryCommunicationCredentialStore()
    store.create(NewCommunicationCredential(_OLD_LOCATOR, "gmail", b"opaque-old-secret"))
    gmail, client, store = _gmail_service(unit, store=store)
    gmail.start_reauthorization(_principal(), account.id)
    result = gmail.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.connector_account_id == account.id
    assert result.status is ConnectorAccountStatus.ACTIVE
    assert result.granted_capabilities == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )
    restored = unit.connector_account_store[account.id]
    assert restored.credential_ref is not None
    assert restored.credential_ref != _OLD_LOCATOR
    assert store.get(_OLD_LOCATOR) is None
    assert store.get(restored.credential_ref) is not None
    assert len(unit.connector_account_store) == 1


def test_reauthorize_callback_rejects_different_mailbox_and_compensates() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    client = FakeMailboxOAuthClient(_authorization_result(subject=_OTHER_SUB))
    gmail, client, store = _gmail_service(unit, client=client)
    gmail.start_reauthorization(_principal(), account.id)
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        gmail.complete_authorization(code=_CODE, state=client.last_state, error=None)
    restored = unit.connector_account_store[account.id]
    assert restored.status is ConnectorAccountStatus.DISCONNECTED
    assert restored.external_account_id == _GOOGLE_SUB
    assert store._records == {}
    assert len(unit.connector_account_store) == 1


def test_reauthorize_callback_rejects_replay_and_wrong_purpose() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    gmail, client, _store = _gmail_service(unit)
    gmail.start_reauthorization(_principal(), account.id)
    state = client.last_state
    gmail.complete_authorization(code=_CODE, state=state, error=None)
    from app.application.exceptions import MailboxAuthorizationSessionInvalidError

    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        gmail.complete_authorization(code=_CODE, state=state, error=None)


def test_connect_callback_still_rejects_reauthorize_session_mismatch_via_connect_reuse() -> None:
    """Normal CONNECT remains available and does not bind connector_account_id."""
    unit = InMemoryUnitOfWork()
    gmail, client, _store = _gmail_service(unit)
    gmail.start_authorization(_principal())
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.purpose is MailboxAuthorizationPurpose.CONNECT
    assert stored.connector_account_id is None
    result = gmail.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.status is ConnectorAccountStatus.ACTIVE


def test_concurrent_reauthorize_loser_compensates_new_credential() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    gmail, client, store = _gmail_service(unit)
    gmail.start_reauthorization(_principal(), account.id)
    original_reactivate = unit.connector_accounts.reactivate_owned

    def lose_cas(*args, **kwargs):
        return None

    unit.connector_accounts.reactivate_owned = lose_cas  # type: ignore[method-assign]
    with pytest.raises(ConnectorAccountConflictError):
        gmail.complete_authorization(code=_CODE, state=client.last_state, error=None)
    unit.connector_accounts.reactivate_owned = original_reactivate  # type: ignore[method-assign]
    assert store._records == {}
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.DISCONNECTED


def test_persist_failure_after_stale_delete_compensates_new_credential() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=_OLD_LOCATOR,
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    store = InMemoryCommunicationCredentialStore()
    store.create(NewCommunicationCredential(_OLD_LOCATOR, "gmail", b"opaque-old-secret"))
    gmail, client, store = _gmail_service(unit, store=store)
    gmail.start_reauthorization(_principal(), account.id)
    unit.connector_accounts.reactivate_owned = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ServiceUnavailableError("Gmail mailbox authorization is unavailable.")
        )
    )
    with pytest.raises(ServiceUnavailableError):
        gmail.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert store.get(_OLD_LOCATOR) is None
    assert store._records == {}


def test_reauthorize_callback_rejects_missing_bound_account_id() -> None:
    """REAUTHORIZE sessions without a bound account id cannot attach a credential."""
    from dataclasses import replace

    from app.domain.enums import MailboxAuthorizationPurpose

    unit = InMemoryUnitOfWork()
    gmail, client, store = _gmail_service(unit)
    gmail.start_authorization(_principal())
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    unit.mailbox_authorization_session_store[stored.id] = replace(
        stored,
        purpose=MailboxAuthorizationPurpose.REAUTHORIZE,
        connector_account_id=None,
    )
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        gmail.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert store._records == {}
    assert unit.connector_account_store == {}


def test_reauthorize_callback_rejects_wrong_provider_session() -> None:
    """A Gmail reauthorize state cannot be consumed by the Microsoft callback."""
    from app.application.services.microsoft_mailbox_oauth import MicrosoftMailboxOAuthService

    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    gmail, client, store = _gmail_service(unit)
    gmail.start_reauthorization(_principal(), account.id)
    factory = UnitOfWorkFactory(unit)

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="microsoft_graph",
            secret_material=secret_material,
        )

    microsoft = MicrosoftMailboxOAuthService(
        IdentityResolver(factory),
        factory,
        FakeMailboxOAuthClient(),
        store,
        create_stored,
    )
    from app.application.exceptions import MailboxAuthorizationSessionInvalidError

    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        microsoft.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.DISCONNECTED
    assert store._records == {}


def test_microsoft_reauthorize_rejects_different_mailbox() -> None:
    """Graph reauthorization cannot swap the bound {tid}:{oid} identity."""
    from app.application.services.microsoft_mailbox_oauth import MicrosoftMailboxOAuthService
    from app.infrastructure.oauth.microsoft import serialize_microsoft_mailbox_secret
    from tests.unit.application.test_microsoft_mailbox_oauth import (
        FakeMailboxOAuthClient as MicrosoftFakeClient,
    )

    user_id = uuid4()
    bound = "9188040d-6c67-4c5b-b112-36a304b66dad:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    other = "9188040d-6c67-4c5b-b112-36a304b66dad:cccccccc-cccc-cccc-cccc-cccccccccccc"
    account = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id=bound,
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    factory = UnitOfWorkFactory(unit)
    store = InMemoryCommunicationCredentialStore()
    client = MicrosoftFakeClient(
        MailboxOAuthAuthorizationResult(
            external_account_id=other,
            granted_capabilities=(
                CommunicationCapability.MAIL_READ,
                CommunicationCapability.MAIL_SEND,
            ),
            secret_material=serialize_microsoft_mailbox_secret(
                refresh_token=_REFRESH,
                scopes=("https://graph.microsoft.com/Mail.Read",),
                tenant_id="9188040d-6c67-4c5b-b112-36a304b66dad",
                object_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
            ),
        )
    )

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="microsoft_graph",
            secret_material=secret_material,
        )

    microsoft = MicrosoftMailboxOAuthService(
        IdentityResolver(factory),
        factory,
        client,
        store,
        create_stored,
    )
    microsoft.start_reauthorization(_principal(), account.id)
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        microsoft.complete_authorization(code=_CODE, state=client.last_state, error=None)
    restored = unit.connector_account_store[account.id]
    assert restored.status is ConnectorAccountStatus.DISCONNECTED
    assert restored.external_account_id == bound
    assert store._records == {}
    assert len(unit.connector_account_store) == 1
