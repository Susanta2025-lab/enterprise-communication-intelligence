"""CONNECT_ANOTHER is distinct from CONNECT and exact-account REAUTHORIZE."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.exceptions import MailboxAuthorizationSessionInvalidError
from app.application.services.identity import IdentityResolver
from app.application.services.mailbox_authorization_sessions import (
    MailboxAuthorizationSessionService,
)
from app.core.exceptions import MailboxOAuthIdentityMismatchError
from app.domain.enums import (
    CommunicationCapability,
    ConnectorAccountStatus,
    MailboxAuthorizationPurpose,
)
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.unit.application.test_gmail_mailbox_oauth import (
    _GOOGLE_SUB,
    _ISSUER,
    _REFRESH,
    _SUBJECT,
    FakeMailboxOAuthClient,
    _authorization_result,
    _principal,
    _service,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    _EXTERNAL,
    _OID,
    MSA_TENANT_ID,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    _ISSUER as _MS_ISSUER,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    _REFRESH as _MS_REFRESH,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    _SUBJECT as _MS_SUBJECT,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    FakeMailboxOAuthClient as MicrosoftFakeClient,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    _authorization_result as _microsoft_authorization_result,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    _principal as _microsoft_principal,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    _service as _microsoft_service,
)

_OTHER_SUB = "google-oidc-sub-other"
_OTHER_OID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_OTHER_EXTERNAL = f"{MSA_TENANT_ID}:{_OTHER_OID}"
_DISPLAY = "ops.mailbox@contoso.example"
_CODE = "AUTH_CODE_SENTINEL_APP_111"
_MS_CODE = "AUTH_CODE_SENTINEL_MS_APP_111"


def test_gmail_connect_another_requests_account_selection_and_is_unbound() -> None:
    service, unit, client, _store = _service()
    service.start_connect_another(_principal())
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.purpose is MailboxAuthorizationPurpose.CONNECT_ANOTHER
    assert stored.connector_account_id is None
    assert client.last_account_selection is True


def test_gmail_first_connect_does_not_request_account_selection() -> None:
    service, _unit, client, _store = _service()
    service.start_authorization(_principal())
    assert client.last_account_selection is False


def test_gmail_reauthorize_does_not_request_account_selection() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        status=ConnectorAccountStatus.DISCONNECTED,
        credential_ref=None,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    service, _unit, client, _store = _service(unit=unit)
    service.start_reauthorization(_principal(), account.id)
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.purpose is MailboxAuthorizationPurpose.REAUTHORIZE
    assert stored.connector_account_id == account.id
    assert client.last_account_selection is False


def test_gmail_connect_another_creates_second_row_without_mutating_first() -> None:
    user_id = uuid4()
    existing = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref="oauth-existing-gmail-01",
        display_identity="first.mailbox@contoso.example",
        granted_capabilities=(
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        ),
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={existing.id: existing},
    )
    client = FakeMailboxOAuthClient(
        _authorization_result(subject=_OTHER_SUB, display_identity=_DISPLAY)
    )
    service, unit, client, _store = _service(unit=unit, client=client)
    service.start_connect_another(_principal())
    result = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.reused_existing is False
    assert result.connector_account_id != existing.id
    assert result.external_account_id == _OTHER_SUB
    assert len(unit.connector_account_store) == 2
    first = unit.connector_account_store[existing.id]
    second = unit.connector_account_store[result.connector_account_id]
    assert first.external_account_id == _GOOGLE_SUB
    assert first.credential_ref == "oauth-existing-gmail-01"
    assert first.display_identity == "first.mailbox@contoso.example"
    assert first.status is ConnectorAccountStatus.ACTIVE
    assert second.external_account_id == _OTHER_SUB
    assert second.display_identity == _DISPLAY
    assert second.status is ConnectorAccountStatus.ACTIVE


def test_gmail_connect_another_same_account_reuses_existing_row() -> None:
    user_id = uuid4()
    existing = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref="oauth-existing-gmail-01",
        display_identity="first.mailbox@contoso.example",
        granted_capabilities=(
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        ),
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={existing.id: existing},
    )
    client = FakeMailboxOAuthClient(
        _authorization_result(subject=_GOOGLE_SUB, display_identity=_DISPLAY)
    )
    service, unit, client, _store = _service(unit=unit, client=client)
    service.start_connect_another(_principal())
    result = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.reused_existing is True
    assert result.connector_account_id == existing.id
    assert len(unit.connector_account_store) == 1
    restored = unit.connector_account_store[existing.id]
    assert restored.credential_ref == "oauth-existing-gmail-01"
    assert restored.display_identity == "first.mailbox@contoso.example"


def test_gmail_connect_another_reactivates_same_disconnected_row() -> None:
    user_id = uuid4()
    disconnected = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        status=ConnectorAccountStatus.DISCONNECTED,
        credential_ref=None,
        display_identity="first.mailbox@contoso.example",
    )
    other = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_OTHER_SUB,
        credential_ref="oauth-other-gmail-01",
        display_identity="other.mailbox@contoso.example",
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={disconnected.id: disconnected, other.id: other},
    )
    client = FakeMailboxOAuthClient(
        _authorization_result(subject=_GOOGLE_SUB, display_identity=_DISPLAY)
    )
    service, unit, client, _store = _service(unit=unit, client=client)
    service.start_connect_another(_principal())
    result = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.reused_existing is False
    assert result.connector_account_id == disconnected.id
    assert len(unit.connector_account_store) == 2
    restored = unit.connector_account_store[disconnected.id]
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.external_account_id == _GOOGLE_SUB
    assert restored.credential_ref is not None
    assert restored.display_identity == _DISPLAY
    untouched = unit.connector_account_store[other.id]
    assert untouched.credential_ref == "oauth-other-gmail-01"
    assert untouched.display_identity == "other.mailbox@contoso.example"
    assert untouched.status is ConnectorAccountStatus.ACTIVE


def test_gmail_connect_another_reactivates_same_reauth_required_row() -> None:
    user_id = uuid4()
    required = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
        credential_ref="oauth-stale-gmail-01",
        display_identity="first.mailbox@contoso.example",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    other = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_OTHER_SUB,
        credential_ref="oauth-other-gmail-01",
        display_identity="other.mailbox@contoso.example",
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={required.id: required, other.id: other},
    )
    client = FakeMailboxOAuthClient(
        _authorization_result(subject=_GOOGLE_SUB, display_identity=_DISPLAY)
    )
    service, unit, client, _store = _service(unit=unit, client=client)
    service.start_connect_another(_principal())
    result = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    assert result.connector_account_id == required.id
    assert len(unit.connector_account_store) == 2
    restored = unit.connector_account_store[required.id]
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.external_account_id == _GOOGLE_SUB
    assert restored.credential_ref != "oauth-stale-gmail-01"
    assert restored.display_identity == _DISPLAY
    untouched = unit.connector_account_store[other.id]
    assert untouched.credential_ref == "oauth-other-gmail-01"
    assert untouched.status is ConnectorAccountStatus.ACTIVE


def test_gmail_connect_another_completion_logs_omit_identities_and_secrets(
    log_events: list[dict],
) -> None:
    client = FakeMailboxOAuthClient(
        _authorization_result(subject=_GOOGLE_SUB, display_identity=_DISPLAY)
    )
    service, _unit, client, _store = _service(client=client)
    service.start_connect_another(_principal())
    service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    completed = [
        event
        for event in log_events
        if event.get("event") in {
            "gmail_oauth_authorization_completed",
            "gmail_oauth_authorization_started",
        }
    ]
    assert completed
    blob = repr(completed)
    assert _DISPLAY not in blob
    assert _GOOGLE_SUB not in blob
    assert _REFRESH not in blob
    assert _CODE not in blob
    assert "external_account_id" not in blob
    assert "display_identity" not in blob
    assert "credential_ref" not in blob
    assert "refresh_token" not in blob
    assert "access_token" not in blob
    assert "id_token" not in blob


def test_gmail_connect_another_does_not_weaken_reauthorize_identity_check() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        status=ConnectorAccountStatus.DISCONNECTED,
        credential_ref=None,
        display_identity=_DISPLAY,
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER, _SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    client = FakeMailboxOAuthClient(_authorization_result(subject=_OTHER_SUB))
    service, unit, client, store = _service(unit=unit, client=client)
    service.start_reauthorization(_principal(), account.id)
    with pytest.raises(MailboxOAuthIdentityMismatchError):
        service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    restored = unit.connector_account_store[account.id]
    assert restored.status is ConnectorAccountStatus.DISCONNECTED
    assert restored.external_account_id == _GOOGLE_SUB
    assert restored.display_identity == _DISPLAY
    assert store._records == {}


def test_gmail_display_identity_survives_disconnect_and_updates_on_reconnect() -> None:
    client = FakeMailboxOAuthClient(
        _authorization_result(subject=_GOOGLE_SUB, display_identity=_DISPLAY)
    )
    service, unit, client, _store = _service(client=client)
    service.start_authorization(_principal())
    created = service.complete_authorization(code=_CODE, state=client.last_state, error=None)
    stored = unit.connector_account_store[created.connector_account_id]
    assert stored.display_identity == _DISPLAY
    disconnected = unit.connector_accounts.disconnect_owned(stored.id, stored.user_id)
    assert disconnected is not None
    assert disconnected.status is ConnectorAccountStatus.DISCONNECTED
    assert disconnected.display_identity == _DISPLAY
    assert disconnected.credential_ref is None
    client.result = _authorization_result(
        subject=_GOOGLE_SUB,
        display_identity="updated.mailbox@contoso.example",
    )
    service.start_reauthorization(_principal(), stored.id)
    recovered = service.complete_authorization(
        code=_CODE,
        state=client.last_state,
        error=None,
    )
    assert recovered.connector_account_id == stored.id
    restored = unit.connector_account_store[stored.id]
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.display_identity == "updated.mailbox@contoso.example"
    assert restored.external_account_id == _GOOGLE_SUB


def test_microsoft_connect_another_requests_account_selection() -> None:
    service, unit, client, _store = _microsoft_service()
    service.start_connect_another(_microsoft_principal())
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.purpose is MailboxAuthorizationPurpose.CONNECT_ANOTHER
    assert stored.connector_account_id is None
    assert client.last_account_selection is True


def test_microsoft_connect_another_creates_second_row_without_mutating_first() -> None:
    user_id = uuid4()
    existing = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id=_EXTERNAL,
        credential_ref="oauth-existing-graph-01",
        display_identity="first.outlook@contoso.example",
        granted_capabilities=(
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        ),
    )
    unit = InMemoryUnitOfWork(
        identities={(_MS_ISSUER, _MS_SUBJECT): user_id},
        connector_accounts={existing.id: existing},
    )
    client = MicrosoftFakeClient(
        _microsoft_authorization_result(
            external_account_id=_OTHER_EXTERNAL,
            object_id=_OTHER_OID,
            display_identity="second.outlook@contoso.example",
        )
    )
    service, unit, client, _store = _microsoft_service(unit=unit, client=client)
    service.start_connect_another(_microsoft_principal())
    result = service.complete_authorization(
        code=_MS_CODE,
        state=client.last_state,
        error=None,
    )
    assert result.reused_existing is False
    assert result.connector_account_id != existing.id
    assert len(unit.connector_account_store) == 2
    first = unit.connector_account_store[existing.id]
    assert first.external_account_id == _EXTERNAL
    assert first.credential_ref == "oauth-existing-graph-01"
    assert first.display_identity == "first.outlook@contoso.example"


def test_microsoft_connect_another_same_account_reuses_existing_row() -> None:
    user_id = uuid4()
    existing = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id=_EXTERNAL,
        credential_ref="oauth-existing-graph-01",
        display_identity="first.outlook@contoso.example",
        granted_capabilities=(
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        ),
    )
    unit = InMemoryUnitOfWork(
        identities={(_MS_ISSUER, _MS_SUBJECT): user_id},
        connector_accounts={existing.id: existing},
    )
    client = MicrosoftFakeClient(
        _microsoft_authorization_result(display_identity="updated.outlook@contoso.example")
    )
    service, unit, client, _store = _microsoft_service(unit=unit, client=client)
    service.start_connect_another(_microsoft_principal())
    result = service.complete_authorization(
        code=_MS_CODE,
        state=client.last_state,
        error=None,
    )
    assert result.reused_existing is True
    assert result.connector_account_id == existing.id
    assert len(unit.connector_account_store) == 1
    restored = unit.connector_account_store[existing.id]
    assert restored.credential_ref == "oauth-existing-graph-01"
    assert restored.display_identity == "first.outlook@contoso.example"
    assert restored.external_account_id == _EXTERNAL


def test_microsoft_connect_another_reactivates_same_disconnected_row() -> None:
    user_id = uuid4()
    disconnected = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id=_EXTERNAL,
        status=ConnectorAccountStatus.DISCONNECTED,
        credential_ref=None,
        display_identity="first.outlook@contoso.example",
    )
    other = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id=_OTHER_EXTERNAL,
        credential_ref="oauth-other-graph-01",
        display_identity="other.outlook@contoso.example",
    )
    unit = InMemoryUnitOfWork(
        identities={(_MS_ISSUER, _MS_SUBJECT): user_id},
        connector_accounts={disconnected.id: disconnected, other.id: other},
    )
    client = MicrosoftFakeClient(
        _microsoft_authorization_result(display_identity=_DISPLAY)
    )
    service, unit, client, _store = _microsoft_service(unit=unit, client=client)
    service.start_connect_another(_microsoft_principal())
    result = service.complete_authorization(
        code=_MS_CODE,
        state=client.last_state,
        error=None,
    )
    assert result.connector_account_id == disconnected.id
    assert len(unit.connector_account_store) == 2
    restored = unit.connector_account_store[disconnected.id]
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.external_account_id == _EXTERNAL
    assert restored.credential_ref is not None
    assert restored.display_identity == _DISPLAY
    untouched = unit.connector_account_store[other.id]
    assert untouched.credential_ref == "oauth-other-graph-01"
    assert untouched.display_identity == "other.outlook@contoso.example"


def test_microsoft_connect_another_reactivates_same_reauth_required_row() -> None:
    user_id = uuid4()
    required = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id=_EXTERNAL,
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
        credential_ref="oauth-stale-graph-01",
        display_identity="first.outlook@contoso.example",
    )
    other = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id=_OTHER_EXTERNAL,
        credential_ref="oauth-other-graph-01",
        display_identity="other.outlook@contoso.example",
    )
    unit = InMemoryUnitOfWork(
        identities={(_MS_ISSUER, _MS_SUBJECT): user_id},
        connector_accounts={required.id: required, other.id: other},
    )
    client = MicrosoftFakeClient(
        _microsoft_authorization_result(display_identity=_DISPLAY)
    )
    service, unit, client, _store = _microsoft_service(unit=unit, client=client)
    service.start_connect_another(_microsoft_principal())
    result = service.complete_authorization(
        code=_MS_CODE,
        state=client.last_state,
        error=None,
    )
    assert result.connector_account_id == required.id
    assert len(unit.connector_account_store) == 2
    restored = unit.connector_account_store[required.id]
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.external_account_id == _EXTERNAL
    assert restored.credential_ref != "oauth-stale-graph-01"
    untouched = unit.connector_account_store[other.id]
    assert untouched.credential_ref == "oauth-other-graph-01"


def test_microsoft_connect_another_completion_logs_omit_identities_and_secrets(
    log_events: list[dict],
) -> None:
    client = MicrosoftFakeClient(_microsoft_authorization_result(display_identity=_DISPLAY))
    service, _unit, client, _store = _microsoft_service(client=client)
    service.start_connect_another(_microsoft_principal())
    service.complete_authorization(code=_MS_CODE, state=client.last_state, error=None)
    completed = [
        event
        for event in log_events
        if event.get("event") in {
            "microsoft_oauth_authorization_completed",
            "microsoft_oauth_authorization_started",
        }
    ]
    assert completed
    blob = repr(completed)
    assert _DISPLAY not in blob
    assert _EXTERNAL not in blob
    assert MSA_TENANT_ID not in blob
    assert _OID not in blob
    assert _MS_REFRESH not in blob
    assert _MS_CODE not in blob
    assert "external_account_id" not in blob
    assert "display_identity" not in blob
    assert "credential_ref" not in blob
    assert "refresh_token" not in blob
    assert "access_token" not in blob
    assert "id_token" not in blob


def test_microsoft_reauthorize_still_rejects_different_account() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id=_EXTERNAL,
        status=ConnectorAccountStatus.DISCONNECTED,
        credential_ref=None,
    )
    unit = InMemoryUnitOfWork(
        identities={(_MS_ISSUER, _MS_SUBJECT): user_id},
        connector_accounts={account.id: account},
    )
    client = MicrosoftFakeClient(
        _microsoft_authorization_result(
            external_account_id=_OTHER_EXTERNAL,
            object_id=_OTHER_OID,
        )
    )
    service, unit, client, store = _microsoft_service(unit=unit, client=client)
    service.start_reauthorization(_microsoft_principal(), account.id)
    with pytest.raises(MailboxOAuthIdentityMismatchError):
        service.complete_authorization(
            code=_MS_CODE,
            state=client.last_state,
            error=None,
        )
    restored = unit.connector_account_store[account.id]
    assert restored.status is ConnectorAccountStatus.DISCONNECTED
    assert restored.external_account_id == _EXTERNAL
    assert store._records == {}


def test_connect_another_cannot_bind_an_existing_connector() -> None:
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    sessions = MailboxAuthorizationSessionService(IdentityResolver(factory), factory)
    with pytest.raises(MailboxAuthorizationSessionInvalidError):
        sessions.start_authorization(
            _principal(),
            provider="gmail",
            purpose="connect_another",
            connector_account_id=uuid4(),
        )
