"""Offline ingestion boundary: mocked Graph HTTP through the existing workflow."""

import httpx

from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.communication_ingestion import CommunicationIngestionService
from app.domain.enums import SourceType
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from app.providers.mock.provider import MockAIProvider
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GRAPH_TOKEN,
    GraphHttpStub,
    graph_resource,
)


def test_graph_connector_ingestion_uses_existing_workflow_without_persistence() -> None:
    """Mocked Graph REST → connector → ingestion → workflow → MockAIProvider."""
    stub = GraphHttpStub()
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        body="Please review the Q3 budget proposal before Friday.",
        subject="Q3 budget review",
    )

    with httpx.Client(transport=httpx.MockTransport(stub)) as client:
        connector = MicrosoftGraphCommunicationConnector(
            http_client=client,
            access_token_provider=lambda: GRAPH_TOKEN,
        )
        workflow = CommunicationAnalysisWorkflowService(
            CommunicationAnalysisService(MockAIProvider())
        )
        service = CommunicationIngestionService(connector, workflow)
        outcome = service.analyze_message("msg-1")

    assert outcome.analysis_id is None
    assert outcome.result.provider == "mock"
    assert outcome.result.analysis.summary.text
    assert outcome.result.analysis.message_id == "msg-1"
    assert stub.requests[0].url.host == "graph.microsoft.com"
    assert stub.requests[0].url.path.endswith("/msg-1")
    assert stub.requests[0].headers.get("prefer") == 'outlook.body-content-type="text"'
    assert len(stub.requests) == 1


def test_graph_normalized_message_is_email_source_type() -> None:
    stub = GraphHttpStub()
    stub.messages["msg-1"] = graph_resource("msg-1")

    with httpx.Client(transport=httpx.MockTransport(stub)) as client:
        connector = MicrosoftGraphCommunicationConnector(
            http_client=client,
            access_token_provider=lambda: GRAPH_TOKEN,
        )
        message = connector.fetch_message("msg-1")

    assert message.metadata.source_type is SourceType.EMAIL
    assert message.message_id == "msg-1"
    assert connector.provider == "microsoft_graph"
