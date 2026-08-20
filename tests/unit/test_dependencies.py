"""Unit tests for API dependency providers."""

import pytest
from fastapi import HTTPException

from app.api.dependencies import (
    get_ai_provider,
    get_communication_analysis_service,
    require_communications_analyze,
    require_communications_workflow,
    require_permission,
)
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.core.config import get_settings
from app.core.security import (
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticatedPrincipal,
)
from app.domain.interfaces import AIProvider
from app.providers.amazon_bedrock.provider import AmazonBedrockProvider
from app.providers.microsoft_foundry.provider import MicrosoftFoundryProvider
from app.providers.mock.provider import MockAIProvider
from tests.support.jwt_tokens import (
    TEST_ISSUER,
    TEST_PERMISSION,
    TEST_SUBJECT,
    generate_test_rsa_private_key,
    make_test_validator,
)

_FOUNDRY_ENDPOINT = (
    "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev"
)
_FOUNDRY_DEPLOYMENT = "eci-gpt-54-mini"
_BEDROCK_REGION = "eu-south-2"
_BEDROCK_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_get_ai_provider_returns_ai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dependency function should return an object implementing AIProvider."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()

    provider = get_ai_provider()

    assert isinstance(provider, AIProvider)
    assert isinstance(provider, MockAIProvider)


def test_get_ai_provider_uses_configured_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dependency resolution should honor AI_PROVIDER configuration."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()

    provider = get_ai_provider()
    assert provider.PROVIDER_NAME == "mock"


def test_get_ai_provider_rejects_unsupported_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported provider configuration should surface through the dependency."""
    from app.core.exceptions import ConfigurationError

    monkeypatch.setenv("AI_PROVIDER", "azure")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        get_ai_provider()


def test_get_communication_analysis_service_uses_resolved_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service dependency should be built from the configured provider."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()

    service = get_communication_analysis_service(get_ai_provider())

    assert isinstance(service, CommunicationAnalysisService)


def test_get_communication_analysis_service_rejects_unsupported_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported provider configuration must surface before service creation."""
    from app.core.exceptions import ConfigurationError

    monkeypatch.setenv("AI_PROVIDER", "aws")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        get_communication_analysis_service(get_ai_provider())


def test_get_ai_provider_selects_microsoft_foundry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_PROVIDER=microsoft_foundry should resolve MicrosoftFoundryProvider."""
    monkeypatch.setenv("AI_PROVIDER", "microsoft_foundry")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", _FOUNDRY_ENDPOINT)
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", _FOUNDRY_DEPLOYMENT)
    get_settings.cache_clear()

    provider = get_ai_provider()

    assert isinstance(provider, AIProvider)
    assert isinstance(provider, MicrosoftFoundryProvider)
    assert provider.PROVIDER_NAME == "microsoft_foundry"


def test_get_ai_provider_selects_amazon_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_PROVIDER=amazon_bedrock should resolve AmazonBedrockProvider."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.setenv("BEDROCK_REGION", _BEDROCK_REGION)
    monkeypatch.setenv("BEDROCK_MODEL_ID", _BEDROCK_MODEL_ID)
    get_settings.cache_clear()

    provider = get_ai_provider()

    assert isinstance(provider, AIProvider)
    assert isinstance(provider, AmazonBedrockProvider)
    assert provider.PROVIDER_NAME == "amazon_bedrock"
    assert provider._bedrock_runtime_client is None


def test_get_communication_analysis_service_accepts_amazon_bedrock_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service dependency should remain provider-independent for Bedrock."""
    monkeypatch.setenv("AI_PROVIDER", "amazon_bedrock")
    monkeypatch.setenv("BEDROCK_REGION", _BEDROCK_REGION)
    monkeypatch.setenv("BEDROCK_MODEL_ID", _BEDROCK_MODEL_ID)
    get_settings.cache_clear()

    service = get_communication_analysis_service(get_ai_provider())

    assert isinstance(service, CommunicationAnalysisService)


def _principal(*permissions: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset(permissions),
    )


@pytest.fixture
def permission_validator():
    return make_test_validator(generate_test_rsa_private_key())


def test_require_communications_analyze_accepts_analyze_permission(
    permission_validator,
) -> None:
    """Existing analysis authorization still requires communications:analyze."""
    principal = _principal(TEST_PERMISSION)
    result = require_communications_analyze(principal, permission_validator)
    assert result is principal


def test_analyze_only_principal_is_denied_workflow_permission(
    permission_validator,
) -> None:
    """communications:analyze does not satisfy communications:workflow."""
    principal = _principal(TEST_PERMISSION)
    require_communications_analyze(principal, permission_validator)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_workflow(principal, permission_validator)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized"


def test_workflow_only_principal_is_denied_analyze_permission(
    permission_validator,
) -> None:
    """communications:workflow does not satisfy communications:analyze."""
    principal = _principal(COMMUNICATIONS_WORKFLOW_PERMISSION)
    require_communications_workflow(principal, permission_validator)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_analyze(principal, permission_validator)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized"


def test_principal_with_both_permissions_passes_either_dependency(
    permission_validator,
) -> None:
    """A principal with both capabilities satisfies analyze and workflow checks."""
    principal = _principal(TEST_PERMISSION, COMMUNICATIONS_WORKFLOW_PERMISSION)
    assert require_communications_analyze(principal, permission_validator) is principal
    assert require_communications_workflow(principal, permission_validator) is principal
    workflow_dep = require_permission(COMMUNICATIONS_WORKFLOW_PERMISSION)
    assert workflow_dep(principal, permission_validator) is principal


def test_require_permission_skips_checks_when_auth_disabled() -> None:
    """AUTH_MODE=disabled returns None without requiring a permission."""
    workflow_dep = require_permission(COMMUNICATIONS_WORKFLOW_PERMISSION)
    assert require_communications_analyze(None, None) is None
    assert workflow_dep(None, None) is None


def test_require_permission_rejects_blank_permission() -> None:
    """A blank required permission is a programming error, not a grant."""
    with pytest.raises(ValueError, match="required_permission must not be empty"):
        require_permission("")
    with pytest.raises(ValueError, match="required_permission must not be empty"):
        require_permission("   ")
