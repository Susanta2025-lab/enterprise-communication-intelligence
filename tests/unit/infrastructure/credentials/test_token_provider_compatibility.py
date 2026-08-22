"""Read-adapter compatibility for the shared AccessTokenProvider contract."""

from __future__ import annotations

import httpx

from app.domain.interfaces import AccessTokenProvider
from app.infrastructure.connectors.common.auth import (
    AccessTokenProvider as ConnectorAccessTokenProvider,
)
from app.infrastructure.connectors.gmail import GmailCommunicationConnector
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from app.infrastructure.credentials import EnvironmentCommunicationCredentialResolver
from tests.unit.infrastructure.connectors.gmail.conftest import GmailHttpStub, gmail_resource
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GraphHttpStub,
    graph_resource,
)

_GMAIL_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_GMAIL_DEMO_ACCOUNT_ACCESS_TOKEN"
_GRAPH_ENV = "ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_GRAPH_DEMO_ACCOUNT_ACCESS_TOKEN"
_GMAIL_TOKEN = "fake-gmail-token"
_GRAPH_TOKEN = "fake-graph-token"


def test_domain_and_connector_access_token_provider_are_the_same_type() -> None:
    assert AccessTokenProvider is ConnectorAccessTokenProvider


def test_resolved_token_provider_is_usable_by_gmail_connector() -> None:
    stub = GmailHttpStub()
    stub.messages["msg-1"] = gmail_resource("msg-1")
    resolver = EnvironmentCommunicationCredentialResolver(
        environ={_GMAIL_ENV: _GMAIL_TOKEN},
    )
    token_provider = resolver.resolve(
        credential_ref="gmail-demo-account",
        provider="gmail",
    )
    client = httpx.Client(transport=httpx.MockTransport(stub))
    connector = GmailCommunicationConnector(
        http_client=client,
        access_token_provider=token_provider,
    )
    try:
        message = connector.fetch_message("msg-1")
    finally:
        client.close()

    assert message.message_id == "msg-1"
    assert stub.requests[0].headers.get("authorization") == f"Bearer {_GMAIL_TOKEN}"


def test_resolved_token_provider_is_usable_by_graph_connector() -> None:
    stub = GraphHttpStub()
    stub.messages["msg-1"] = graph_resource("msg-1")
    resolver = EnvironmentCommunicationCredentialResolver(
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    token_provider = resolver.resolve(
        credential_ref="graph-demo-account",
        provider="microsoft_graph",
    )
    client = httpx.Client(transport=httpx.MockTransport(stub))
    connector = MicrosoftGraphCommunicationConnector(
        http_client=client,
        access_token_provider=token_provider,
    )
    try:
        message = connector.fetch_message("msg-1")
    finally:
        client.close()

    assert message.message_id == "msg-1"
    assert stub.requests[0].headers.get("authorization") == f"Bearer {_GRAPH_TOKEN}"
