"""Deterministic locator → cloud secret-name mapping.

API clients never supply Key Vault or Secrets Manager names. Names are derived
only from server-generated ``oauth-`` locators plus a constrained namespace.
"""

from __future__ import annotations

import re
from typing import Final

from app.core.exceptions import CommunicationCredentialUnavailableError
from app.infrastructure.credentials.locators import is_oauth_credential_locator
from app.infrastructure.credentials.validation import require_credential_ref

AZURE_SECRET_NAME_PREFIX: Final[str] = "eci-"
DEFAULT_AWS_SECRET_NAMESPACE: Final[str] = "eci/mailbox-oauth"
_AZURE_SECRET_NAME = re.compile(r"^[0-9a-zA-Z-]{1,127}$")
_AWS_NAMESPACE = re.compile(r"^[A-Za-z0-9/_+=.@-]{1,256}$")
_AWS_SECRET_ID = re.compile(r"^[A-Za-z0-9/_+=.@-]{1,512}$")


def require_oauth_locator(credential_ref: object) -> str:
    """Return a server-generated OAuth locator or raise generic unavailability."""
    locator = require_credential_ref(credential_ref)
    if not is_oauth_credential_locator(locator):
        raise CommunicationCredentialUnavailableError()
    return locator


def azure_secret_name_for_locator(credential_ref: object) -> str:
    """Derive a Key Vault secret name from an opaque OAuth locator.

    Key Vault names allow only alphanumerics and hyphens. The ``oauth-`` locator
    charset already matches; an ``eci-`` prefix namespaces ECI secrets.
    """
    locator = require_oauth_locator(credential_ref)
    name = f"{AZURE_SECRET_NAME_PREFIX}{locator}"
    if _AZURE_SECRET_NAME.fullmatch(name) is None:
        raise CommunicationCredentialUnavailableError()
    return name


def normalize_aws_secret_namespace(value: object) -> str:
    """Return a constrained ECI Secrets Manager namespace or raise ValueError."""
    if not isinstance(value, str):
        raise ValueError("AWS_SECRETS_MANAGER_NAMESPACE is invalid.")
    stripped = value.strip().strip("/")
    if (
        not stripped
        or ".." in stripped
        or "//" in stripped
        or _AWS_NAMESPACE.fullmatch(stripped) is None
    ):
        raise ValueError("AWS_SECRETS_MANAGER_NAMESPACE is invalid.")
    return stripped


def aws_secret_id_for_locator(credential_ref: object, namespace: str) -> str:
    """Derive a namespaced Secrets Manager secret id from an OAuth locator."""
    locator = require_oauth_locator(credential_ref)
    ns = normalize_aws_secret_namespace(namespace)
    secret_id = f"{ns}/{locator}"
    if _AWS_SECRET_ID.fullmatch(secret_id) is None:
        raise CommunicationCredentialUnavailableError()
    return secret_id
