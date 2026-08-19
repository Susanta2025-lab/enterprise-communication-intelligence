"""Unit tests for CommunicationAnalysisWorkflowService."""

from uuid import UUID

import pytest

from app.application.exceptions import AnalysisFailedError
from app.application.services.analysis_history import AnalysisHistoryService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.communication_analysis_workflow import (
    CommunicationAnalysisWorkflowService,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.security import AuthenticatedPrincipal
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.providers.mock.provider import MockAIProvider
from tests.support.in_memory_persistence import InMemoryUnitOfWork, UnitOfWorkFactory
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION, TEST_SUBJECT
from tests.unit.application.conftest import RequestFactory
from tests.unit.application.test_communication_analysis_service import _RecordingProvider


class _FailingProvider(AIProvider):
    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        raise RuntimeError("provider unreachable")


class _SaveFailingHistory(AnalysisHistoryService):
    def __init__(self) -> None:
        self.save_calls = 0

    def save(self, user_id, request, result):  # noqa: ANN001
        self.save_calls += 1
        raise PersistenceError("Could not persist analysis.")


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )


def test_persistence_disabled_calls_ai_once_without_identity(
    make_request: RequestFactory,
) -> None:
    """Without persistence wiring, analyze stays AI-only."""
    request = make_request("Sharing the notes from today's standup for visibility.")
    recording = _RecordingProvider(MockAIProvider().analyze(request))
    workflow = CommunicationAnalysisWorkflowService(CommunicationAnalysisService(recording))

    outcome = workflow.analyze(request)

    assert outcome.analysis_id is None
    assert recording.calls == [request]


def test_persistence_disabled_with_principal_none_does_not_lookup(
    make_request: RequestFactory,
) -> None:
    """AUTH_MODE=disabled must not resolve identity or persist."""
    request = make_request("Sharing the notes from today's standup.")
    recording = _RecordingProvider(MockAIProvider().analyze(request))
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(recording),
        principal=None,
        identity_resolver=IdentityResolver(factory),
        history_service=AnalysisHistoryService(factory),
    )

    outcome = workflow.analyze(request)

    assert outcome.analysis_id is None
    assert recording.calls == [request]
    assert unit.identity_repository.create_calls == 0
    assert unit.analysis_repository.save_calls == 0


def test_persistence_enabled_resolves_identity_before_ai(
    make_request: RequestFactory,
) -> None:
    """Identity resolution must happen before the provider is invoked."""
    order: list[str] = []

    class _OrderedProvider(AIProvider):
        def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
            order.append("ai")
            return MockAIProvider().analyze(request)

    class _OrderedResolver(IdentityResolver):
        def resolve_or_create(self, principal: AuthenticatedPrincipal) -> UUID:
            order.append("identity")
            return super().resolve_or_create(principal)

    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(_OrderedProvider()),
        principal=_principal(),
        identity_resolver=_OrderedResolver(factory),
        history_service=AnalysisHistoryService(factory),
    )

    outcome = workflow.analyze(make_request("Sharing the notes from today's standup."))

    assert order == ["identity", "ai"]
    assert isinstance(outcome.analysis_id, UUID)
    assert unit.analysis_repository.save_calls == 1


def test_identity_failure_prevents_ai_and_raises_unavailable(
    make_request: RequestFactory,
) -> None:
    """A persistence outage before inference must not call the provider."""
    request = make_request("Sharing the notes from today's standup.")
    recording = _RecordingProvider(MockAIProvider().analyze(request))
    unit = InMemoryUnitOfWork(fail_on_enter=PersistenceError("Could not persist identity."))
    factory = UnitOfWorkFactory(unit)
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(recording),
        principal=_principal(),
        identity_resolver=IdentityResolver(factory),
        history_service=AnalysisHistoryService(factory),
    )

    with pytest.raises(ServiceUnavailableError):
        workflow.analyze(request)

    assert recording.calls == []


def test_unexpected_identity_error_prevents_ai_without_leaking_details(
    make_request: RequestFactory,
) -> None:
    """Unexpected identity failures must become 503-equivalent with zero AI calls."""
    request = make_request("Sharing the notes from today's standup.")
    recording = _RecordingProvider(MockAIProvider().analyze(request))
    sentinel = "password=supersecret host=db.internal"

    class _BrokenResolver:
        def resolve_or_create(self, principal: AuthenticatedPrincipal) -> UUID:
            raise RuntimeError(sentinel)

    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(recording),
        principal=_principal(),
        identity_resolver=_BrokenResolver(),  # type: ignore[arg-type]
        history_service=AnalysisHistoryService(UnitOfWorkFactory(InMemoryUnitOfWork())),
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        workflow.analyze(request)

    assert exc_info.value.message == "Persistence is currently unavailable."
    assert sentinel not in exc_info.value.message
    assert exc_info.value.__cause__ is None
    assert recording.calls == []


def test_ai_failure_does_not_save_analysis(make_request: RequestFactory) -> None:
    """Provider failures must not create an analysis row."""
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(_FailingProvider()),
        principal=_principal(),
        identity_resolver=IdentityResolver(factory),
        history_service=AnalysisHistoryService(factory),
    )

    with pytest.raises(AnalysisFailedError):
        workflow.analyze(make_request("Sharing the notes from today's standup."))

    assert unit.analysis_repository.save_calls == 0
    assert unit.identity_repository.create_calls == 1


def test_save_failure_after_ai_returns_result_without_id(
    make_request: RequestFactory,
) -> None:
    """A failed save must not retry the provider and must omit analysis_id."""
    request = make_request("Sharing the notes from today's standup.")
    recording = _RecordingProvider(MockAIProvider().analyze(request))
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    history = _SaveFailingHistory()
    workflow = CommunicationAnalysisWorkflowService(
        CommunicationAnalysisService(recording),
        principal=_principal(),
        identity_resolver=IdentityResolver(factory),
        history_service=history,
    )

    outcome = workflow.analyze(request)

    assert recording.calls == [request]
    assert outcome.analysis_id is None
    assert outcome.result.analysis.summary.text
    assert history.save_calls == 1
    assert unit.analysis_repository.save_calls == 0
