"""Server-generated opaque mailbox credential locators.

Locators are compatible with existing credential_ref validation. They are never
derived from user id, email, or provider account id. Public clients must not
supply them.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

from app.core.exceptions import (
    CommunicationCredentialConflictError,
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    CommunicationCredentialStore,
    NewCommunicationCredential,
)
from app.infrastructure.credentials.validation import (
    is_valid_credential_ref,
    require_secret_material,
    require_supported_provider,
)

LocatorGenerator = Callable[[], str]

_LOCATOR_PREFIX = "oauth-"
_LOCATOR_RANDOM_BYTES = 16
_MAX_CREATE_ATTEMPTS = 5


def generate_credential_locator() -> str:
    """Return a high-entropy locator matching credential_ref validation."""
    return f"{_LOCATOR_PREFIX}{secrets.token_hex(_LOCATOR_RANDOM_BYTES)}"


def is_oauth_credential_locator(credential_ref: object) -> bool:
    """Return True when ``credential_ref`` uses the server-generated OAuth prefix."""
    return (
        isinstance(credential_ref, str)
        and credential_ref.startswith(_LOCATOR_PREFIX)
        and is_valid_credential_ref(credential_ref)
    )


def create_communication_credential(
    store: CommunicationCredentialStore,
    *,
    provider: str,
    secret_material: bytes,
    generate_locator: LocatorGenerator = generate_credential_locator,
    max_attempts: int = _MAX_CREATE_ATTEMPTS,
) -> CommunicationCredentialRecord:
    """Persist credential material under a newly generated locator.

    On locator collision, generate a different locator and retry a bounded
    number of times. Existing records are never overwritten.
    """
    provider_slug = require_supported_provider(provider)
    material = require_secret_material(secret_material)
    if max_attempts < 1:
        raise CommunicationCredentialUnavailableError()

    for _ in range(max_attempts):
        locator = generate_locator()
        if not is_valid_credential_ref(locator):
            raise CommunicationCredentialUnavailableError()
        try:
            return store.create(
                NewCommunicationCredential(locator, provider_slug, material)
            )
        except CommunicationCredentialConflictError:
            continue
        except (
            CommunicationCredentialUnavailableError,
            UnsupportedCommunicationCredentialProviderError,
        ):
            raise
        except Exception:
            raise CommunicationCredentialUnavailableError() from None

    raise CommunicationCredentialUnavailableError()
