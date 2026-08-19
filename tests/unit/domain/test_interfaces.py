"""Unit tests for domain interfaces."""

from abc import ABC

import pytest

from app.domain.enums import PriorityLevel, SourceType
from app.domain.interfaces import (
    AIProvider,
    AnalysisRepository,
    IdentityRepository,
    PersistenceUnitOfWork,
)
from app.domain.models import (
    CommunicationAnalysis,
    CommunicationMessage,
    MessageMetadata,
    Priority,
    Summary,
)
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest


class _StubAIProvider(AIProvider):
    """Minimal concrete provider used to validate the interface contract."""

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        return CommunicationAnalysisResult(
            analysis=CommunicationAnalysis(
                message_id=request.message.message_id,
                summary=Summary(text="Stub summary"),
                priority=Priority(level=PriorityLevel.LOW),
            ),
            provider="stub",
        )


def test_ai_provider_is_abstract() -> None:
    """AIProvider must not be instantiable without an analyze implementation."""
    assert issubclass(AIProvider, ABC)
    with pytest.raises(TypeError):
        AIProvider()  # type: ignore[abstract]


def test_ai_provider_contract_with_stub() -> None:
    """A concrete provider should accept domain requests and return domain results."""
    request = CommunicationRequest(
        message=CommunicationMessage(
            body="Status update for the rollout.",
            metadata=MessageMetadata(
                source_type=SourceType.SLACK,
                sender="ops-bot",
            ),
            message_id="msg-200",
        )
    )

    result = _StubAIProvider().analyze(request)

    assert isinstance(result, CommunicationAnalysisResult)
    assert result.provider == "stub"
    assert result.analysis.message_id == "msg-200"
    assert result.analysis.priority.level is PriorityLevel.LOW


def test_repository_interfaces_are_abstract() -> None:
    """Persistence ports must not be instantiable without implementations."""
    assert issubclass(IdentityRepository, ABC)
    assert issubclass(AnalysisRepository, ABC)
    assert issubclass(PersistenceUnitOfWork, ABC)
    with pytest.raises(TypeError):
        IdentityRepository()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        AnalysisRepository()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        PersistenceUnitOfWork()  # type: ignore[abstract]


def test_domain_package_has_no_fastapi_dependency() -> None:
    """Domain modules must remain independent of FastAPI."""
    import app.domain.enums as enums
    import app.domain.interfaces.ai_provider as ai_provider
    import app.domain.interfaces.analysis_repository as analysis_repository
    import app.domain.interfaces.identity_repository as identity_repository
    import app.domain.interfaces.persistence_unit_of_work as persistence_unit_of_work
    import app.domain.models.analysis as analysis_models
    import app.domain.models.message as message_models
    import app.domain.schemas.analysis as analysis_schemas

    for module in (
        enums,
        ai_provider,
        analysis_repository,
        identity_repository,
        persistence_unit_of_work,
        analysis_models,
        message_models,
        analysis_schemas,
    ):
        module_globals = set(module.__dict__)
        assert "fastapi" not in module_globals
        assert "sqlalchemy" not in module_globals
        assert not any(name.startswith("fastapi") for name in module_globals)
        assert not any(name.startswith("sqlalchemy") for name in module_globals)
