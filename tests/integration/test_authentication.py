"""Integration tests for application-user authentication and authorization."""

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_ai_provider, get_token_validator
from app.core.config import get_settings
from app.core.security import COMMUNICATIONS_WORKFLOW_PERMISSION
from app.domain.interfaces import AIProvider
from app.main import create_app
from tests.support.jwt_tokens import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    TEST_JWKS_URL,
    TEST_PERMISSION,
    bearer_header,
    encode_test_token,
    generate_test_rsa_private_key,
    make_test_validator,
)

_ANALYZE_URL = "/api/v1/communications/analyze"
_SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "LOG_LEVEL",
    "API_V1_PREFIX",
    "AI_PROVIDER",
    "FOUNDRY_PROJECT_ENDPOINT",
    "FOUNDRY_MODEL_DEPLOYMENT",
    "BEDROCK_REGION",
    "BEDROCK_MODEL_ID",
    "AUTH_MODE",
    "OIDC_ISSUER",
    "OIDC_AUDIENCE",
    "OIDC_JWKS_URL",
    "OIDC_REQUIRED_PERMISSION",
    "DATABASE_URL",
)
_PRIVATE_TOKEN_SENTINEL = "ECI_PRIVATE_TOKEN_SENTINEL"
_PRIVATE_CLAIM_SENTINEL = "ECI_PRIVATE_CLAIM_SENTINEL"


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _valid_payload() -> dict:
    return {
        "message": {
            "body": "Sharing the notes from today's standup for visibility.",
            "message_id": "msg-001",
            "metadata": {
                "source_type": "email",
                "sender": "alice@example.com",
                "recipients": ["bob@example.com"],
                "subject": "Standup notes",
            },
        },
        "include_draft_reply": True,
        "include_action_items": True,
    }


def _enable_oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setenv("OIDC_REQUIRED_PERMISSION", TEST_PERMISSION)


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def oidc_client(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> Iterator[TestClient]:
    """TestClient with OIDC enabled and local RSA key resolution."""
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def oidc_client_with_logs(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    log_events: list[dict],
) -> Iterator[TestClient]:
    """OIDC TestClient with captured structured logs."""
    del log_events
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    with TestClient(application) as test_client:
        yield test_client


def _authorized_token(private_key, extra_claims: dict | None = None) -> str:
    claims = {"scp": TEST_PERMISSION}
    if extra_claims:
        claims.update(extra_claims)
    return encode_test_token(private_key, extra_claims=claims)


def test_health_endpoints_remain_public_with_oidc_enabled(
    oidc_client: TestClient,
) -> None:
    """Health and readiness must not require a bearer token."""
    assert oidc_client.get("/health").status_code == 200
    assert oidc_client.get("/api/v1/health").status_code == 200
    assert oidc_client.get("/api/v1/readiness").status_code == 200
    assert oidc_client.get("/health").json() == {"status": "healthy"}
    assert oidc_client.get("/api/v1/readiness").json() == {"status": "ready"}


def test_analyze_without_token_returns_401(oidc_client: TestClient) -> None:
    """Missing bearer token must be rejected before analysis."""
    response = oidc_client.post(_ANALYZE_URL, json=_valid_payload())
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers.get("www-authenticate") == "Bearer"


def test_analyze_with_invalid_token_returns_401(
    oidc_client: TestClient,
) -> None:
    """Malformed tokens must return 401."""
    response = oidc_client.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header("not-a-jwt"),
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers.get("www-authenticate") == "Bearer"


def test_analyze_with_valid_token_lacking_permission_returns_403(
    oidc_client: TestClient,
    private_key,
) -> None:
    """Authenticated callers without communications:analyze must receive 403."""
    token = encode_test_token(private_key, extra_claims={"scp": "other:permission"})
    response = oidc_client.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(token),
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}
    assert "www-authenticate" not in {key.lower() for key in response.headers}


def test_analyze_with_authorized_token_returns_existing_analysis(
    oidc_client: TestClient,
    private_key,
) -> None:
    """A valid authorized token must preserve existing mock analysis behavior."""
    response = oidc_client.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(_authorized_token(private_key)),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "mock"
    assert payload["analysis"]["priority"]["level"] == "medium"
    assert payload["analysis"]["category"] == "general"
    assert payload["analysis"]["message_id"] == "msg-001"
    assert "analysis_id" not in payload


def test_analyze_with_workflow_permission_only_returns_403(
    oidc_client: TestClient,
    private_key,
) -> None:
    """communications:workflow must not authorize the analyze endpoint."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": COMMUNICATIONS_WORKFLOW_PERMISSION},
    )
    response = oidc_client.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(token),
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}


def test_analyze_with_analyze_and_workflow_permissions_returns_200(
    oidc_client: TestClient,
    private_key,
) -> None:
    """A token holding both permissions still authorizes analysis."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": f"{TEST_PERMISSION} {COMMUNICATIONS_WORKFLOW_PERMISSION}"},
    )
    response = oidc_client.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(token),
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_unauthorized_requests_do_not_invoke_provider(
    oidc_client: TestClient,
    private_key,
) -> None:
    """401 and 403 responses must never call the AI provider."""
    provider = MagicMock(spec=AIProvider)
    oidc_client.app.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        missing = oidc_client.post(_ANALYZE_URL, json=_valid_payload())
        invalid = oidc_client.post(
            _ANALYZE_URL,
            json=_valid_payload(),
            headers=bearer_header("not-a-jwt"),
        )
        forbidden = oidc_client.post(
            _ANALYZE_URL,
            json=_valid_payload(),
            headers=bearer_header(encode_test_token(private_key)),
        )
    finally:
        oidc_client.app.dependency_overrides.pop(get_ai_provider, None)

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert forbidden.status_code == 403
    provider.analyze.assert_not_called()


def test_request_id_is_present_on_auth_responses(
    oidc_client_with_logs: TestClient,
    private_key,
    log_events: list[dict],
) -> None:
    """401, 403, and authorized 200 responses must include X-Request-ID."""
    unauthorized = oidc_client_with_logs.post(_ANALYZE_URL, json=_valid_payload())
    forbidden = oidc_client_with_logs.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(encode_test_token(private_key)),
    )
    authorized = oidc_client_with_logs.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(_authorized_token(private_key)),
    )

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 403
    assert authorized.status_code == 200

    for response in (unauthorized, forbidden, authorized):
        request_id = response.headers["x-request-id"]
        assert request_id
        matching = [
            event
            for event in log_events
            if event.get("event") == "http_request_completed"
            and event.get("request_id") == request_id
        ]
        assert matching

    auth_failed = [
        event for event in log_events if event.get("event") == "authentication_failed"
    ]
    authz_failed = [
        event for event in log_events if event.get("event") == "authorization_failed"
    ]
    auth_ok = [
        event for event in log_events if event.get("event") == "authentication_succeeded"
    ]
    assert auth_failed
    assert authz_failed
    assert auth_ok
    assert all("request_id" in event for event in [*auth_failed, *authz_failed, *auth_ok])


def test_privacy_sentinels_are_not_logged_on_auth_failure(
    oidc_client_with_logs: TestClient,
    log_events: list[dict],
) -> None:
    """Authentication logs must not contain tokens or claim sentinels."""
    response = oidc_client_with_logs.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(_PRIVATE_TOKEN_SENTINEL),
    )
    assert response.status_code == 401
    serialized = repr(log_events)
    assert _PRIVATE_TOKEN_SENTINEL not in serialized
    assert _PRIVATE_CLAIM_SENTINEL not in serialized
    assert "Authorization" not in serialized
    failed = [event for event in log_events if event.get("event") == "authentication_failed"]
    assert failed
    assert failed[-1]["reason"] in {"invalid_token", "missing_token"}


def test_privacy_sentinels_are_not_logged_for_valid_token(
    oidc_client_with_logs: TestClient,
    private_key,
    log_events: list[dict],
) -> None:
    """Successful auth logs must not include subject, token, or extra claims."""
    token = encode_test_token(
        private_key,
        extra_claims={"scp": TEST_PERMISSION, "name": _PRIVATE_CLAIM_SENTINEL},
    )
    response = oidc_client_with_logs.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(token),
    )
    assert response.status_code == 200
    serialized = repr(log_events)
    assert token not in serialized
    assert _PRIVATE_CLAIM_SENTINEL not in serialized
    assert "eci-test-subject" not in serialized
    assert TEST_ISSUER not in serialized
    succeeded = [event for event in log_events if event.get("event") == "authentication_succeeded"]
    assert succeeded
    for event in succeeded:
        assert "issuer" not in event
        assert "subject" not in event
        assert "user_id" not in event
