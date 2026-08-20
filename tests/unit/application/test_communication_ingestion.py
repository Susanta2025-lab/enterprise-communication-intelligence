"""Unit tests for CommunicationIngestionService."""

import pytest

from app.application.exceptions import AnalysisFailedError
from app.application.services.communication_analysis_workflow import PersistedAnalysisOutcome
from app.application.services.communication_ingestion import CommunicationIngestionService
from app.core.exceptions import ConnectorMessageNotFoundError, ConnectorUnavailableError
from app.domain.enums import MessageCategory, PriorityLevel, SourceType
from app.domain.interfaces import CommunicationConnector, ConnectorMessageQuery, MessagePage
from app.domain.models import CommunicationAnalysis, CommunicationMessage, Priority, Summary
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from tests.unit.application.conftest import RequestFactory


class _RecordingConnector(CommunicationConnector):
    def __init__(self, message: CommunicationMessage) -> None:
        self.message = message
        self.fetch_ids: list[str] = []

    @property
    def provider(self) -> str:
        return "fake"

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        return MessagePage(items=[self.message], next_cursor=None)

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        self.fetch_ids.append(provider_message_id)
        return self.message


class _FailingConnector(CommunicationConnector):
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.fetch_ids: list[str] = []

    @property
    def provider(self) -> str:
        return "fake"

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        raise self.error

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        self.fetch_ids.append(provider_message_id)
        raise self.error


class _RecordingWorkflow:
    def __init__(self, outcome: PersistedAnalysisOutcome) -> None:
        self.outcome = outcome
        self.calls: list[CommunicationRequest] = []

    def analyze(self, request: CommunicationRequest) -> PersistedAnalysisOutcome:
        self.calls.append(request)
        return self.outcome


class _FailingWorkflow:
    def __init__(self) -> None:
        self.calls: list[CommunicationRequest] = []

    def analyze(self, request: CommunicationRequest) -> PersistedAnalysisOutcome:
        self.calls.append(request)
        raise AnalysisFailedError("AI provider failed to analyze the communication.")


def _outcome() -> PersistedAnalysisOutcome:
    result = CommunicationAnalysisResult(
        analysis=CommunicationAnalysis(
            summary=Summary(text="Summary: ingested"),
            priority=Priority(level=PriorityLevel.MEDIUM),
            category=MessageCategory.GENERAL,
        ),
        provider="mock",
    )
    return PersistedAnalysisOutcome(result=result, analysis_id=None)


def test_successful_fetch_calls_workflow_exactly_once(make_request: RequestFactory) -> None:
    """A fetched message is analyzed once through the injected workflow."""
    request = make_request("Please review the Q3 budget proposal before Friday.")
    connector = _RecordingConnector(request.message)
    workflow = _RecordingWorkflow(_outcome())
    service = CommunicationIngestionService(connector, workflow)  # type: ignore[arg-type]

    outcome = service.analyze_message("fake-msg-001")

    assert connector.fetch_ids == ["fake-msg-001"]
    assert len(workflow.calls) == 1
    assert outcome is workflow.outcome


def test_provider_message_id_is_passed_to_connector(make_request: RequestFactory) -> None:
    """The opaque provider id is forwarded unchanged to fetch_message."""
    request = make_request("Please review the Q3 budget proposal before Friday.")
    connector = _RecordingConnector(request.message)
    service = CommunicationIngestionService(connector, _RecordingWorkflow(_outcome()))  # type: ignore[arg-type]

    service.analyze_message("fake-msg-004")

    assert connector.fetch_ids == ["fake-msg-004"]


def test_normalized_message_becomes_communication_request(
    make_request: RequestFactory,
) -> None:
    """Connector output is wrapped as CommunicationRequest before analysis."""
    request = make_request("Please review the Q3 budget proposal before Friday.")
    connector = _RecordingConnector(request.message)
    workflow = _RecordingWorkflow(_outcome())
    service = CommunicationIngestionService(connector, workflow)  # type: ignore[arg-type]

    service.analyze_message("fake-msg-001")

    analyzed = workflow.calls[0]
    assert isinstance(analyzed, CommunicationRequest)
    assert analyzed.message == request.message
    assert analyzed.message.metadata.source_type is SourceType.EMAIL


def test_workflow_result_is_returned_unchanged(make_request: RequestFactory) -> None:
    """Ingestion must not rewrite the workflow outcome."""
    expected = _outcome()
    request = make_request("Please review the Q3 budget proposal before Friday.")
    service = CommunicationIngestionService(
        _RecordingConnector(request.message),
        _RecordingWorkflow(expected),  # type: ignore[arg-type]
    )

    assert service.analyze_message("fake-msg-001") is expected


def test_connector_failure_does_not_call_workflow() -> None:
    """Connector errors stop the use case before analysis."""
    workflow = _RecordingWorkflow(_outcome())
    connector = _FailingConnector(ConnectorMessageNotFoundError())
    service = CommunicationIngestionService(connector, workflow)  # type: ignore[arg-type]

    with pytest.raises(ConnectorMessageNotFoundError):
        service.analyze_message("missing-message")

    assert connector.fetch_ids == ["missing-message"]
    assert workflow.calls == []


def test_workflow_failure_fetches_only_once(make_request: RequestFactory) -> None:
    """A workflow failure must not retry the connector fetch."""
    request = make_request("Please review the Q3 budget proposal before Friday.")
    connector = _RecordingConnector(request.message)
    workflow = _FailingWorkflow()
    service = CommunicationIngestionService(connector, workflow)  # type: ignore[arg-type]

    with pytest.raises(AnalysisFailedError):
        service.analyze_message("fake-msg-001")

    assert connector.fetch_ids == ["fake-msg-001"]
    assert len(workflow.calls) == 1


def test_unavailable_connector_does_not_retry() -> None:
    """Transient connector failures are not retried by ingestion."""
    workflow = _RecordingWorkflow(_outcome())
    connector = _FailingConnector(ConnectorUnavailableError())
    service = CommunicationIngestionService(connector, workflow)  # type: ignore[arg-type]

    with pytest.raises(ConnectorUnavailableError):
        service.analyze_message("fake-msg-001")

    assert connector.fetch_ids == ["fake-msg-001"]
    assert workflow.calls == []


def test_ingestion_module_does_not_import_ai_or_persistence() -> None:
    """Ingestion must depend on the connector port and workflow, not AI or storage."""
    import app.application.services.communication_ingestion as ingestion

    names = set(ingestion.__dict__)
    assert "CommunicationConnector" in names
    assert "CommunicationAnalysisWorkflowService" in names
    assert "AIProvider" not in names
    assert "CommunicationAnalysisService" not in names
    assert "create_ai_provider" not in names
    assert "AnalysisHistoryService" not in names
    assert "fastapi" not in names
    assert "sqlalchemy" not in names


def test_fetch_telemetry_omits_content_and_cursor(
    make_request: RequestFactory,
    log_events: list[dict],
) -> None:
    """Connector fetch logs stay within the allowed telemetry fields."""
    request = make_request("Please review the Q3 budget proposal before Friday.")
    service = CommunicationIngestionService(
        _RecordingConnector(request.message),
        _RecordingWorkflow(_outcome()),  # type: ignore[arg-type]
    )

    service.analyze_message("fake-msg-001")

    started = [event for event in log_events if event["event"] == "connector_fetch_started"]
    completed = [event for event in log_events if event["event"] == "connector_fetch_completed"]
    assert started[-1]["provider"] == "fake"
    assert completed[-1]["provider"] == "fake"
    assert completed[-1]["result_count"] == 1
    assert isinstance(completed[-1]["duration_ms"], float)
    serialized = repr(completed[-1])
    assert request.message.body not in serialized
    assert (request.message.metadata.subject or "") not in serialized
    assert "fake-msg-001" not in serialized


def test_fetch_failure_telemetry_uses_error_class(
    log_events: list[dict],
) -> None:
    """Failed fetches log error_class and must not include str(exc)."""
    service = CommunicationIngestionService(
        _FailingConnector(ConnectorMessageNotFoundError()),
        _RecordingWorkflow(_outcome()),  # type: ignore[arg-type]
    )

    with pytest.raises(ConnectorMessageNotFoundError):
        service.analyze_message("missing-message")

    failed = [event for event in log_events if event["event"] == "connector_fetch_failed"]
    assert failed[-1]["error_class"] == "ConnectorMessageNotFoundError"
    assert failed[-1]["provider"] == "fake"
    assert "Connector message not found." not in repr(failed[-1])
