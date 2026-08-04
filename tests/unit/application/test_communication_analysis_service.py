"""Unit tests for CommunicationAnalysisService."""

import pytest
from pydantic import ValidationError

from app.application.exceptions import AnalysisFailedError
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.domain.enums import MessageCategory, PriorityLevel
from app.domain.interfaces import AIProvider
from app.domain.models import CommunicationAnalysis, Priority, Summary
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.providers.mock.provider import MockAIProvider
from tests.unit.application.conftest import RequestFactory


class _RecordingProvider(AIProvider):
    """Test double that records the request it was called with."""

    def __init__(self, result: CommunicationAnalysisResult) -> None:
        self.result = result
        self.calls: list[CommunicationRequest] = []

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        self.calls.append(request)
        return self.result


class _FailingProvider(AIProvider):
    """Test double that always raises to simulate provider failure."""

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        raise RuntimeError("provider unreachable")


def _sample_result() -> CommunicationAnalysisResult:
    return CommunicationAnalysisResult(
        analysis=CommunicationAnalysis(
            summary=Summary(text="Summary: test"),
            priority=Priority(level=PriorityLevel.MEDIUM),
            category=MessageCategory.GENERAL,
        ),
        provider="stub",
    )


def test_service_orchestrates_successful_analysis(make_request: RequestFactory) -> None:
    """The service should return the provider's result unchanged on success."""
    expected = _sample_result()
    provider = _RecordingProvider(expected)
    service = CommunicationAnalysisService(provider)
    request = make_request("Please review the report.")

    result = service.analyze(request)

    assert result == expected


def test_service_invokes_provider_with_the_given_request(
    make_request: RequestFactory,
) -> None:
    """The service must delegate exactly the received request to the provider."""
    provider = _RecordingProvider(_sample_result())
    service = CommunicationAnalysisService(provider)
    request = make_request("Please review the report.")

    service.analyze(request)

    assert provider.calls == [request]


def test_service_uses_constructor_injected_provider(make_request: RequestFactory) -> None:
    """Different injected providers should be used without changing the service."""
    request = make_request("Ordinary business update.")

    mock_provider = MockAIProvider()
    service_with_mock = CommunicationAnalysisService(mock_provider)
    result_from_mock = service_with_mock.analyze(request)
    assert result_from_mock.provider == "mock"

    stub_result = _sample_result()
    stub_provider = _RecordingProvider(stub_result)
    service_with_stub = CommunicationAnalysisService(stub_provider)
    result_from_stub = service_with_stub.analyze(request)
    assert result_from_stub == stub_result


def test_service_translates_provider_failures(make_request: RequestFactory) -> None:
    """Provider exceptions must be translated into AnalysisFailedError."""
    service = CommunicationAnalysisService(_FailingProvider())
    request = make_request("Please review the report.")

    with pytest.raises(AnalysisFailedError) as exc_info:
        service.analyze(request)

    assert "failed to analyze" in exc_info.value.message
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_invalid_request_is_rejected_before_reaching_the_service() -> None:
    """Invalid communication data must fail domain validation, not provider logic."""
    with pytest.raises(ValidationError):
        CommunicationRequest.model_validate(
            {
                "message": {
                    "body": "   ",
                    "metadata": {
                        "source_type": "email",
                        "sender": "alice@example.com",
                    },
                }
            }
        )


def test_service_is_deterministic_with_mock_provider(make_request: RequestFactory) -> None:
    """Identical requests through the service must produce identical results."""
    service = CommunicationAnalysisService(MockAIProvider())
    request = make_request("Please schedule a meeting before the deadline.")

    first = service.analyze(request)
    second = service.analyze(request)

    assert first == second


def test_service_remains_stateless_across_requests(make_request: RequestFactory) -> None:
    """The same service instance must not carry state between distinct requests."""
    service = CommunicationAnalysisService(MockAIProvider())

    urgent_result = service.analyze(make_request("This is urgent and needs ASAP attention."))
    normal_result = service.analyze(make_request("Just a routine status update."))

    assert urgent_result.analysis.priority.level is PriorityLevel.HIGH
    assert normal_result.analysis.priority.level is PriorityLevel.MEDIUM
