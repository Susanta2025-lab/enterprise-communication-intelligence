"""AWS Secrets Manager CommunicationCredentialStore.

Production identity is the default boto3 credential chain (ECS task role).
Application Settings do not store AWS access keys. Unit tests inject a client
and never create a live boto3 session.

Same-locator mutations are serialized with a PostgreSQL advisory lock. AWS
native version/stage compare-and-set remains in place as defense in depth.
PostgreSQL stores no OAuth secret material.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from app.core.exceptions import (
    CommunicationCredentialConflictError,
    CommunicationCredentialUnavailableError,
)
from app.core.logging import get_logger
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    CommunicationCredentialStore,
    NewCommunicationCredential,
)
from app.infrastructure.credentials.envelope import (
    deserialize_secret_envelope,
    new_logical_version,
    serialize_secret_envelope,
)
from app.infrastructure.credentials.mutation import CredentialMutationCoordinator
from app.infrastructure.credentials.secret_names import (
    DEFAULT_AWS_SECRET_NAMESPACE,
    aws_secret_id_for_locator,
    normalize_aws_secret_namespace,
)
from app.infrastructure.credentials.validation import (
    require_credential_ref,
    require_secret_material,
    require_supported_provider,
)

logger = get_logger(__name__)

MutationListener = Callable[[str], None]
_T = TypeVar("_T")


class _SecretsManagerClient(Protocol):
    def create_secret(self, **kwargs: Any) -> Any: ...

    def get_secret_value(self, **kwargs: Any) -> Any: ...

    def describe_secret(self, **kwargs: Any) -> Any: ...

    def put_secret_value(self, **kwargs: Any) -> Any: ...

    def update_secret_version_stage(self, **kwargs: Any) -> Any: ...

    def delete_secret(self, **kwargs: Any) -> Any: ...


class AwsSecretsManagerCommunicationCredentialStore(CommunicationCredentialStore):
    """Secrets Manager-backed store with PostgreSQL serialization plus native CAS.

    Replacement still writes ``AWSPENDING`` and moves ``AWSCURRENT`` only from
    the VersionId that was read. PostgreSQL advisory locks serialize ECI
    writers for the same locator so create / replace / delete cannot race each
    other across application instances that share the database.
    """

    BACKEND_NAME = "aws_secrets_manager"

    def __init__(
        self,
        region: str,
        *,
        namespace: str = DEFAULT_AWS_SECRET_NAMESPACE,
        client: _SecretsManagerClient | None = None,
        client_factory: Callable[[], _SecretsManagerClient] | None = None,
        mutation_coordinator: CredentialMutationCoordinator,
    ) -> None:
        resolved_region = region.strip()
        if not resolved_region:
            raise CommunicationCredentialUnavailableError()
        self._region = resolved_region
        self._namespace = normalize_aws_secret_namespace(namespace)
        self._client = client
        self._client_factory = client_factory
        self._mutation_coordinator = mutation_coordinator
        self._listeners: list[MutationListener] = []

    def __repr__(self) -> str:
        return "AwsSecretsManagerCommunicationCredentialStore()"

    def add_mutation_listener(self, listener: MutationListener) -> None:
        """Register a same-process callback invoked after create/replace/delete."""
        self._listeners.append(listener)

    def create(
        self,
        credential: NewCommunicationCredential,
    ) -> CommunicationCredentialRecord:
        locator = require_credential_ref(credential.credential_ref)
        provider = require_supported_provider(credential.provider)
        material = require_secret_material(credential.secret_material)
        secret_id = aws_secret_id_for_locator(locator, self._namespace)
        return self._run_locked(
            locator,
            "create",
            lambda: self._create_locked(locator, provider, material, secret_id),
        )

    def get(self, credential_ref: str) -> CommunicationCredentialRecord | None:
        locator = require_credential_ref(credential_ref)
        secret_id = aws_secret_id_for_locator(locator, self._namespace)
        fetched = self._get_current(secret_id)
        if fetched is None:
            return None
        _version_id, provider, version, material = fetched
        return CommunicationCredentialRecord(locator, provider, version, material)

    def replace_if_version(
        self,
        credential_ref: str,
        expected_version: str,
        secret_material: bytes,
    ) -> CommunicationCredentialRecord | None:
        locator = require_credential_ref(credential_ref)
        if not isinstance(expected_version, str) or not expected_version:
            raise CommunicationCredentialUnavailableError()
        material = require_secret_material(secret_material)
        secret_id = aws_secret_id_for_locator(locator, self._namespace)
        return self._run_locked(
            locator,
            "replace",
            lambda: self._replace_locked(locator, expected_version, material, secret_id),
        )

    def delete(self, credential_ref: str) -> None:
        locator = require_credential_ref(credential_ref)
        secret_id = aws_secret_id_for_locator(locator, self._namespace)
        self._run_locked(
            locator,
            "delete",
            lambda: self._delete_locked(locator, secret_id),
        )

    def _run_locked(
        self,
        locator: str,
        operation: str,
        action: Callable[[], _T],
    ) -> _T:
        try:
            with self._mutation_coordinator.lock(locator):
                return action()
        except CommunicationCredentialConflictError:
            raise
        except CommunicationCredentialUnavailableError:
            raise
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, locator=locator)
            raise CommunicationCredentialUnavailableError() from None

    def _create_locked(
        self,
        locator: str,
        provider: str,
        material: bytes,
        secret_id: str,
    ) -> CommunicationCredentialRecord:
        version = new_logical_version()
        envelope = serialize_secret_envelope(
            provider=provider,
            logical_version=version,
            secret_material=material,
        )
        try:
            self._sm().create_secret(
                Name=secret_id,
                SecretString=envelope,
                ClientRequestToken=str(uuid4()),
            )
        except ClientError as exc:
            if _aws_error_code(exc) in {"ResourceExistsException", "InvalidRequestException"}:
                logger.warning(
                    "credential_store_conflict",
                    backend=self.BACKEND_NAME,
                    operation="create",
                    locator=locator,
                    outcome="conflict",
                )
                raise CommunicationCredentialConflictError() from None
            self._raise_mapped(exc, operation="create", locator=locator)
        except Exception as exc:
            self._raise_mapped(exc, operation="create", locator=locator)
        record = CommunicationCredentialRecord(locator, provider, version, material)
        self._notify(locator)
        logger.info(
            "credential_store_created",
            backend=self.BACKEND_NAME,
            operation="create",
            locator=locator,
            outcome="created",
        )
        return record

    def _replace_locked(
        self,
        locator: str,
        expected_version: str,
        material: bytes,
        secret_id: str,
    ) -> CommunicationCredentialRecord | None:
        fetched = self._get_current(secret_id)
        if fetched is None or fetched[2] != expected_version:
            logger.info(
                "credential_store_cas_mismatch",
                backend=self.BACKEND_NAME,
                operation="replace",
                locator=locator,
                outcome="cas_mismatch",
            )
            return None
        current_version_id, provider, _logical, _material = fetched
        version = new_logical_version()
        envelope = serialize_secret_envelope(
            provider=provider,
            logical_version=version,
            secret_material=material,
        )
        pending_id = str(uuid4())
        try:
            self._sm().put_secret_value(
                SecretId=secret_id,
                ClientRequestToken=pending_id,
                SecretString=envelope,
                VersionStages=["AWSPENDING"],
            )
            self._sm().update_secret_version_stage(
                SecretId=secret_id,
                VersionStage="AWSCURRENT",
                MoveToVersionId=pending_id,
                RemoveFromVersionId=current_version_id,
            )
        except ClientError as exc:
            if _aws_error_code(exc) in {
                "InvalidRequestException",
                "ResourceNotFoundException",
                "PreconditionFailed",
            }:
                logger.info(
                    "credential_store_cas_mismatch",
                    backend=self.BACKEND_NAME,
                    operation="replace",
                    locator=locator,
                    outcome="cas_mismatch",
                )
                return None
            self._raise_mapped(exc, operation="replace", locator=locator)
        except Exception as exc:
            self._raise_mapped(exc, operation="replace", locator=locator)
        record = CommunicationCredentialRecord(locator, provider, version, material)
        self._notify(locator)
        logger.info(
            "credential_store_replaced",
            backend=self.BACKEND_NAME,
            operation="replace",
            locator=locator,
            outcome="replaced",
        )
        return record

    def _delete_locked(self, locator: str, secret_id: str) -> None:
        try:
            self._sm().delete_secret(
                SecretId=secret_id,
                RecoveryWindowInDays=7,
            )
        except ClientError as exc:
            if _aws_error_code(exc) == "ResourceNotFoundException":
                logger.info(
                    "credential_store_deleted",
                    backend=self.BACKEND_NAME,
                    operation="delete",
                    locator=locator,
                    outcome="not_found",
                )
                self._notify(locator)
                return
            if _aws_error_code(exc) == "InvalidRequestException":
                self._require_deleted_or_absent(
                    secret_id,
                    source_exc=exc,
                    operation="delete",
                    locator=locator,
                )
                logger.info(
                    "credential_store_deleted",
                    backend=self.BACKEND_NAME,
                    operation="delete",
                    locator=locator,
                    outcome="already_deleted",
                )
                self._notify(locator)
                return
            self._raise_mapped(exc, operation="delete", locator=locator)
        except Exception as exc:
            self._raise_mapped(exc, operation="delete", locator=locator)
        self._notify(locator)
        logger.info(
            "credential_store_deleted",
            backend=self.BACKEND_NAME,
            operation="delete",
            locator=locator,
            outcome="deleted",
        )

    def _sm(self) -> _SecretsManagerClient:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            try:
                self._client = self._client_factory()
            except Exception as exc:
                self._raise_mapped(exc, operation="client", locator=None)
            if self._client is None:
                raise CommunicationCredentialUnavailableError()
            return self._client
        try:
            self._client = boto3.client("secretsmanager", region_name=self._region)
        except Exception as exc:
            self._raise_mapped(exc, operation="client", locator=None)
        if self._client is None:
            raise CommunicationCredentialUnavailableError()
        return self._client

    def _get_current(
        self,
        secret_id: str,
    ) -> tuple[str, str, str, bytes] | None:
        try:
            response = self._sm().get_secret_value(SecretId=secret_id)
        except ClientError as exc:
            if _aws_error_code(exc) == "ResourceNotFoundException":
                return None
            if _aws_error_code(exc) == "InvalidRequestException":
                self._require_deleted_or_absent(
                    secret_id,
                    source_exc=exc,
                    operation="get",
                    locator=None,
                )
                return None
            self._raise_mapped(exc, operation="get", locator=None)
        except Exception as exc:
            self._raise_mapped(exc, operation="get", locator=None)
        version_id = response.get("VersionId")
        secret_string = response.get("SecretString")
        if not isinstance(version_id, str) or not version_id:
            logger.warning(
                "credential_store_malformed",
                backend=self.BACKEND_NAME,
                operation="get",
                outcome="malformed",
            )
            raise CommunicationCredentialUnavailableError()
        try:
            provider, logical_version, material = deserialize_secret_envelope(secret_string)
        except CommunicationCredentialUnavailableError:
            logger.warning(
                "credential_store_malformed",
                backend=self.BACKEND_NAME,
                operation="get",
                outcome="malformed",
            )
            raise
        return version_id, provider, logical_version, material

    def _require_deleted_or_absent(
        self,
        secret_id: str,
        *,
        source_exc: ClientError,
        operation: str,
        locator: str | None,
    ) -> None:
        """Confirm scheduled deletion or absence after InvalidRequestException.

        DescribeSecret is consulted only on this exceptional path. Presence of
        DeletedDate (or ResourceNotFoundException) means the ECI credential is
        already gone. Other InvalidRequestException states stay unavailable.
        Error-message text is not inspected.
        """
        response: object = None
        try:
            response = self._sm().describe_secret(SecretId=secret_id)
        except ClientError as exc:
            if _aws_error_code(exc) == "ResourceNotFoundException":
                return
            self._raise_mapped(exc, operation=operation, locator=locator)
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, locator=locator)
        if isinstance(response, dict) and response.get("DeletedDate") is not None:
            return
        self._raise_mapped(source_exc, operation=operation, locator=locator)

    def _raise_mapped(
        self,
        exc: Exception,
        *,
        operation: str,
        locator: str | None,
    ) -> None:
        logger.warning(
            "credential_store_unavailable",
            backend=self.BACKEND_NAME,
            operation=operation,
            locator=locator,
            outcome=_aws_outcome(exc),
        )
        raise CommunicationCredentialUnavailableError() from None

    def _notify(self, locator: str) -> None:
        for listener in list(self._listeners):
            try:
                listener(locator)
            except Exception:
                continue


def _aws_error_code(exc: ClientError) -> str:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return ""
    error = response.get("Error")
    if not isinstance(error, dict):
        return ""
    code = error.get("Code")
    return code if isinstance(code, str) else ""


def _aws_outcome(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        code = _aws_error_code(exc)
        if code in {"AccessDeniedException", "UnrecognizedClientException"}:
            return "permission_denied"
        if code == "ResourceNotFoundException":
            return "not_found"
        if code in {
            "ThrottlingException",
            "LimitExceededException",
            "InternalServiceError",
            "RequestTimeoutException",
        }:
            return "transient_failure"
        return "backend_unavailable"
    if isinstance(exc, EndpointConnectionError):
        return "transient_failure"
    if isinstance(exc, BotoCoreError):
        return "backend_unavailable"
    return "backend_unavailable"
