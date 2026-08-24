"""Azure Key Vault CommunicationCredentialStore.

Production identity is DefaultAzureCredential (Container Apps managed identity).
No Azure client secret is stored in application configuration. Unit tests inject
a SecretClient and never construct DefaultAzureCredential.

Azure Set Secret is not a linearizable compare-and-swap. Multi-instance
mutation safety comes from a PostgreSQL advisory lock keyed by the opaque
credential locator, covering the full read / compare / write critical section.
Key Vault remains the secret store. PostgreSQL stores no OAuth secret material.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

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
from app.infrastructure.credentials.secret_names import azure_secret_name_for_locator
from app.infrastructure.credentials.validation import (
    require_credential_ref,
    require_secret_material,
    require_supported_provider,
)

logger = get_logger(__name__)

MutationListener = Callable[[str], None]
_T = TypeVar("_T")


class _SecretClient(Protocol):
    def get_secret(self, name: str) -> Any: ...

    def set_secret(self, name: str, value: str) -> Any: ...

    def begin_delete_secret(self, name: str) -> Any: ...


class AzureKeyVaultCommunicationCredentialStore(CommunicationCredentialStore):
    """Key Vault-backed opaque credential store.

    Key Vault does not provide the required compare-and-set primitive. ECI
    serializes same-locator mutations with PostgreSQL advisory locks, then
    persists secret material in Key Vault. Concurrent ECI writers that share
    the coordinator therefore observe compare-and-set: at most one replace
    with a given expected version succeeds.
    """

    BACKEND_NAME = "azure_key_vault"

    def __init__(
        self,
        vault_url: str,
        *,
        secret_client: _SecretClient | None = None,
        credential_factory: Callable[[], Any] | None = None,
        mutation_coordinator: CredentialMutationCoordinator,
    ) -> None:
        url = vault_url.strip().rstrip("/")
        if not url:
            raise CommunicationCredentialUnavailableError()
        self._vault_url = url
        self._secret_client = secret_client
        self._credential_factory = credential_factory
        self._mutation_coordinator = mutation_coordinator
        self._listeners: list[MutationListener] = []

    def __repr__(self) -> str:
        return "AzureKeyVaultCommunicationCredentialStore()"

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
        name = azure_secret_name_for_locator(locator)
        return self._run_locked(
            locator,
            "create",
            lambda: self._create_locked(locator, provider, material, name),
        )

    def get(self, credential_ref: str) -> CommunicationCredentialRecord | None:
        locator = require_credential_ref(credential_ref)
        name = azure_secret_name_for_locator(locator)
        parsed = self._read_envelope(name)
        if parsed is None:
            return None
        provider, version, material = parsed
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
        name = azure_secret_name_for_locator(locator)
        return self._run_locked(
            locator,
            "replace",
            lambda: self._replace_locked(locator, expected_version, material, name),
        )

    def delete(self, credential_ref: str) -> None:
        locator = require_credential_ref(credential_ref)
        name = azure_secret_name_for_locator(locator)
        self._run_locked(locator, "delete", lambda: self._delete_locked(locator, name))

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
        except Exception as extra:
            self._raise_mapped(extra, operation=operation, locator=locator)
            raise CommunicationCredentialUnavailableError() from None

    def _create_locked(
        self,
        locator: str,
        provider: str,
        material: bytes,
        name: str,
    ) -> CommunicationCredentialRecord:
        if self._read_envelope(name) is not None:
            logger.warning(
                "credential_store_conflict",
                backend=self.BACKEND_NAME,
                operation="create",
                locator=locator,
                outcome="conflict",
            )
            raise CommunicationCredentialConflictError()
        version = new_logical_version()
        envelope = serialize_secret_envelope(
            provider=provider,
            logical_version=version,
            secret_material=material,
        )
        self._write_secret(name, envelope, operation="create", locator=locator)
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
        name: str,
    ) -> CommunicationCredentialRecord | None:
        parsed = self._read_envelope(name)
        if parsed is None or parsed[1] != expected_version:
            logger.info(
                "credential_store_cas_mismatch",
                backend=self.BACKEND_NAME,
                operation="replace",
                locator=locator,
                outcome="cas_mismatch",
            )
            return None
        provider = parsed[0]
        version = new_logical_version()
        envelope = serialize_secret_envelope(
            provider=provider,
            logical_version=version,
            secret_material=material,
        )
        self._write_secret(name, envelope, operation="replace", locator=locator)
        current = self._read_envelope(name)
        if current is None or current[1] != version:
            logger.info(
                "credential_store_cas_mismatch",
                backend=self.BACKEND_NAME,
                operation="replace",
                locator=locator,
                outcome="cas_mismatch",
            )
            return None
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

    def _delete_locked(self, locator: str, name: str) -> None:
        try:
            self._client().begin_delete_secret(name)
        except ResourceNotFoundError:
            logger.info(
                "credential_store_deleted",
                backend=self.BACKEND_NAME,
                operation="delete",
                locator=locator,
                outcome="not_found",
            )
            self._notify(locator)
            return
        except Exception as extra:
            self._raise_mapped(extra, operation="delete", locator=locator)
        self._notify(locator)
        logger.info(
            "credential_store_deleted",
            backend=self.BACKEND_NAME,
            operation="delete",
            locator=locator,
            outcome="deleted",
        )

    def _client(self) -> _SecretClient:
        if self._secret_client is not None:
            return self._secret_client
        factory = self._credential_factory or DefaultAzureCredential
        try:
            credential = factory()
            self._secret_client = SecretClient(
                vault_url=self._vault_url,
                credential=credential,
            )
        except Exception as extra:
            self._raise_mapped(extra, operation="client", locator=None)
        if self._secret_client is None:
            raise CommunicationCredentialUnavailableError()
        return self._secret_client

    def _read_envelope(self, name: str) -> tuple[str, str, bytes] | None:
        try:
            secret = self._client().get_secret(name)
        except ResourceNotFoundError:
            return None
        except Exception as extra:
            self._raise_mapped(extra, operation="get", locator=None)
        value = getattr(secret, "value", None)
        try:
            return deserialize_secret_envelope(value)
        except CommunicationCredentialUnavailableError:
            logger.warning(
                "credential_store_malformed",
                backend=self.BACKEND_NAME,
                operation="get",
                outcome="malformed",
            )
            raise

    def _write_secret(
        self,
        name: str,
        envelope: str,
        *,
        operation: str,
        locator: str,
    ) -> None:
        try:
            self._client().set_secret(name, envelope)
        except Exception as extra:
            self._raise_mapped(extra, operation=operation, locator=locator)

    def _raise_mapped(
        self,
        extra: Exception,
        *,
        operation: str,
        locator: str | None,
    ) -> None:
        logger.warning(
            "credential_store_unavailable",
            backend=self.BACKEND_NAME,
            operation=operation,
            locator=locator,
            outcome=_azure_outcome(extra),
            status_code=_http_status(extra),
        )
        raise CommunicationCredentialUnavailableError() from None

    def _notify(self, locator: str) -> None:
        for listener in list(self._listeners):
            try:
                listener(locator)
            except Exception:
                continue


def _http_status(extra: Exception) -> int | None:
    status = getattr(extra, "status_code", None)
    return status if isinstance(status, int) else None


def _azure_outcome(extra: Exception) -> str:
    if isinstance(extra, ClientAuthenticationError):
        return "permission_denied"
    if isinstance(extra, ResourceNotFoundError):
        return "not_found"
    if isinstance(extra, ServiceRequestError):
        return "transient_failure"
    status = _http_status(extra)
    if status in {401, 403}:
        return "permission_denied"
    if status == 404:
        return "not_found"
    if status in {408, 429, 500, 502, 503, 504}:
        return "transient_failure"
    if isinstance(extra, HttpResponseError):
        return "backend_unavailable"
    return "backend_unavailable"
