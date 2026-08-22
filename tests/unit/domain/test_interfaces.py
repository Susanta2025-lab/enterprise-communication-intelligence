"""Unit tests for domain interfaces."""

from abc import ABC
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import PriorityLevel, SourceType, WorkflowActionType
from app.domain.interfaces import (
    AIProvider,
    AnalysisRepository,
    CommunicationActionExecution,
    CommunicationActionExecutor,
    CommunicationConnector,
    CommunicationCredentialResolver,
    ConnectorAccountRepository,
    IdentityRepository,
    PersistenceUnitOfWork,
    WorkflowActionRepository,
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
    assert issubclass(ConnectorAccountRepository, ABC)
    assert issubclass(WorkflowActionRepository, ABC)
    assert issubclass(PersistenceUnitOfWork, ABC)
    with pytest.raises(TypeError):
        IdentityRepository()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        AnalysisRepository()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        ConnectorAccountRepository()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        WorkflowActionRepository()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        PersistenceUnitOfWork()  # type: ignore[abstract]


def test_communication_connector_interface_is_abstract() -> None:
    """Connector ports must not be instantiable without implementations."""
    assert issubclass(CommunicationConnector, ABC)
    with pytest.raises(TypeError):
        CommunicationConnector()  # type: ignore[abstract]


def test_communication_action_executor_interface_is_abstract() -> None:
    """The write port must not be instantiable without an execute implementation."""
    assert issubclass(CommunicationActionExecutor, ABC)
    assert "execute" in CommunicationActionExecutor.__abstractmethods__
    with pytest.raises(TypeError):
        CommunicationActionExecutor()  # type: ignore[abstract]


def test_communication_credential_resolver_interface_is_abstract() -> None:
    """The credential port must not be instantiable without a resolve implementation."""
    assert issubclass(CommunicationCredentialResolver, ABC)
    assert "resolve" in CommunicationCredentialResolver.__abstractmethods__
    with pytest.raises(TypeError):
        CommunicationCredentialResolver()  # type: ignore[abstract]


def test_communication_action_execution_is_immutable_and_validated() -> None:
    """The executor command is a frozen approved-snapshot, not a workflow entity."""
    action_id = uuid4()
    connector_account_id = uuid4()
    command = CommunicationActionExecution(
        action_id=action_id,
        action_type=WorkflowActionType.REPLY,
        approved_reply_body="  Thanks, I will review the report and respond by Friday.  ",
        connector_account_id=connector_account_id,
        provider_message_id="provider-msg-001",
        provider="fake",
    )
    assert command.action_id == action_id
    assert command.action_type is WorkflowActionType.REPLY
    assert command.approved_reply_body == (
        "Thanks, I will review the report and respond by Friday."
    )
    assert command.connector_account_id == connector_account_id
    assert command.provider_message_id == "provider-msg-001"
    assert command.provider == "fake"
    assert set(CommunicationActionExecution.model_fields) == {
        "action_id",
        "action_type",
        "approved_reply_body",
        "connector_account_id",
        "provider_message_id",
        "provider",
    }
    assert "proposed_reply_body" not in CommunicationActionExecution.model_fields
    assert "analysis_id" not in CommunicationActionExecution.model_fields
    assert "owner_user_id" not in CommunicationActionExecution.model_fields
    assert "credential_ref" not in CommunicationActionExecution.model_fields
    with pytest.raises(ValidationError):
        command.action_id = uuid4()  # type: ignore[misc]
    with pytest.raises(ValidationError):
        command.action_type = WorkflowActionType.REPLY  # type: ignore[misc]
    with pytest.raises(ValidationError):
        command.approved_reply_body = "mutated"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        command.connector_account_id = uuid4()  # type: ignore[misc]
    with pytest.raises(ValidationError):
        command.provider_message_id = "mutated"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        command.provider = "gmail"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        CommunicationActionExecution(
            action_id=action_id,
            action_type=WorkflowActionType.REPLY,
            approved_reply_body="   ",
            connector_account_id=connector_account_id,
            provider_message_id="provider-msg-001",
            provider="fake",
        )
    with pytest.raises(ValidationError):
        CommunicationActionExecution.model_validate(
            {
                "action_id": action_id,
                "action_type": WorkflowActionType.REPLY,
                "approved_reply_body": "Thanks, I will review the report.",
                "connector_account_id": str(connector_account_id),
                "provider_message_id": "provider-msg-001",
                "provider": "fake",
                "proposed_reply_body": "ignored",
            }
        )


def test_domain_package_has_no_fastapi_dependency() -> None:
    """Domain modules must remain independent of FastAPI."""
    import app.domain.enums as enums
    import app.domain.exceptions as domain_exceptions
    import app.domain.interfaces.ai_provider as ai_provider
    import app.domain.interfaces.analysis_repository as analysis_repository
    import app.domain.interfaces.communication_action_executor as communication_action_executor
    import app.domain.interfaces.communication_connector as communication_connector
    import app.domain.interfaces.communication_credential_resolver as credential_resolver
    import app.domain.interfaces.connector_account_repository as connector_account_repository
    import app.domain.interfaces.identity_repository as identity_repository
    import app.domain.interfaces.persistence_unit_of_work as persistence_unit_of_work
    import app.domain.interfaces.workflow_action_repository as workflow_action_repository
    import app.domain.models.analysis as analysis_models
    import app.domain.models.message as message_models
    import app.domain.models.workflow as workflow_models
    import app.domain.schemas.analysis as analysis_schemas

    for module in (
        enums,
        domain_exceptions,
        ai_provider,
        analysis_repository,
        communication_action_executor,
        communication_connector,
        credential_resolver,
        connector_account_repository,
        identity_repository,
        persistence_unit_of_work,
        workflow_action_repository,
        analysis_models,
        message_models,
        workflow_models,
        analysis_schemas,
    ):
        module_globals = set(module.__dict__)
        assert "fastapi" not in module_globals
        assert "sqlalchemy" not in module_globals
        assert not any(name.startswith("fastapi") for name in module_globals)
        assert not any(name.startswith("sqlalchemy") for name in module_globals)
