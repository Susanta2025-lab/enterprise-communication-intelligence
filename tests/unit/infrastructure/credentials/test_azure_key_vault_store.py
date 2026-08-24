"""Azure Key Vault CommunicationCredentialStore tests. No live Azure calls."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from azure.core.exceptions import HttpResponseError

from app.core.exceptions import (
    CommunicationCredentialConflictError,
    CommunicationCredentialUnavailableError,
)
from app.domain.interfaces.communication_credential_store import NewCommunicationCredential
from app.infrastructure.credentials.azure_key_vault import (
    AzureKeyVaultCommunicationCredentialStore,
)
from app.infrastructure.credentials.locators import generate_credential_locator
from app.infrastructure.credentials.secret_names import azure_secret_name_for_locator
from tests.unit.infrastructure.credentials.cloud_fakes import (
    FakeAzureSecretClient,
    RecordingCredentialMutationCoordinator,
)

_MATERIAL = b"opaque-azure-secret-AAA"
_MATERIAL_TWO = b"opaque-azure-secret-BBB"


def _store(
    client: FakeAzureSecretClient | None = None,
    coordinator: RecordingCredentialMutationCoordinator | None = None,
) -> tuple[
    AzureKeyVaultCommunicationCredentialStore,
    FakeAzureSecretClient,
    RecordingCredentialMutationCoordinator,
]:
    fake = client or FakeAzureSecretClient()
    coord = coordinator or RecordingCredentialMutationCoordinator()
    store = AzureKeyVaultCommunicationCredentialStore(
        "https://eci-dev.vault.azure.net",
        secret_client=fake,
        mutation_coordinator=coord,
    )
    return store, fake, coord


def test_create_get_replace_delete_round_trip() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    assert created.secret_material == _MATERIAL
    found = store.get(locator)
    assert found is not None
    assert found.version == created.version
    assert found.provider == "gmail"
    name = azure_secret_name_for_locator(locator)
    assert name in fake.values
    replaced = store.replace_if_version(locator, created.version, _MATERIAL_TWO)
    assert replaced is not None
    assert replaced.secret_material == _MATERIAL_TWO
    assert replaced.version != created.version
    stale = store.replace_if_version(locator, created.version, b"stale-loser")
    assert stale is None
    assert store.get(locator) is not None
    assert store.get(locator).secret_material == _MATERIAL_TWO
    store.delete(locator)
    assert store.get(locator) is None
    store.delete(locator)


def test_duplicate_create_does_not_overwrite() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    first = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    with pytest.raises(CommunicationCredentialConflictError):
        store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL_TWO))
    found = store.get(locator)
    assert found is not None
    assert found.secret_material == _MATERIAL
    assert found.version == first.version
    assert list(fake.values.values())[0].count("opaque-azure-secret-BBB") == 0


def test_unknown_locator_returns_none() -> None:
    store, _fake, _coord = _store()
    assert store.get(generate_credential_locator()) is None
    assert (
        store.replace_if_version(
            generate_credential_locator(),
            "missing-version",
            _MATERIAL_TWO,
        )
        is None
    )


def test_non_oauth_locator_does_not_touch_vault() -> None:
    store, fake, _coord = _store()
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.get("demo-account")
    assert fake.get_calls == []


def test_malformed_secret_is_unavailable_without_echo() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    fake.values[azure_secret_name_for_locator(locator)] = '{"secret":"LEAKED-REFRESH"}'
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        store.get(locator)
    blob = f"{exc_info.value}{exc_info.value!r}{exc_info.value.message}"
    assert "LEAKED-REFRESH" not in blob


def test_permission_and_transient_failures_are_unavailable() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    fake.fail_status = 403
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.get(locator)
    fake.fail_status = 429
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.get(locator)
    fake.fail_status = 503
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))


def test_injected_client_does_not_construct_azure_credential() -> None:
    fake = FakeAzureSecretClient()
    with patch("app.infrastructure.credentials.azure_key_vault.DefaultAzureCredential") as cred:
        store = AzureKeyVaultCommunicationCredentialStore(
            "https://eci-dev.vault.azure.net",
            secret_client=fake,
            mutation_coordinator=RecordingCredentialMutationCoordinator(),
        )
        locator = generate_credential_locator()
        store.create(NewCommunicationCredential(locator, "microsoft_graph", _MATERIAL))
        cred.assert_not_called()


def test_repr_omits_secret_material() -> None:
    store, _fake, _coord = _store()
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    blob = f"{store!r}{created!r}{store.get(locator)!r}"
    assert "opaque-azure-secret" not in blob


def test_http_error_without_live_network() -> None:
    error = HttpResponseError("denied")
    error.status_code = 401
    fake = FakeAzureSecretClient()

    def boom(_name: str) -> None:
        raise error

    fake.get_secret = boom  # type: ignore[method-assign]
    store = AzureKeyVaultCommunicationCredentialStore(
        "https://eci-dev.vault.azure.net",
        secret_client=fake,
        mutation_coordinator=RecordingCredentialMutationCoordinator(),
    )
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.get(generate_credential_locator())


class _LockAwareAzureClient(FakeAzureSecretClient):
    def __init__(self, coordinator: RecordingCredentialMutationCoordinator) -> None:
        super().__init__()
        self.coordinator = coordinator
        self.get_lock_held: list[bool] = []
        self.set_lock_held: list[bool] = []
        self.delete_lock_held: list[bool] = []

    def get_secret(self, name: str) -> object:
        self.get_lock_held.append(bool(self.coordinator.active))
        return super().get_secret(name)

    def set_secret(self, name: str, value: str) -> object:
        self.set_lock_held.append(bool(self.coordinator.active))
        return super().set_secret(name, value)

    def begin_delete_secret(self, name: str) -> object:
        self.delete_lock_held.append(bool(self.coordinator.active))
        return super().begin_delete_secret(name)


def test_create_acquires_coordinator_before_check_and_write() -> None:
    coordinator = RecordingCredentialMutationCoordinator()
    fake = _LockAwareAzureClient(coordinator)
    store, _client, coord = _store(client=fake, coordinator=coordinator)
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    assert coord.acquired == [locator]
    assert fake.get_lock_held == [True]
    assert fake.set_lock_held == [True]


def test_replace_acquires_coordinator_around_read_compare_write() -> None:
    coordinator = RecordingCredentialMutationCoordinator()
    fake = _LockAwareAzureClient(coordinator)
    store, _client, coord = _store(client=fake, coordinator=coordinator)
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    coord.acquired.clear()
    fake.get_lock_held.clear()
    fake.set_lock_held.clear()
    replaced = store.replace_if_version(locator, created.version, _MATERIAL_TWO)
    assert replaced is not None
    assert coord.acquired == [locator]
    assert fake.get_lock_held and all(fake.get_lock_held)
    assert fake.set_lock_held == [True]


def test_stale_azure_version_returns_none_without_write() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    winner = store.replace_if_version(locator, created.version, _MATERIAL_TWO)
    assert winner is not None
    writes_after_winner = len(fake.set_calls)
    stale = store.replace_if_version(locator, created.version, b"stale-loser")
    assert stale is None
    assert len(fake.set_calls) == writes_after_winner
    assert store.get(locator).secret_material == _MATERIAL_TWO


def test_delete_is_coordinated() -> None:
    coordinator = RecordingCredentialMutationCoordinator()
    fake = _LockAwareAzureClient(coordinator)
    store, _client, coord = _store(client=fake, coordinator=coordinator)
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    coord.acquired.clear()
    store.delete(locator)
    assert coord.acquired == [locator]
    assert fake.delete_lock_held == [True]


def test_get_does_not_require_mutation_lock() -> None:
    coordinator = RecordingCredentialMutationCoordinator()
    fake = _LockAwareAzureClient(coordinator)
    store, _client, coord = _store(client=fake, coordinator=coordinator)
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    coord.acquired.clear()
    fake.get_lock_held.clear()
    found = store.get(locator)
    assert found is not None
    assert coord.acquired == []
    assert fake.get_lock_held == [False]


def test_coordinator_failure_is_provider_neutral_unavailability() -> None:
    coordinator = RecordingCredentialMutationCoordinator()
    coordinator.error = RuntimeError("coordination failed")
    store, fake, _coord = _store(coordinator=coordinator)
    locator = generate_credential_locator()
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    blob = f"{exc_info.value}{exc_info.value.message}{exc_info.value!r}"
    assert "coordination failed" not in blob
    assert fake.set_calls == []


def test_coordinator_never_receives_secret_material() -> None:
    coordinator = RecordingCredentialMutationCoordinator()
    store, _fake, coord = _store(coordinator=coordinator)
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    store.replace_if_version(locator, created.version, _MATERIAL_TWO)
    store.delete(locator)
    blob = "".join(coord.acquired)
    assert "opaque-azure-secret" not in blob
    assert _MATERIAL.decode() not in blob
    assert _MATERIAL_TWO.decode() not in blob
    assert coord.acquired == [locator, locator, locator]
