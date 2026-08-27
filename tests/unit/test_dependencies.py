"""Unit tests for API dependency providers."""

import inspect
from collections.abc import Callable
from typing import Annotated, get_args, get_origin

import pytest
from fastapi import HTTPException
from fastapi.params import Depends as DependsParam

from app.api.dependencies import (
    get_ai_provider,
    get_communication_analysis_service,
    get_connector_account_listing_service,
    get_connector_account_oauth_service,
    get_connector_account_service,
    get_workflow_action_service,
    require_authenticated_communications_connect,
    require_authenticated_communications_read,
    require_authenticated_communications_read_and_analyze,
    require_authenticated_communications_send,
    require_authenticated_communications_workflow,
    require_communications_analyze,
    require_communications_connect,
    require_communications_read,
    require_communications_read_and_analyze,
    require_communications_send,
    require_communications_workflow,
    require_permission,
    require_permissions,
    require_unit_of_work_factory,
)
from app.api.routes.connector_accounts import (
    disconnect_connector_account,
    list_owned_connector_accounts,
    reauthorize_connector_account,
)
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.connector_accounts import ConnectorAccountService
from app.application.services.identity import IdentityResolver
from app.application.services.workflow_actions import WorkflowActionService
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.security import (
    COMMUNICATIONS_CONNECT_PERMISSION,
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
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


def test_require_authenticated_communications_workflow_rejects_missing_principal() -> None:
    """AUTH_MODE=disabled must not pass None into WorkflowActionService."""
    with pytest.raises(HTTPException) as exc_info:
        require_authenticated_communications_workflow(None)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_require_authenticated_communications_workflow_returns_principal(
    permission_validator,
) -> None:
    """A workflow-authorized principal is passed through unchanged."""
    principal = _principal(COMMUNICATIONS_WORKFLOW_PERMISSION)
    authorized = require_communications_workflow(principal, permission_validator)
    assert require_authenticated_communications_workflow(authorized) is principal


def test_require_authenticated_communications_send_rejects_missing_principal() -> None:
    """AUTH_MODE=disabled must not pass None into execution."""
    with pytest.raises(HTTPException) as exc_info:
        require_authenticated_communications_send(None)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_require_authenticated_communications_send_returns_principal(
    permission_validator,
) -> None:
    """A send-authorized principal is passed through unchanged."""
    principal = _principal(COMMUNICATIONS_SEND_PERMISSION)
    authorized = require_communications_send(principal, permission_validator)
    assert require_authenticated_communications_send(authorized) is principal


def test_workflow_only_principal_is_denied_send_permission(
    permission_validator,
) -> None:
    """communications:workflow does not satisfy communications:send."""
    principal = _principal(COMMUNICATIONS_WORKFLOW_PERMISSION)
    require_communications_workflow(principal, permission_validator)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_send(principal, permission_validator)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized"


def test_send_only_principal_is_denied_workflow_permission(
    permission_validator,
) -> None:
    """communications:send does not satisfy communications:workflow."""
    principal = _principal(COMMUNICATIONS_SEND_PERMISSION)
    require_communications_send(principal, permission_validator)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_workflow(principal, permission_validator)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized"


def test_analyze_only_principal_is_denied_send_permission(
    permission_validator,
) -> None:
    """communications:analyze does not satisfy communications:send."""
    principal = _principal(TEST_PERMISSION)
    require_communications_analyze(principal, permission_validator)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_send(principal, permission_validator)
    assert exc_info.value.status_code == 403


def test_require_authenticated_communications_connect_rejects_missing_principal() -> None:
    """AUTH_MODE=disabled must not pass None into mailbox connect operations."""
    with pytest.raises(HTTPException) as exc_info:
        require_authenticated_communications_connect(None)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_require_authenticated_communications_connect_returns_principal(
    permission_validator,
) -> None:
    """A connect-authorized principal is passed through unchanged."""
    principal = _principal(COMMUNICATIONS_CONNECT_PERMISSION)
    authorized = require_communications_connect(principal, permission_validator)
    assert require_authenticated_communications_connect(authorized) is principal


def test_analyze_workflow_and_send_are_denied_connect_permission(
    permission_validator,
) -> None:
    """analyze, workflow, and send do not satisfy communications:connect."""
    for permission, dependency in (
        (TEST_PERMISSION, require_communications_analyze),
        (COMMUNICATIONS_WORKFLOW_PERMISSION, require_communications_workflow),
        (COMMUNICATIONS_SEND_PERMISSION, require_communications_send),
    ):
        principal = _principal(permission)
        dependency(principal, permission_validator)
        with pytest.raises(HTTPException) as exc_info:
            require_communications_connect(principal, permission_validator)
        assert exc_info.value.status_code == 403


def test_connect_only_principal_is_denied_other_permissions(
    permission_validator,
) -> None:
    """communications:connect does not satisfy analyze, workflow, or send."""
    principal = _principal(COMMUNICATIONS_CONNECT_PERMISSION)
    require_communications_connect(principal, permission_validator)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_analyze(principal, permission_validator)
    assert exc_info.value.status_code == 403
    with pytest.raises(HTTPException):
        require_communications_workflow(principal, permission_validator)
    with pytest.raises(HTTPException):
        require_communications_send(principal, permission_validator)


def test_require_communications_connect_skips_checks_when_auth_disabled() -> None:
    """AUTH_MODE=disabled returns None from the non-authenticated connect dependency."""
    assert require_communications_connect(None, None) is None


def test_get_workflow_action_service_uses_identity_resolver_and_uow_factory() -> None:
    """Workflow routes receive WorkflowActionService, not a repository or Session."""

    def _factory() -> object:
        raise AssertionError("factory should not be called during construction")

    resolver = IdentityResolver(_factory)
    service = get_workflow_action_service(resolver, _factory)
    assert isinstance(service, WorkflowActionService)


def test_require_permission_rejects_blank_permission() -> None:
    """A blank required permission is a programming error, not a grant."""
    with pytest.raises(ValueError, match="required_permission must not be empty"):
        require_permission("")
    with pytest.raises(ValueError, match="required_permission must not be empty"):
        require_permission("   ")
    with pytest.raises(ValueError, match="required_permissions must not be empty"):
        require_permissions()
    with pytest.raises(ValueError, match="required_permission must not be empty"):
        require_permissions(COMMUNICATIONS_READ_PERMISSION, "   ")


def test_read_only_principal_is_authorized_for_mailbox_listing(
    permission_validator,
) -> None:
    """communications:read alone authorizes the mailbox-list dependency."""
    principal = _principal(COMMUNICATIONS_READ_PERMISSION)
    authorized = require_communications_read(principal, permission_validator)
    assert require_authenticated_communications_read(authorized) is principal


@pytest.mark.parametrize(
    "permission",
    [
        TEST_PERMISSION,
        COMMUNICATIONS_CONNECT_PERMISSION,
        COMMUNICATIONS_WORKFLOW_PERMISSION,
        COMMUNICATIONS_SEND_PERMISSION,
    ],
)
def test_mailbox_listing_denies_principals_without_read(
    permission_validator,
    permission: str,
) -> None:
    """analyze, connect, workflow, and send do not satisfy communications:read."""
    principal = _principal(permission)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_read(principal, permission_validator)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized"


def test_mailbox_analyze_requires_read_and_analyze(
    permission_validator,
) -> None:
    """Mailbox-backed analyze is authorized only when both permissions are present."""
    principal = _principal(COMMUNICATIONS_READ_PERMISSION, TEST_PERMISSION)
    authorized = require_communications_read_and_analyze(principal, permission_validator)
    assert require_authenticated_communications_read_and_analyze(authorized) is principal


def test_mailbox_analyze_denies_read_only(
    permission_validator,
) -> None:
    """communications:read does not imply communications:analyze."""
    principal = _principal(COMMUNICATIONS_READ_PERMISSION)
    require_communications_read(principal, permission_validator)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_read_and_analyze(principal, permission_validator)
    assert exc_info.value.status_code == 403


def test_mailbox_analyze_denies_analyze_only(
    permission_validator,
) -> None:
    """communications:analyze does not imply communications:read."""
    principal = _principal(TEST_PERMISSION)
    require_communications_analyze(principal, permission_validator)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_read_and_analyze(principal, permission_validator)
    assert exc_info.value.status_code == 403


def test_mailbox_analyze_denies_read_and_connect_without_analyze(
    permission_validator,
) -> None:
    """Connect plus read still cannot invoke mailbox-backed AI analysis."""
    principal = _principal(COMMUNICATIONS_READ_PERMISSION, COMMUNICATIONS_CONNECT_PERMISSION)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_read_and_analyze(principal, permission_validator)
    assert exc_info.value.status_code == 403


def test_mailbox_analyze_denies_analyze_and_connect_without_read(
    permission_validator,
) -> None:
    """Connect plus analyze still cannot retrieve mailbox content."""
    principal = _principal(TEST_PERMISSION, COMMUNICATIONS_CONNECT_PERMISSION)
    with pytest.raises(HTTPException) as exc_info:
        require_communications_read_and_analyze(principal, permission_validator)
    assert exc_info.value.status_code == 403


def test_mailbox_analyze_accepts_read_analyze_and_unrelated_permissions(
    permission_validator,
) -> None:
    """Unrelated extra permissions do not disturb read+analyze authorization."""
    principal = _principal(
        COMMUNICATIONS_READ_PERMISSION,
        TEST_PERMISSION,
        COMMUNICATIONS_CONNECT_PERMISSION,
        COMMUNICATIONS_WORKFLOW_PERMISSION,
        COMMUNICATIONS_SEND_PERMISSION,
    )
    authorized = require_communications_read_and_analyze(principal, permission_validator)
    assert authorized is principal
    assert require_communications_analyze(principal, permission_validator) is principal
    assert require_communications_connect(principal, permission_validator) is principal
    assert require_communications_workflow(principal, permission_validator) is principal
    assert require_communications_send(principal, permission_validator) is principal


def test_direct_text_analyze_still_requires_only_analyze(
    permission_validator,
) -> None:
    """Direct-text analyze does not start requiring communications:read."""
    analyze_only = _principal(TEST_PERMISSION)
    assert require_communications_analyze(analyze_only, permission_validator) is analyze_only
    with pytest.raises(HTTPException) as exc_info:
        require_communications_read(analyze_only, permission_validator)
    assert exc_info.value.status_code == 403
    read_only = _principal(COMMUNICATIONS_READ_PERMISSION)
    with pytest.raises(HTTPException):
        require_communications_analyze(read_only, permission_validator)


def test_connect_send_and_workflow_remain_independent_of_read(
    permission_validator,
) -> None:
    """Connect, workflow, and send authorization is unchanged by communications:read."""
    connect_only = _principal(COMMUNICATIONS_CONNECT_PERMISSION)
    assert require_communications_connect(connect_only, permission_validator) is connect_only
    with pytest.raises(HTTPException):
        require_communications_read(connect_only, permission_validator)
    workflow_only = _principal(COMMUNICATIONS_WORKFLOW_PERMISSION)
    assert require_communications_workflow(workflow_only, permission_validator) is workflow_only
    with pytest.raises(HTTPException):
        require_communications_read(workflow_only, permission_validator)
    send_only = _principal(COMMUNICATIONS_SEND_PERMISSION)
    assert require_communications_send(send_only, permission_validator) is send_only
    with pytest.raises(HTTPException):
        require_communications_read(send_only, permission_validator)
    read_only = _principal(COMMUNICATIONS_READ_PERMISSION)
    with pytest.raises(HTTPException):
        require_communications_connect(read_only, permission_validator)
    with pytest.raises(HTTPException):
        require_communications_workflow(read_only, permission_validator)
    with pytest.raises(HTTPException):
        require_communications_send(read_only, permission_validator)


def test_mailbox_read_dependencies_reject_missing_principal() -> None:
    """Mailbox operations always require an authenticated ECI principal."""
    for dependency in (
        require_authenticated_communications_read,
        require_authenticated_communications_read_and_analyze,
    ):
        with pytest.raises(HTTPException) as exc_info:
            dependency(None)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Not authenticated"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_require_permissions_accepts_all_listed_permissions(
    permission_validator,
) -> None:
    """The generic multi-permission dependency requires every listed permission."""
    dependency = require_permissions(COMMUNICATIONS_READ_PERMISSION, TEST_PERMISSION)
    principal = _principal(COMMUNICATIONS_READ_PERMISSION, TEST_PERMISSION)
    assert dependency(principal, permission_validator) is principal
    with pytest.raises(HTTPException) as exc_info:
        dependency(_principal(COMMUNICATIONS_READ_PERMISSION), permission_validator)
    assert exc_info.value.status_code == 403


def test_communication_http_client_closes_after_generator_exit() -> None:
    """The request-scoped write client is closed when the yield dependency finishes."""
    from app.api.dependencies import get_communication_http_client

    principal = _principal(COMMUNICATIONS_SEND_PERMISSION)
    generator = get_communication_http_client(principal)
    client = next(generator)
    assert client.is_closed is False
    with pytest.raises(StopIteration):
        next(generator)
    assert client.is_closed is True


def test_mailbox_read_http_client_closes_after_generator_exit() -> None:
    """The request-scoped read client is closed when the yield dependency finishes."""
    from app.api.dependencies import get_mailbox_read_http_client

    principal = _principal(COMMUNICATIONS_READ_PERMISSION)
    generator = get_mailbox_read_http_client(principal)
    client = next(generator)
    assert client.is_closed is False
    with pytest.raises(StopIteration):
        next(generator)
    assert client.is_closed is True


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


def test_connector_account_list_depends_on_read_listing_service() -> None:
    """GET listing is communications:read plus persistence, not connect/store."""
    assert _depends_on(list_owned_connector_accounts, get_connector_account_listing_service)
    assert _depends_on(list_owned_connector_accounts, require_authenticated_communications_read)
    assert _depends_on(get_connector_account_listing_service, require_unit_of_work_factory)
    assert not _depends_on(list_owned_connector_accounts, get_connector_account_service)
    assert not _depends_on(
        list_owned_connector_accounts,
        require_authenticated_communications_connect,
    )
    assert not _depends_on(
        get_connector_account_listing_service,
        require_authenticated_communications_connect,
    )
    listing_source = inspect.getsource(get_connector_account_listing_service)
    assert "require_shared_oauth_store" not in listing_source
    assert "token_revoker" not in listing_source


def test_connector_account_lifecycle_still_requires_connect() -> None:
    """Disconnect and reauthorize remain communications:connect protected."""
    assert _depends_on(disconnect_connector_account, get_connector_account_service)
    assert _depends_on(
        disconnect_connector_account,
        require_authenticated_communications_connect,
    )
    assert not _depends_on(disconnect_connector_account, get_connector_account_listing_service)
    assert _depends_on(reauthorize_connector_account, get_connector_account_oauth_service)
    assert _depends_on(
        reauthorize_connector_account,
        require_authenticated_communications_connect,
    )
    assert _depends_on(
        get_connector_account_service,
        require_authenticated_communications_connect,
    )
    assert _depends_on(
        get_connector_account_oauth_service,
        require_authenticated_communications_connect,
    )


def test_get_connector_account_listing_service_is_persistence_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Listing construction does not touch the mailbox OAuth credential store."""

    def _forbidden_store(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("listing must not require the shared OAuth store")

    monkeypatch.setattr(
        "app.infrastructure.oauth.runtime.require_shared_oauth_store",
        _forbidden_store,
    )

    def _factory() -> object:
        raise AssertionError("unit of work should not open during construction")

    principal = _principal(COMMUNICATIONS_READ_PERMISSION)
    service = get_connector_account_listing_service(principal, _factory)
    assert isinstance(service, ConnectorAccountService)
    assert service._credential_store is None
    assert service._token_revokers == {}


def test_connector_account_lifecycle_builder_requires_oauth_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disconnect/reauthorize construction still requires the shared OAuth store."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    for name in (
        "GMAIL_OAUTH_CLIENT_ID",
        "GMAIL_OAUTH_CLIENT_SECRET",
        "GMAIL_OAUTH_REDIRECT_URI",
        "MICROSOFT_OAUTH_CLIENT_ID",
        "MICROSOFT_OAUTH_CLIENT_SECRET",
        "MICROSOFT_OAUTH_REDIRECT_URI",
        "MICROSOFT_OAUTH_TENANT",
        "CREDENTIAL_STORE_BACKEND",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    def _factory() -> object:
        raise AssertionError("unit of work should not open during construction")

    monkeypatch.setattr("app.api.dependencies.get_unit_of_work_factory", lambda: _factory)
    principal = _principal(COMMUNICATIONS_CONNECT_PERMISSION)
    with pytest.raises(ServiceUnavailableError):
        get_connector_account_service(principal)
    with pytest.raises(ServiceUnavailableError):
        get_connector_account_oauth_service(principal)
    listing = get_connector_account_listing_service(principal, _factory)
    assert listing._credential_store is None
    from app.api import dependencies as deps

    assert "require_shared_oauth_store" in inspect.getsource(deps._build_connector_account_service)
