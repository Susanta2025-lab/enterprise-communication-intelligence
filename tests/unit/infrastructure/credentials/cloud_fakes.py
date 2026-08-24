"""In-memory fakes for Azure Key Vault and AWS Secrets Manager clients."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from azure.core.exceptions import ResourceNotFoundError
from botocore.exceptions import ClientError


def aws_client_error(
    code: str,
    operation: str = "GetSecretValue",
    message: str = "denied",
) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


class RecordingCredentialMutationCoordinator:
    """Test double that records lock acquisition without PostgreSQL."""

    def __init__(self) -> None:
        self.acquired: list[str] = []
        self.active: list[str] = []
        self.error: Exception | None = None

    @contextmanager
    def lock(self, credential_ref: str) -> Iterator[None]:
        if self.error is not None:
            raise self.error
        self.acquired.append(credential_ref)
        self.active.append(credential_ref)
        try:
            yield
        finally:
            self.active.pop()


class FakeAzureSecretClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_status: int | None = None
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []
        self._lock = threading.Lock()

    def get_secret(self, name: str) -> SimpleNamespace:
        with self._lock:
            self.get_calls.append(name)
            self._maybe_fail()
            if name not in self.values:
                raise ResourceNotFoundError("Secret not found.")
            return SimpleNamespace(name=name, value=self.values[name])

    def set_secret(self, name: str, value: str) -> SimpleNamespace:
        with self._lock:
            self.set_calls.append((name, value))
            self._maybe_fail()
            self.values[name] = value
            return SimpleNamespace(name=name, value=value)

    def begin_delete_secret(self, name: str) -> SimpleNamespace:
        with self._lock:
            self.delete_calls.append(name)
            self._maybe_fail()
            if name not in self.values:
                raise ResourceNotFoundError("Secret not found.")
            del self.values[name]
            return SimpleNamespace(result=lambda: None)

    def _maybe_fail(self) -> None:
        if self.fail_status is None:
            return
        from azure.core.exceptions import HttpResponseError

        error = HttpResponseError("cloud failure")
        error.status_code = self.fail_status
        raise error


class FakeSecretsManagerClient:
    def __init__(self) -> None:
        self.secrets: dict[str, dict[str, object]] = {}
        self.fail_code: str | None = None
        self.fail_operation: str | None = None
        self.error_message = "denied"
        self.force_get_invalid_request: set[str] = set()
        self.create_calls = 0
        self.get_calls = 0
        self.put_calls = 0
        self.stage_calls = 0
        self.describe_calls = 0
        self.delete_calls = 0
        self.describe_ids: list[str] = []
        self.last_delete_kwargs: dict[str, object] | None = None
        self._lock = threading.Lock()

    def create_secret(self, **kwargs: object) -> dict[str, str]:
        with self._lock:
            self._maybe_fail("CreateSecret")
            self.create_calls += 1
            name = str(kwargs["Name"])
            if name in self.secrets:
                raise aws_client_error("ResourceExistsException", "CreateSecret")
            version_id = str(kwargs.get("ClientRequestToken") or uuid4())
            self.secrets[name] = {
                "versions": {version_id: str(kwargs["SecretString"])},
                "stages": {"AWSCURRENT": version_id},
            }
            return {"Name": name, "VersionId": version_id}

    def get_secret_value(self, **kwargs: object) -> dict[str, str]:
        with self._lock:
            self.get_calls += 1
            self._maybe_fail("GetSecretValue")
            name = str(kwargs["SecretId"])
            if name in self.force_get_invalid_request:
                raise aws_client_error(
                    "InvalidRequestException",
                    "GetSecretValue",
                    message=self.error_message,
                )
            secret = self.secrets.get(name)
            if secret is None:
                raise aws_client_error("ResourceNotFoundException", "GetSecretValue")
            if secret.get("deleted_date") is not None:
                raise aws_client_error(
                    "InvalidRequestException",
                    "GetSecretValue",
                    message=self.error_message,
                )
            stages = secret["stages"]
            assert isinstance(stages, dict)
            version_id = stages.get("AWSCURRENT")
            if not isinstance(version_id, str):
                raise aws_client_error("ResourceNotFoundException", "GetSecretValue")
            versions = secret["versions"]
            assert isinstance(versions, dict)
            return {
                "Name": name,
                "VersionId": version_id,
                "SecretString": str(versions[version_id]),
            }

    def describe_secret(self, **kwargs: object) -> dict[str, object]:
        with self._lock:
            name = str(kwargs["SecretId"])
            self.describe_calls += 1
            self.describe_ids.append(name)
            self._maybe_fail("DescribeSecret")
            secret = self.secrets.get(name)
            if secret is None:
                raise aws_client_error("ResourceNotFoundException", "DescribeSecret")
            payload: dict[str, object] = {
                "ARN": f"arn:aws:secretsmanager:eu-west-1:123:secret:{name}",
                "Name": name,
            }
            deleted_date = secret.get("deleted_date")
            if deleted_date is not None:
                payload["DeletedDate"] = deleted_date
            return payload

    def put_secret_value(self, **kwargs: object) -> dict[str, object]:
        with self._lock:
            self._maybe_fail("PutSecretValue")
            self.put_calls += 1
            name = str(kwargs["SecretId"])
            secret = self.secrets.get(name)
            if secret is None:
                raise aws_client_error("ResourceNotFoundException", "PutSecretValue")
            version_id = str(kwargs.get("ClientRequestToken") or uuid4())
            stages = list(kwargs.get("VersionStages") or ["AWSCURRENT"])
            versions = secret["versions"]
            stage_map = secret["stages"]
            assert isinstance(versions, dict)
            assert isinstance(stage_map, dict)
            versions[version_id] = str(kwargs["SecretString"])
            for stage in stages:
                stage_map[str(stage)] = version_id
            return {"VersionId": version_id, "VersionStages": stages}

    def update_secret_version_stage(self, **kwargs: object) -> dict[str, str]:
        with self._lock:
            self._maybe_fail("UpdateSecretVersionStage")
            self.stage_calls += 1
            name = str(kwargs["SecretId"])
            secret = self.secrets[name]
            stage = str(kwargs["VersionStage"])
            move_to = str(kwargs["MoveToVersionId"])
            remove_from = kwargs.get("RemoveFromVersionId")
            stage_map = secret["stages"]
            assert isinstance(stage_map, dict)
            current = stage_map.get(stage)
            if remove_from is not None and current != remove_from:
                raise aws_client_error("InvalidRequestException", "UpdateSecretVersionStage")
            stage_map[stage] = move_to
            if stage == "AWSCURRENT" and stage_map.get("AWSPENDING") == move_to:
                del stage_map["AWSPENDING"]
            return {"ARN": f"arn:aws:secretsmanager:eu-west-1:123:secret:{name}"}

    def delete_secret(self, **kwargs: object) -> dict[str, str]:
        with self._lock:
            self.delete_calls += 1
            self.last_delete_kwargs = dict(kwargs)
            self._maybe_fail("DeleteSecret")
            if kwargs.get("ForceDeleteWithoutRecovery"):
                raise aws_client_error("InvalidRequestException", "DeleteSecret")
            name = str(kwargs["SecretId"])
            secret = self.secrets.get(name)
            if secret is None:
                raise aws_client_error("ResourceNotFoundException", "DeleteSecret")
            if secret.get("deleted_date") is not None:
                raise aws_client_error(
                    "InvalidRequestException",
                    "DeleteSecret",
                    message=self.error_message,
                )
            secret["deleted_date"] = datetime.now(UTC)
            return {"Name": name}

    def _maybe_fail(self, operation: str) -> None:
        if self.fail_code is None:
            return
        if self.fail_operation is not None and self.fail_operation != operation:
            return
        raise aws_client_error(self.fail_code, operation, message=self.error_message)
