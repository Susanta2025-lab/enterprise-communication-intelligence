"""Privacy tests for cloud credential stores. Secret bytes must never be logged."""

from __future__ import annotations

from app.domain.interfaces.communication_credential_store import NewCommunicationCredential
from app.infrastructure.credentials.aws_secrets_manager import (
    AwsSecretsManagerCommunicationCredentialStore,
)
from app.infrastructure.credentials.azure_key_vault import (
    AzureKeyVaultCommunicationCredentialStore,
)
from app.infrastructure.credentials.locators import generate_credential_locator
from tests.unit.infrastructure.credentials.cloud_fakes import (
    FakeAzureSecretClient,
    FakeSecretsManagerClient,
    RecordingCredentialMutationCoordinator,
)

_MATERIAL = b"SUPER-SECRET-REFRESH-MATERIAL-XYZ"


def _blob(events: list[dict]) -> str:
    return " ".join(str(event) for event in events)


def test_azure_store_logs_omit_secret_material(log_events: list[dict]) -> None:
    store = AzureKeyVaultCommunicationCredentialStore(
        "https://eci-dev.vault.azure.net",
        secret_client=FakeAzureSecretClient(),
        mutation_coordinator=RecordingCredentialMutationCoordinator(),
    )
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    store.get(locator)
    store.replace_if_version(locator, created.version, _MATERIAL)
    store.delete(locator)
    blob = _blob(log_events)
    assert "SUPER-SECRET-REFRESH-MATERIAL-XYZ" not in blob
    assert _MATERIAL.decode() not in blob


def test_aws_store_logs_omit_secret_material(log_events: list[dict]) -> None:
    store = AwsSecretsManagerCommunicationCredentialStore(
        "eu-west-1",
        client=FakeSecretsManagerClient(),
        mutation_coordinator=RecordingCredentialMutationCoordinator(),
    )
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    store.get(locator)
    store.replace_if_version(locator, created.version, _MATERIAL)
    store.delete(locator)
    blob = _blob(log_events)
    assert "SUPER-SECRET-REFRESH-MATERIAL-XYZ" not in blob
