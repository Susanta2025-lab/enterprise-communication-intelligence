"""Unit tests for ConnectorAccountService."""

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    ConnectorAccountInvalidRequestError,
    ConnectorAccountNotFoundError,
)
from app.application.services.connector_accounts import ConnectorAccountService
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from tests.support.in_memory_persistence import InMemoryUnitOfWork, UnitOfWorkFactory
from tests.support.jwt_tokens import TEST_PERMISSION

_ISSUER_A = "https://issuer-a.example.invalid/"
_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_A = "subject-a"
_SUBJECT_B = "subject-b"
_PROVIDER = "fake"
_ACCOUNT = "fake-account-001"
_CREDENTIAL_REF = "cred-ref-fake-001"


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
) -> tuple[ConnectorAccountService, tuple[InMemoryUnitOfWork, ...]]:
    factory = UnitOfWorkFactory(*units) if units else UnitOfWorkFactory()
    if units:
        stored = units
    else:
        stored = (factory._units[0],)
    identity = IdentityResolver(factory)
    store = InMemoryCommunicationCredentialStore()
    return ConnectorAccountService(identity, factory, credential_store=store), stored


def test_register_creates_identity_and_active_account() -> None:
    """First registration resolves the internal user and stores an active account."""
    service, units = _service()
    unit = units[0]

    result = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
    )

    assert result.provider == _PROVIDER
    assert result.external_account_id == _ACCOUNT
    assert result.status is ConnectorAccountStatus.ACTIVE
    assert "credential_ref" not in asdict(result)
    assert "user_id" not in asdict(result)
    stored = next(iter(unit.connector_account_store.values()))
    assert stored.user_id == unit.identities[(_ISSUER_A, _SUBJECT_A)]
    assert stored.credential_ref == _CREDENTIAL_REF
    assert unit.identity_repository.create_calls == 1


def test_register_without_credential_ref_stores_null() -> None:
    """Omitting the locator stores null internally and still omits it from results."""
    service, units = _service()
    unit = units[0]
    result = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
    )
    assert "credential_ref" not in asdict(result)
    assert next(iter(unit.connector_account_store.values())).credential_ref is None


def test_register_reuses_existing_active_account() -> None:
    """An existing active row is returned without creating a duplicate."""
    identities: dict[tuple[str, str], UUID] = {}
    store: dict[UUID, ConnectorAccountRecord] = {}
    unit = InMemoryUnitOfWork(identities=identities, connector_accounts=store)
    service, _units = _service(unit)

    created = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
    )
    reused = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref="cred-ref-fake-002",
    )

    assert reused.id == created.id
    assert next(iter(store.values())).credential_ref == _CREDENTIAL_REF
    assert unit.connector_accounts.create_calls == 1


def test_register_reactivates_disconnected_account() -> None:
    """A disconnected row is reused, reactivated, and receives the new locator."""
    service, units = _service()
    unit = units[0]
    created = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
    )

    disconnected = service.disconnect_owned(_principal(), created.id)
    assert disconnected.status is ConnectorAccountStatus.DISCONNECTED
    stored_disconnected = next(iter(unit.connector_account_store.values()))
    assert stored_disconnected.credential_ref is None
    assert stored_disconnected.granted_capabilities is None

    restored = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref="cred-ref-fake-002",
    )
    assert restored.id == created.id
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert next(iter(unit.connector_account_store.values())).credential_ref == (
        "cred-ref-fake-002"
    )


def test_register_reactivation_can_clear_credential_ref() -> None:
    """Supplying None on reconnect replaces the previous locator with null."""
    service, units = _service()
    unit = units[0]
    created = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
    )
    service.disconnect_owned(_principal(), created.id)
    restored = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=None,
    )
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert next(iter(unit.connector_account_store.values())).credential_ref is None


def test_disconnect_clears_known_granted_capabilities() -> None:
    """Disconnect must not leave grant metadata on an account without a credential."""
    user_id = uuid4()
    now = datetime.now(UTC)
    account_id = uuid4()
    store = {
        account_id: ConnectorAccountRecord(
            id=account_id,
            user_id=user_id,
            provider=_PROVIDER,
            external_account_id=_ACCOUNT,
            credential_ref=_CREDENTIAL_REF,
            status=ConnectorAccountStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            granted_capabilities=(
                CommunicationCapability.MAIL_READ,
                CommunicationCapability.MAIL_SEND,
            ),
        )
    }
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts=store,
    )
    service, _units = _service(unit)
    disconnected = service.disconnect_owned(_principal(), account_id)
    assert disconnected.status is ConnectorAccountStatus.DISCONNECTED
    assert disconnected.granted_capabilities is None
    assert store[account_id].credential_ref is None
    assert store[account_id].granted_capabilities is None


def test_register_reactivates_reauth_required_account() -> None:
    """REAUTH_REQUIRED can be reactivated onto ACTIVE for later OAuth reauthorization."""
    user_id = uuid4()
    now = datetime.now(UTC)
    account_id = uuid4()
    store = {
        account_id: ConnectorAccountRecord(
            id=account_id,
            user_id=user_id,
            provider=_PROVIDER,
            external_account_id=_ACCOUNT,
            credential_ref=None,
            status=ConnectorAccountStatus.REAUTH_REQUIRED,
            created_at=now,
            updated_at=now,
            granted_capabilities=None,
        )
    }
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        connector_accounts=store,
    )
    service, _units = _service(unit)
    restored = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref="cred-ref-fake-003",
    )
    assert restored.id == account_id
    assert restored.status is ConnectorAccountStatus.ACTIVE
    assert restored.granted_capabilities is None
    assert store[account_id].credential_ref == "cred-ref-fake-003"


def test_list_unseen_principal_is_empty_and_does_not_create_user() -> None:
    """Listing must not invent an identity mapping."""
    service, units = _service()
    unit = units[0]

    items = service.list_owned(_principal())

    assert items == []
    assert unit.identity_repository.create_calls == 0
    assert unit.identities == {}


def test_get_unseen_principal_is_not_found_and_does_not_create_user() -> None:
    """Get must not invent an identity mapping."""
    service, units = _service()
    unit = units[0]

    with pytest.raises(ConnectorAccountNotFoundError):
        service.get_owned(_principal(), uuid4())

    assert unit.identity_repository.create_calls == 0
    assert unit.identities == {}


def test_disconnect_unseen_principal_is_not_found_and_does_not_create_user() -> None:
    """Disconnect must not invent an identity mapping."""
    service, units = _service()
    unit = units[0]

    with pytest.raises(ConnectorAccountNotFoundError):
        service.disconnect_owned(_principal(), uuid4())

    assert unit.identity_repository.create_calls == 0
    assert unit.identities == {}


def test_ownership_isolation_between_principals() -> None:
    """User B cannot get, list, or disconnect user A's connector account."""
    identities: dict[tuple[str, str], UUID] = {}
    store: dict[UUID, ConnectorAccountRecord] = {}
    shared = InMemoryUnitOfWork(identities=identities, connector_accounts=store)
    service, _units = _service(shared)
    owner = _principal(issuer=_ISSUER_A, subject=_SUBJECT_A)
    other = _principal(issuer=_ISSUER_B, subject=_SUBJECT_B)

    created = service.register(
        owner,
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
    )
    service.register(
        other,
        provider=_PROVIDER,
        external_account_id="fake-account-002",
        credential_ref="cred-ref-fake-002",
    )

    owned = service.get_owned(owner, created.id)
    assert owned.id == created.id

    with pytest.raises(ConnectorAccountNotFoundError) as get_error:
        service.get_owned(other, created.id)
    with pytest.raises(ConnectorAccountNotFoundError) as disconnect_error:
        service.disconnect_owned(other, created.id)
    with pytest.raises(ConnectorAccountNotFoundError):
        service.get_owned(owner, uuid4())

    assert get_error.value.message == disconnect_error.value.message
    assert str(created.id) not in str(get_error.value)
    listed = service.list_owned(other)
    assert [item.id for item in listed] != [created.id]
    assert all(item.id != created.id for item in listed)
    assert created.id in store


def test_application_result_omits_credential_ref_and_user_id() -> None:
    """Management results must not expose locators or internal user ids."""
    service, _units = _service()
    result = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
    )
    payload = asdict(result)
    assert set(payload) == {
        "id",
        "provider",
        "external_account_id",
        "status",
        "granted_capabilities",
        "created_at",
        "updated_at",
    }
    assert payload["granted_capabilities"] is None
    assert _CREDENTIAL_REF not in str(payload.values())


def test_invalid_provider_is_rejected() -> None:
    """Provider must be a lowercase slug, not a URL or mailbox identifier."""
    service, units = _service()
    unit = units[0]
    with pytest.raises(ConnectorAccountInvalidRequestError):
        service.register(
            _principal(),
            provider="https://mail.example.invalid/",
            external_account_id=_ACCOUNT,
        )
    with pytest.raises(ConnectorAccountInvalidRequestError):
        service.register(
            _principal(),
            provider="Fake",
            external_account_id=_ACCOUNT,
        )
    with pytest.raises(ConnectorAccountInvalidRequestError):
        service.register(_principal(), provider="", external_account_id=_ACCOUNT)
    with pytest.raises(ConnectorAccountInvalidRequestError):
        service.register(_principal(), provider="  ", external_account_id=_ACCOUNT)
    with pytest.raises(ConnectorAccountInvalidRequestError):
        service.register(
            _principal(),
            provider=_PROVIDER,
            external_account_id="  ",
        )
    assert unit.identity_repository.create_calls == 0


def test_accepted_provider_slugs_are_stored_verbatim() -> None:
    """Stable lowercase slugs are stored as given and are not aliased."""
    service, units = _service()
    unit = units[0]
    gmail = service.register(
        _principal(),
        provider="gmail",
        external_account_id=_ACCOUNT,
    )
    graph = service.register(
        _principal(),
        provider="microsoft_graph",
        external_account_id=_ACCOUNT,
    )
    fake = service.register(
        _principal(),
        provider="fake",
        external_account_id=_ACCOUNT,
    )
    assert gmail.provider == "gmail"
    assert graph.provider == "microsoft_graph"
    assert fake.provider == "fake"
    assert {row.provider for row in unit.connector_account_store.values()} == {
        "gmail",
        "microsoft_graph",
        "fake",
    }


def test_concurrent_duplicate_rereads_the_winner() -> None:
    """A unique-violation race must resolve the committed winner."""
    winner_id = uuid4()
    user_id = uuid4()
    identities = {(_ISSUER_A, _SUBJECT_A): user_id}
    now = datetime.now(UTC)
    winner = ConnectorAccountRecord(
        id=winner_id,
        user_id=user_id,
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
        status=ConnectorAccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    class _ConflictThenLookup:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self) -> InMemoryUnitOfWork:
            self.calls += 1
            if self.calls == 1:
                return InMemoryUnitOfWork(identities=identities)
            if self.calls == 2:
                unit = InMemoryUnitOfWork(identities=identities)

                class _ConflictRepo:
                    def find_by_owner_provider_external_account(
                        self,
                        owner_id: UUID,
                        provider: str,
                        external_account_id: str,
                    ) -> ConnectorAccountRecord | None:
                        return None

                    def create(self, account: object) -> ConnectorAccountRecord:
                        raise PersistenceError("Connector account is already registered.")

                unit._connector_accounts = _ConflictRepo()  # type: ignore[assignment]
                return unit
            return InMemoryUnitOfWork(
                identities=identities,
                connector_accounts={winner_id: winner},
            )

    factory = _ConflictThenLookup()
    service = ConnectorAccountService(IdentityResolver(factory), factory)
    found = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
    )
    assert found.id == winner_id


def test_persistence_failure_is_unavailable_without_account_details() -> None:
    """Public errors must not include ids, locators, or driver text."""
    user_id = uuid4()
    identities = {(_ISSUER_A, _SUBJECT_A): user_id}

    class _IdentityOkThenFail:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self) -> InMemoryUnitOfWork:
            self.calls += 1
            if self.calls == 1:
                return InMemoryUnitOfWork(identities=identities)
            return InMemoryUnitOfWork(
                identities=identities,
                fail_on_enter=PersistenceError("Could not persist connector account."),
            )

    factory = _IdentityOkThenFail()
    service = ConnectorAccountService(IdentityResolver(factory), factory)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.list_owned(_principal())

    assert exc_info.value.message == "Persistence is currently unavailable."
    assert _ACCOUNT not in exc_info.value.message
    assert _CREDENTIAL_REF not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_list_pagination_defaults() -> None:
    """List uses Phase 9 history-style limit and newest-first ordering."""
    identities: dict[tuple[str, str], UUID] = {}
    store: dict[UUID, ConnectorAccountRecord] = {}
    unit = InMemoryUnitOfWork(identities=identities, connector_accounts=store)
    service, _units = _service(unit)
    first = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id=_ACCOUNT,
        credential_ref=_CREDENTIAL_REF,
    )
    second = service.register(
        _principal(),
        provider=_PROVIDER,
        external_account_id="fake-account-002",
        credential_ref=_CREDENTIAL_REF,
    )
    page = service.list_owned(_principal(), limit=1, offset=0)
    rest = service.list_owned(_principal(), limit=1, offset=1)
    assert [item.id for item in page] == [second.id]
    assert [item.id for item in rest] == [first.id]
