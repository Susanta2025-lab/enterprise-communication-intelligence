"""AWS Secrets Manager CommunicationCredentialStore tests. No live AWS calls."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.exceptions import (
    CommunicationCredentialConflictError,
    CommunicationCredentialUnavailableError,
)
from app.domain.interfaces.communication_credential_store import NewCommunicationCredential
from app.infrastructure.credentials.aws_secrets_manager import (
    AwsSecretsManagerCommunicationCredentialStore,
)
from app.infrastructure.credentials.locators import generate_credential_locator
from app.infrastructure.credentials.secret_names import (
    DEFAULT_AWS_SECRET_NAMESPACE,
    aws_secret_id_for_locator,
)
from tests.unit.infrastructure.credentials.cloud_fakes import (
    FakeSecretsManagerClient,
    RecordingCredentialMutationCoordinator,
)

_MATERIAL = b"opaque-aws-secret-AAA"
_MATERIAL_TWO = b"opaque-aws-secret-BBB"


def _store(
    client: FakeSecretsManagerClient | None = None,
    coordinator: RecordingCredentialMutationCoordinator | None = None,
) -> tuple[
    AwsSecretsManagerCommunicationCredentialStore,
    FakeSecretsManagerClient,
    RecordingCredentialMutationCoordinator,
]:
    fake = client or FakeSecretsManagerClient()
    coord = coordinator or RecordingCredentialMutationCoordinator()
    store = AwsSecretsManagerCommunicationCredentialStore(
        "eu-west-1",
        client=fake,
        mutation_coordinator=coord,
    )
    return store, fake, coord


def test_create_get_replace_delete_round_trip() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "microsoft_graph", _MATERIAL))
    found = store.get(locator)
    assert found is not None
    assert found.secret_material == _MATERIAL
    assert found.provider == "microsoft_graph"
    assert fake.create_calls == 1
    replaced = store.replace_if_version(locator, created.version, _MATERIAL_TWO)
    assert replaced is not None
    assert replaced.secret_material == _MATERIAL_TWO
    assert fake.stage_calls == 1
    stale = store.replace_if_version(locator, created.version, b"stale-loser")
    assert stale is None
    assert store.get(locator).secret_material == _MATERIAL_TWO
    store.delete(locator)
    assert store.get(locator) is None
    store.delete(locator)


def test_cas_rejects_when_awscurrent_already_moved() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    winner = store.replace_if_version(locator, created.version, _MATERIAL_TWO)
    assert winner is not None
    lost = store.replace_if_version(locator, created.version, b"should-not-land")
    assert lost is None
    current = store.get(locator)
    assert current is not None
    assert current.secret_material == _MATERIAL_TWO
    assert b"should-not-land" not in str(fake.secrets).encode()


def test_duplicate_create_is_conflict() -> None:
    store, _fake, _coord = _store()
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    with pytest.raises(CommunicationCredentialConflictError):
        store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL_TWO))


def test_permission_throttling_and_malformed_are_unavailable() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    fake.fail_code = "AccessDeniedException"
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.get(locator)
    fake.fail_code = "ThrottlingException"
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.get(locator)
    fake.fail_code = None
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    secret_id = next(iter(fake.secrets))
    versions = fake.secrets[secret_id]["versions"]
    current = fake.secrets[secret_id]["stages"]["AWSCURRENT"]
    versions[current] = '{"secret":"LEAKED-AWS"}'
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        store.get(locator)
    assert "LEAKED-AWS" not in f"{exc_info.value}{exc_info.value.message}"


def test_non_oauth_locator_does_not_call_aws() -> None:
    store, fake, _coord = _store()
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.get("demo-account")
    assert fake.create_calls == 0
    assert fake.secrets == {}


def test_injected_client_does_not_construct_boto3_client() -> None:
    fake = FakeSecretsManagerClient()
    with patch("app.infrastructure.credentials.aws_secrets_manager.boto3.client") as client:
        store = AwsSecretsManagerCommunicationCredentialStore(
            "eu-west-1",
            client=fake,
            mutation_coordinator=RecordingCredentialMutationCoordinator(),
        )
        locator = generate_credential_locator()
        store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
        client.assert_not_called()


def test_repr_omits_secret_material() -> None:
    store, _fake, _coord = _store()
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    blob = f"{store!r}{created!r}"
    assert "opaque-aws-secret" not in blob


def test_aws_mutations_use_coordinator_and_native_cas() -> None:
    coordinator = RecordingCredentialMutationCoordinator()
    store, fake, coord = _store(coordinator=coordinator)
    locator = generate_credential_locator()
    created = store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    assert coord.acquired == [locator]
    coord.acquired.clear()
    replaced = store.replace_if_version(locator, created.version, _MATERIAL_TWO)
    assert replaced is not None
    assert coord.acquired == [locator]
    assert fake.put_calls == 1
    assert fake.stage_calls == 1
    coord.acquired.clear()
    found = store.get(locator)
    assert found is not None
    assert coord.acquired == []
    coord.acquired.clear()
    store.delete(locator)
    assert coord.acquired == [locator]


def test_aws_coordinator_failure_is_unavailable_without_write() -> None:
    coordinator = RecordingCredentialMutationCoordinator()
    coordinator.error = RuntimeError("lock failed")
    store, fake, _coord = _store(coordinator=coordinator)
    locator = generate_credential_locator()
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    assert fake.create_calls == 0
    assert fake.secrets == {}


def _secret_id(locator: str) -> str:
    return aws_secret_id_for_locator(locator, DEFAULT_AWS_SECRET_NAMESPACE)


def _blob(events: list[dict]) -> str:
    return " ".join(str(event) for event in events)


def test_get_resource_not_found_returns_none_without_describe() -> None:
    store, fake, coord = _store()
    locator = generate_credential_locator()
    assert store.get(locator) is None
    assert fake.get_calls == 1
    assert fake.describe_calls == 0
    assert coord.acquired == []


def test_successful_get_does_not_call_describe_secret() -> None:
    store, fake, coord = _store()
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    fake.get_calls = 0
    fake.describe_calls = 0
    coord.acquired.clear()
    found = store.get(locator)
    assert found is not None
    assert found.secret_material == _MATERIAL
    assert fake.get_calls == 1
    assert fake.describe_calls == 0
    assert coord.acquired == []


def test_get_invalid_request_with_deleted_date_returns_none() -> None:
    store, fake, coord = _store()
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    store.delete(locator)
    assert fake.last_delete_kwargs is not None
    assert fake.last_delete_kwargs.get("RecoveryWindowInDays") == 7
    assert "ForceDeleteWithoutRecovery" not in fake.last_delete_kwargs
    fake.get_calls = 0
    fake.describe_calls = 0
    fake.describe_ids.clear()
    coord.acquired.clear()
    assert store.get(locator) is None
    assert fake.get_calls == 1
    assert fake.describe_calls == 1
    assert fake.describe_ids == [_secret_id(locator)]
    assert coord.acquired == []


def test_get_invalid_request_without_deleted_date_is_unavailable(
    log_events: list[dict],
) -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    secret_id = _secret_id(locator)
    fake.force_get_invalid_request.add(secret_id)
    fake.error_message = "cannot use secret LEAKED-AWS-BODY opaque-aws-secret-AAA"
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        store.get(locator)
    blob = f"{exc_info.value}{exc_info.value.message} {_blob(log_events)}"
    assert "LEAKED-AWS-BODY" not in blob
    assert "opaque-aws-secret-AAA" not in blob
    assert _MATERIAL.decode() not in blob
    assert fake.describe_calls == 1
    assert fake.describe_ids == [secret_id]


def test_get_invalid_request_describe_not_found_returns_none() -> None:
    store, fake, coord = _store()
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    secret_id = _secret_id(locator)
    fake.force_get_invalid_request.add(secret_id)
    del fake.secrets[secret_id]
    coord.acquired.clear()
    assert store.get(locator) is None
    assert fake.describe_calls == 1
    assert coord.acquired == []


def test_describe_secret_failures_are_unavailable(log_events: list[dict]) -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    secret_id = _secret_id(locator)
    fake.force_get_invalid_request.add(secret_id)
    fake.error_message = "not authorized LEAKED-AWS-BODY"
    fake.fail_operation = "DescribeSecret"
    for code in (
        "AccessDeniedException",
        "UnrecognizedClientException",
        "ThrottlingException",
        "InternalServiceError",
    ):
        fake.fail_code = code
        with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
            store.get(locator)
        blob = f"{exc_info.value}{exc_info.value.message}"
        assert "LEAKED-AWS-BODY" not in blob
        assert _MATERIAL.decode() not in blob
    assert "LEAKED-AWS-BODY" not in _blob(log_events)
    assert _MATERIAL.decode() not in _blob(log_events)
    assert fake.describe_calls == 4


def test_delete_of_already_scheduled_secret_is_noop() -> None:
    store, fake, coord = _store()
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    store.delete(locator)
    assert fake.delete_calls == 1
    describe_after_first = fake.describe_calls
    coord.acquired.clear()
    store.delete(locator)
    assert fake.delete_calls == 2
    assert fake.describe_calls == describe_after_first + 1
    assert fake.describe_ids[-1] == _secret_id(locator)
    assert fake.last_delete_kwargs is not None
    assert fake.last_delete_kwargs.get("RecoveryWindowInDays") == 7
    assert "ForceDeleteWithoutRecovery" not in fake.last_delete_kwargs
    assert coord.acquired == [locator]
    assert store.get(locator) is None


def test_delete_invalid_request_without_deleted_date_is_unavailable() -> None:
    store, fake, _coord = _store()
    locator = generate_credential_locator()
    store.create(NewCommunicationCredential(locator, "gmail", _MATERIAL))
    fake.fail_code = "InvalidRequestException"
    fake.fail_operation = "DeleteSecret"
    with pytest.raises(CommunicationCredentialUnavailableError):
        store.delete(locator)
    assert fake.describe_calls == 1
    assert fake.secrets[_secret_id(locator)].get("deleted_date") is None
