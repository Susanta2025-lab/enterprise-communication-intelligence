"""Dependency composition tests for the provider-neutral read connector factory."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, get_args, get_origin

import httpx
import pytest
from fastapi import HTTPException
from fastapi.params import Depends as DependsParam

from app.api.dependencies import (
    get_communication_action_executor_factory,
    get_communication_connector_factory,
    get_communication_credential_resolver,
    get_communication_http_client,
    get_mailbox_read_credential_resolver,
    get_mailbox_read_http_client,
    require_authenticated_communications_read,
    require_authenticated_communications_send,
    require_communications_send,
)
from app.core.security import (
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
    AuthenticatedPrincipal,
)
from app.domain.interfaces import (
    CommunicationActionExecutorFactory,
    CommunicationConnectorFactory,
    CommunicationCredentialResolver,
)
from app.infrastructure.connectors.factory import ProviderCommunicationConnectorFactory
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.infrastructure.executors.factory import ProviderCommunicationActionExecutorFactory
from tests.support.jwt_tokens import (
    TEST_ISSUER,
    TEST_SUBJECT,
    generate_test_rsa_private_key,
    make_test_validator,
)


def _principal(*permissions: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset(permissions),
    )


@pytest.fixture
def permission_validator():
    return make_test_validator(generate_test_rsa_private_key())



def _principal(*permissions: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset(permissions),
    )


class _CountingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(599, json={"error": "di must not call HTTP"})


def _depends_on(func: Callable[..., object], target: Callable[..., object]) -> bool:
    seen: set[object] = set()
    stack: list[Callable[..., object] | None] = [func]
    while stack:
        current = stack.pop()
        if current is None or current in seen:
            continue
        seen.add(current)
        if current is target:
            return True
        try:
            signature = inspect.signature(current)
        except (TypeError, ValueError):
            continue
        for parameter in signature.parameters.values():
            candidates: list[object] = [parameter.default]
            annotation = parameter.annotation
            if get_origin(annotation) is Annotated:
                candidates.extend(get_args(annotation)[1:])
            for candidate in candidates:
                if isinstance(candidate, DependsParam) and candidate.dependency is not None:
                    stack.append(candidate.dependency)
    return False


def test_read_factory_dependency_does_not_require_send() -> None:
    assert _depends_on(
        get_communication_connector_factory,
        require_authenticated_communications_read,
    )
    assert not _depends_on(
        get_communication_connector_factory,
        require_authenticated_communications_send,
    )
    assert _depends_on(
        get_mailbox_read_http_client,
        require_authenticated_communications_read,
    )
    assert not _depends_on(
        get_mailbox_read_http_client,
        require_authenticated_communications_send,
    )
    assert _depends_on(
        get_mailbox_read_credential_resolver,
        require_authenticated_communications_read,
    )
    assert not _depends_on(
        get_mailbox_read_credential_resolver,
        require_authenticated_communications_send,
    )


def test_send_factory_dependency_still_requires_send() -> None:
    assert _depends_on(
        get_communication_action_executor_factory,
        require_authenticated_communications_send,
    )
    assert not _depends_on(
        get_communication_action_executor_factory,
        require_authenticated_communications_read,
    )
    assert _depends_on(
        get_communication_http_client,
        require_authenticated_communications_send,
    )
    assert _depends_on(
        get_communication_credential_resolver,
        require_authenticated_communications_send,
    )


def test_read_and_send_resolvers_share_the_same_builder() -> None:
    read_resolver = get_mailbox_read_credential_resolver(
        _principal(COMMUNICATIONS_READ_PERMISSION),
    )
    send_resolver = get_communication_credential_resolver(
        _principal(COMMUNICATIONS_SEND_PERMISSION),
    )
    assert isinstance(read_resolver, CommunicationCredentialResolver)
    assert isinstance(send_resolver, CommunicationCredentialResolver)
    assert type(read_resolver) is type(send_resolver)
    assert isinstance(read_resolver, EnvironmentCommunicationCredentialResolver)


def test_read_factory_builds_without_token_or_provider_io() -> None:
    principal = _principal(COMMUNICATIONS_READ_PERMISSION)
    resolver = get_mailbox_read_credential_resolver(principal)
    transport = _CountingTransport()
    client = httpx.Client(transport=httpx.MockTransport(transport))
    try:
        factory = get_communication_connector_factory(principal, client, resolver)
        assert isinstance(factory, CommunicationConnectorFactory)
        assert isinstance(factory, ProviderCommunicationConnectorFactory)
        assert not isinstance(factory, CommunicationActionExecutorFactory)
        assert not isinstance(factory, ProviderCommunicationActionExecutorFactory)
        assert transport.calls == 0
    finally:
        client.close()
    assert transport.calls == 0


def test_read_authorization_does_not_grant_send_through_factory_dependencies(
    permission_validator,
) -> None:
    read_only = _principal(COMMUNICATIONS_READ_PERMISSION)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_send(read_only, permission_validator)
    assert exc_info.value.status_code == 403


def test_api_does_not_instantiate_vendor_connectors_in_dependencies() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "app" / "api" / "dependencies.py"
    ).read_text(encoding="utf-8")
    assert "GmailCommunicationConnector" not in source
    assert "MicrosoftGraphCommunicationConnector" not in source
    assert "GmailCommunicationActionExecutor" not in source
    assert "MicrosoftGraphCommunicationActionExecutor" not in source
    assert "get_communication_connector_factory" in source
    assert "ProviderCommunicationConnectorFactory" in source
    assert "get_mailbox_read_http_client" in source
    assert "get_mailbox_read_credential_resolver" in source


def test_mailbox_analyze_is_mounted_and_listing_is_not() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "api"
    router = (root / "router.py").read_text(encoding="utf-8")
    mailbox_routes = (root / "routes" / "mailbox_messages.py").read_text(encoding="utf-8")
    assert "mailbox_messages" in router
    assert "messages/analyze" in mailbox_routes
    assert '@router.get(' not in mailbox_routes
    assert "/messages\"" not in mailbox_routes.replace("/messages/analyze", "")
    for path in (root / "routes").glob("*.py"):
        if path.name == "mailbox_messages.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "/messages" not in source
        assert "messages/analyze" not in source
