"""In-process CommunicationCredentialStore for tests and local OAuth foundation.

Records are not written to disk. Thread safety covers concurrent unit tests.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable

from app.core.exceptions import (
    CommunicationCredentialConflictError,
    CommunicationCredentialUnavailableError,
)
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    CommunicationCredentialStore,
    NewCommunicationCredential,
)
from app.infrastructure.credentials.validation import (
    require_credential_ref,
    require_secret_material,
    require_supported_provider,
)

MutationListener = Callable[[str], None]


class InMemoryCommunicationCredentialStore(CommunicationCredentialStore):
    """Thread-safe in-memory opaque credential store with compare-and-set replace."""

    BACKEND_NAME = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, CommunicationCredentialRecord] = {}
        self._listeners: list[MutationListener] = []

    def __repr__(self) -> str:
        return "InMemoryCommunicationCredentialStore()"

    def add_mutation_listener(self, listener: MutationListener) -> None:
        """Register a same-process callback invoked after create/replace/delete."""
        with self._lock:
            self._listeners.append(listener)

    def create(
        self,
        credential: NewCommunicationCredential,
    ) -> CommunicationCredentialRecord:
        locator = require_credential_ref(credential.credential_ref)
        provider = require_supported_provider(credential.provider)
        material = require_secret_material(credential.secret_material)
        record = CommunicationCredentialRecord(locator, provider, _new_version(), material)
        with self._lock:
            if locator in self._records:
                raise CommunicationCredentialConflictError()
            self._records[locator] = record
            listeners = list(self._listeners)
        _notify(listeners, locator)
        return record

    def get(self, credential_ref: str) -> CommunicationCredentialRecord | None:
        locator = require_credential_ref(credential_ref)
        with self._lock:
            return self._records.get(locator)

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
        with self._lock:
            current = self._records.get(locator)
            if current is None or current.version != expected_version:
                return None
            updated = CommunicationCredentialRecord(
                locator,
                current.provider,
                _new_version(),
                material,
            )
            self._records[locator] = updated
            listeners = list(self._listeners)
        _notify(listeners, locator)
        return updated

    def delete(self, credential_ref: str) -> None:
        locator = require_credential_ref(credential_ref)
        with self._lock:
            self._records.pop(locator, None)
            listeners = list(self._listeners)
        _notify(listeners, locator)


def _new_version() -> str:
    return secrets.token_hex(16)


def _notify(listeners: list[MutationListener], credential_ref: str) -> None:
    for listener in listeners:
        try:
            listener(credential_ref)
        except Exception:
            continue
