"""Provider-neutral coordination for durable cloud credential mutations.

PostgreSQL is used only as a distributed lock manager. Secret material never
enters this module, advisory-lock keys, or coordinator logs.
"""

from __future__ import annotations

import hashlib
import struct
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager

_LOCK_NAMESPACE = "eci:mailbox-credential-mutation:"
_DIGEST_SIZE = 8


def advisory_lock_keys(credential_ref: str) -> tuple[int, int]:
    """Return two signed int32 PostgreSQL advisory-lock keys for ``credential_ref``.

    Derivation is SHA-256 over a fixed ECI namespace plus the opaque locator.
    Python's process-randomized ``hash()`` is not used.
    """
    digest = hashlib.sha256(f"{_LOCK_NAMESPACE}{credential_ref}".encode()).digest()
    key1, key2 = struct.unpack(">ii", digest[:_DIGEST_SIZE])
    return key1, key2


class CredentialMutationCoordinator(ABC):
    """Serialize create / replace / delete for one opaque credential locator."""

    @abstractmethod
    def lock(self, credential_ref: str) -> AbstractContextManager[None]:
        """Hold exclusive mutation rights for ``credential_ref`` until exit.

        The context must release on success, exception, rollback, or connection
        loss. Implementations must not accept or persist secret material.
        """
