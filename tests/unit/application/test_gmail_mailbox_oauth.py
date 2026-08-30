"""Gmail mailbox OAuth application orchestration tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.exceptions import (
    MailboxAuthorizationSessionInvalidError,
    MailboxOAuthAuthorizationDeniedError,
)
from app.application.services.gmail_mailbox_oauth import GmailMailboxOAuthService
from app.application.services.identity import IdentityResolver
from app.core.exceptions import (
    MailboxOAuthAuthorizationFailedError,
    PersistenceError,
    ServiceUnavailableError,
)
from app.core.oauth_state import hash_oauth_state
from app.core.pkce import PkceS256
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import (
    CommunicationCapability,
    ConnectorAccountStatus,
)
from app.domain.interfaces.communication_credential_store import CommunicationCredentialRecord
from app.domain.interfaces.mailbox_oauth_client import MailboxOAuthAuthorizationResult
from app.infrastructure.credentials.locators import create_communication_credential
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.oauth.google import (
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
    deserialize_google_mailbox_secret,
    serialize_google_mailbox_secret,
)
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_PERMISSION

_ISSUER = "https://issuer-a.example.invalid/"
_SUBJECT = "subject-a"
_GOOGLE_SUB = "google-oidc-sub-001"
_CODE = "AUTH_CODE_SENTINEL_APP_111"
_REFRESH = "REFRESH_TOKEN_SENTINEL_APP_222"


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_ISSUER,
        subject=_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )


class FakeMailboxOAuthClient:
    def __init__(
        self,
        result: MailboxOAuthAuthorizationResult | None = None,
        *,
        exchange_error: Exception | None = None,
    ) -> None:
        self.exchange_calls = 0
        self.build_calls = 0
        self.last_state: str | None = None
        self.last_challenge: str | None = None
        self.last_verifier: str | None = None
        self.last_code: str | None = None
        self.last_account_selection: bool | None = None
        self.exchange_error = exchange_error
        self.result = result or _authorization_result()

    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
        account_selection: bool = False,
    ) -> str:
        self.build_calls += 1
        self.last_state = state
        self.last_challenge = code_challenge
        self.last_account_selection = account_selection
        return (
            "https://accounts.google.com/o/oauth2/auth"
            f"?state={state}&code_challenge={code_challenge}"
            f"&code_challenge_method={code_challenge_method}"
        )

    def exchange_authorization_code(
        self,
        *,
        code: str,
        code_verifier: str,
    ) -> MailboxOAuthAuthorizationResult:
        self.exchange_calls += 1
        self.last_code = code
        self.last_verifier = code_verifier
        if self.exchange_error is not None:
            raise self.exchange_error
        return self.result


def _authorization_result(
    *,
    subject: str = _GOOGLE_SUB,
    capabilities: tuple[CommunicationCapability, ...] = (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    ),
    scopes: tuple[str, ...] = (GMAIL_READONLY_SCOPE, GMAIL_SEND_SCOPE),
    display_identity: str | None = None,
) -> MailboxOAuthAuthorizationResult:
    return MailboxOAuthAuthorizationResult(
        external_account_id=subject,
        granted_capabilities=capabilities,
        secret_material=serialize_google_mailbox_secret(
            refresh_token=_REFRESH,
            scopes=scopes,
            subject=subject,
        ),
        display_identity=display_identity,
    )


def _service(
    unit: InMemoryUnitOfWork | None = None,
    client: FakeMailboxOAuthClient | None = None,
    store: InMemoryCommunicationCredentialStore | None = None,
) -> tuple[
    GmailMailboxOAuthService,
    InMemoryUnitOfWork,
    FakeMailboxOAuthClient,
    InMemoryCommunicationCredentialStore,
]:
    unit = unit or InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    client = client or FakeMailboxOAuthClient()
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
    return service, unit, client, store


def test_start_embeds_exact_session_state_and_pkce(
    log_events: list[dict],
) -> None:
    service, unit, client, _store = _service()
    result = service.start_authorization(_principal())
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert client.build_calls == 1
    assert client.last_state is not None
    assert hash_oauth_state(client.last_state) == stored.state_hash
    assert stored.pkce_verifier is not None
    assert client.last_challenge == PkceS256.code_challenge(stored.pkce_verifier)
    assert client.last_state in result.authorization_url
    assert client.last_challenge in result.authorization_url
    assert "code_challenge_method=S256" in result.authorization_url
    assert stored.pkce_verifier not in result.authorization_url
    blob = repr(log_events) + repr(result)
    assert stored.pkce_verifier not in blob
    assert stored.pkce_verifier not in repr(log_events)
    assert stored.state_hash not in repr(log_events)
    assert _REFRESH not in blob
    assert client.last_state not in repr(log_events)


def test_invalid_state_does_not_exchange(log_events: list[dict]) -> None:
    service, _unit, client, _store = _service()
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        service.complete_authorization(code=_CODE, state="unknown-state", error=None)
    assert client.exchange_calls == 0
    assert _CODE not in repr(log_events)
    assert "unknown-state" not in repr(log_events)


def test_consumed_state_does_not_exchange_again() -> None:
    service, _unit, client, _store = _service()
    service.start_authorization(_principal())
    state = client.last_state
    assert state is not None
    service.complete_authorization(code=_CODE, state=state, error=None)
    assert client.exchange_calls == 1
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        service.complete_authorization(code=_CODE, state=state, error=None)
    assert client.exchange_calls == 1


def test_google_denial_consumes_state_without_exchange() -> None:
    service, unit, client, _store = _service()
    service.start_authorization(_principal())
    state = client.last_state
    assert state is not None
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    with pytest.raises(MailboxOAuthAuthorizationDeniedError):
        service.complete_authorization(code=None, state=state, error="access_denied")
    assert client.exchange_calls == 0
    assert stored.consumed_at is not None or unit.mailbox_authorization_session_store[
        stored.id
    ].consumed_at is not None
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        service.complete_authorization(code=_CODE, state=state, error=None)
    assert client.exchange_calls == 0


def test_successful_callback_persists_sub_capabilities_and_locator() -> None:
    service, unit, client, store = _service()
    service.start_authorization(_principal())
    state = client.last_state
    assert state is not None
    stored_session = next(iter(unit.mailbox_authorization_session_store.values()))
    result = service.complete_authorization(code=_CODE, state=state, error=None)
    assert client.last_verifier == stored_session.pkce_verifier or client.last_verifier
    assert client.last_code == _CODE
    assert result.provider == "gmail"
    assert result.external_account_id == _GOOGLE_SUB
    assert result.status is ConnectorAccountStatus.ACTIVE
    assert result.granted_capabilities == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )
    assert result.reused_existing is False
    account = next(iter(unit.connector_account_store.values()))
    assert account.external_account_id == _GOOGLE_SUB
    assert account.credential_ref is not None
    assert account.credential_ref.startswith("oauth-")
    found = store.get(account.credential_ref)
    assert found is not None
    material = deserialize_google_mailbox_secret(found.secret_material)
    assert material.refresh_token == _REFRESH
    assert material.subject == _GOOGLE_SUB


def test_read_scope_required_does_not_create_account() -> None:
    client = FakeMailboxOAuthClient(
        _authorization_result(
            capabilities=(CommunicationCapability.MAIL_SEND,),
            scopes=(GMAIL_SEND_SCOPE,),
        )
    )
    service, unit, _client, store = _service(client=client)
    service.start_authorization(_principal())
    with pytest.raises(MailboxOAuthAuthorizationFailedError):
        service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert unit.connector_account_store == {}
    assert store.get("oauth-unused") is None


def test_partial_grant_succeeds_read_only() -> None:
    client = FakeMailboxOAuthClient(
        _authorization_result(
            capabilities=(CommunicationCapability.MAIL_READ,),
            scopes=(GMAIL_READONLY_SCOPE,),
        )
    )
    service, unit, _client, _store = _service(client=client)
    service.start_authorization(_principal())
    result = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.granted_capabilities == (CommunicationCapability.MAIL_READ,)
    account = next(iter(unit.connector_account_store.values()))
    assert account.granted_capabilities == (CommunicationCapability.MAIL_READ,)


def test_duplicate_active_account_does_not_overwrite_credential() -> None:
    user_id = uuid4()
    existing = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref="oauth-existing-live-locator01",
        granted_capabilities=(
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        ),
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={existing.id: existing},
    )
    service, unit, client, store = _service(unit=unit)
    service.start_authorization(_principal())
    result = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.reused_existing is True
    assert result.connector_account_id == existing.id
    restored = unit.connector_account_store[existing.id]
    assert restored.credential_ref == "oauth-existing-live-locator01"
    assert list(store._records) == []


def test_disconnected_account_is_reactivated_with_new_locator() -> None:
    user_id = uuid4()
    existing = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
        granted_capabilities=None,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={existing.id: existing},
    )
    service, unit, client, store = _service(unit=unit)
    service.start_authorization(_principal())
    result = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.reused_existing is False
    restored = unit.connector_account_store[existing.id]
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.credential_ref is not None
    assert restored.credential_ref.startswith("oauth-")
    assert restored.granted_capabilities == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )
    assert store.get(restored.credential_ref) is not None


def test_legacy_email_identity_is_not_merged() -> None:
    user_id = uuid4()
    legacy = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id="mailbox@example.com",
        credential_ref="demo-account",
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={legacy.id: legacy},
    )
    service, unit, client, _store = _service(unit=unit)
    service.start_authorization(_principal())
    result = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.external_account_id == _GOOGLE_SUB
    assert result.connector_account_id != legacy.id
    assert len(unit.connector_account_store) == 2
    assert unit.connector_account_store[legacy.id].external_account_id == "mailbox@example.com"


def test_db_failure_after_store_create_deletes_credential() -> None:
    service, unit, client, store = _service()
    service.start_authorization(_principal())

    def explode(*_args: object, **_kwargs: object):
        raise PersistenceError("Could not persist connector account.")

    unit.connector_accounts.create = explode  # type: ignore[method-assign]
    with pytest.raises(ServiceUnavailableError):
        service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert unit.connector_account_store == {}
    assert store._records == {}


def test_cleanup_failure_does_not_report_success() -> None:
    store = InMemoryCommunicationCredentialStore()
    created: dict[str, str] = {}

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        record = create_communication_credential(
            store,
            provider="gmail",
            secret_material=secret_material,
        )
        created["locator"] = record.credential_ref
        return record

    def explode_delete(_locator: str) -> None:
        raise RuntimeError("cleanup boom")

    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    client = FakeMailboxOAuthClient()
    service = GmailMailboxOAuthService(
        IdentityResolver(factory),
        factory,
        client,
        store,
        create_stored,
    )
    service.start_authorization(_principal())
    unit.connector_accounts.create = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PersistenceError("Could not persist connector account.")
        )
    )
    store.delete = explode_delete  # type: ignore[method-assign]
    with pytest.raises(ServiceUnavailableError):
        service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert created["locator"] in store._records


def test_exchange_uses_consumed_verifier() -> None:
    service, unit, client, _store = _service()
    service.start_authorization(_principal())
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    verifier = stored.pkce_verifier
    service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert client.last_verifier == verifier
    updated = unit.mailbox_authorization_session_store[stored.id]
    assert updated.pkce_verifier is None
    assert updated.consumed_at is not None
