"""Offline ingestion boundary: fake connector through the existing analysis workflow."""

from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.communication_ingestion import CommunicationIngestionService
from app.domain.interfaces import ConnectorMessageQuery
from app.infrastructure.connectors.fake import FakeCommunicationConnector
from app.providers.mock.provider import MockAIProvider


def test_fake_connector_ingestion_uses_existing_workflow_without_persistence() -> None:
    """Fake connector → ingestion → real workflow → MockAIProvider, no database."""
    connector = FakeCommunicationConnector()
    listed = connector.list_messages(ConnectorMessageQuery(limit=1)).items[0]
    assert listed.message_id is not None
    workflow = CommunicationAnalysisWorkflowService(CommunicationAnalysisService(MockAIProvider()))
    service = CommunicationIngestionService(connector, workflow)

    outcome = service.analyze_message(listed.message_id)

    assert outcome.analysis_id is None
    assert outcome.result.provider == "mock"
    assert outcome.result.analysis.summary.text
    assert outcome.result.analysis.message_id == listed.message_id
