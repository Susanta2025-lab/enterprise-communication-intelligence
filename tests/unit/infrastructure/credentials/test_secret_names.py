"""Locator → cloud secret-name mapping tests."""

from __future__ import annotations

import pytest

from app.core.exceptions import CommunicationCredentialUnavailableError
from app.infrastructure.credentials.locators import generate_credential_locator
from app.infrastructure.credentials.secret_names import (
    DEFAULT_AWS_SECRET_NAMESPACE,
    aws_secret_id_for_locator,
    azure_secret_name_for_locator,
    normalize_aws_secret_namespace,
    require_oauth_locator,
)


def test_azure_name_is_derived_from_oauth_locator() -> None:
    locator = generate_credential_locator()
    name = azure_secret_name_for_locator(locator)
    assert name == f"eci-{locator}"
    assert name.startswith("eci-oauth-")
    assert "/" not in name
    assert locator not in ("",)


def test_aws_secret_id_stays_inside_namespace() -> None:
    locator = generate_credential_locator()
    secret_id = aws_secret_id_for_locator(locator, DEFAULT_AWS_SECRET_NAMESPACE)
    assert secret_id == f"{DEFAULT_AWS_SECRET_NAMESPACE}/{locator}"
    assert secret_id.startswith("eci/mailbox-oauth/oauth-")


def test_non_oauth_locator_is_rejected() -> None:
    with pytest.raises(CommunicationCredentialUnavailableError):
        require_oauth_locator("demo-account")
    with pytest.raises(CommunicationCredentialUnavailableError):
        azure_secret_name_for_locator("demo-account")
    with pytest.raises(CommunicationCredentialUnavailableError):
        aws_secret_id_for_locator("demo-account", DEFAULT_AWS_SECRET_NAMESPACE)


def test_namespace_normalization_rejects_traversal() -> None:
    assert normalize_aws_secret_namespace(" eci/mailbox-oauth/ ") == "eci/mailbox-oauth"
    with pytest.raises(ValueError):
        normalize_aws_secret_namespace("../etc")
    with pytest.raises(ValueError):
        normalize_aws_secret_namespace("eci//mailbox")
    with pytest.raises(ValueError):
        normalize_aws_secret_namespace("")
