"""Integration tests for analysis history and persist-after-analyze."""

from collections.abc import Iterator
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_ai_provider, get_token_validator, get_unit_of_work_factory
from app.core.config import get_settings
from app.core.exceptions import PersistenceError
from app.domain.interfaces import AIProvider, PersistenceUnitOfWork
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.infrastructure.storage.database import (
    create_database_engine,
    create_session_factory,
)
from app.infrastructure.storage.models import Analysis, Base, User
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork
from app.main import create_app
from app.providers.mock.provider import MockAIProvider
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
_ANALYSES_URL = "/api/v1/analyses"
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
_SUBJECT_A = "user-a-subject"
_SUBJECT_B = "user-b-subject"
_FORBIDDEN_RESPONSE_KEYS = {
    "user_id",
    "issuer",
    "subject",
    "raw_body",
    "sender",
    "recipient",
    "recipients",
    "email",
    "access_token",
    "refresh_token",
    "Authorization",
}


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _enable_oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setenv("OIDC_REQUIRED_PERMISSION", TEST_PERMISSION)


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


def _authorized_token(private_key, subject: str = _SUBJECT_A) -> str:
    return encode_test_token(
        private_key,
        subject=subject,
        extra_claims={"scp": TEST_PERMISSION},
    )


def _sqlite_session_factory() -> sessionmaker[Session]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def _uow_factory_for(session_factory: sessionmaker[Session]):
    def _factory() -> PersistenceUnitOfWork:
        return SqlAlchemyPersistenceUnitOfWork(session_factory)

    return _factory


def _analysis_count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(Analysis))
        return int(count or 0)


def _user_count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(User))
        return int(count or 0)


def _collect_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value.keys())
        for item in value.values():
            keys.update(_collect_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_keys(item))
    return keys


def _assert_history_privacy(payload: object) -> None:
    keys = _collect_keys(payload)
    assert keys.isdisjoint(_FORBIDDEN_RESPONSE_KEYS)


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def persisted_client(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    log_events: list[dict],
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """OIDC TestClient with in-memory SQLite persistence."""
    del log_events
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    session_factory = _sqlite_session_factory()
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: _uow_factory_for(
        session_factory
    )
    with TestClient(application) as test_client:
        yield test_client, session_factory


def test_user_a_analyze_list_get_delete_cycle(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """Authenticated analyze should persist history that the owner can manage."""
    client, session_factory = persisted_client
    provider = MagicMock(wraps=MockAIProvider())
    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    headers = bearer_header(_authorized_token(private_key, _SUBJECT_A))

    created = client.post(_ANALYZE_URL, json=_valid_payload(), headers=headers)
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["provider"] == "mock"
    analysis_id = created_body["analysis_id"]
    UUID(analysis_id)
    assert provider.analyze.call_count == 1

    listed = client.get(_ANALYSES_URL, headers=headers)
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["limit"] == 20
    assert listed_body["offset"] == 0
    assert len(listed_body["items"]) == 1
    assert listed_body["items"][0]["analysis_id"] == analysis_id
    _assert_history_privacy(listed_body)

    fetched = client.get(f"{_ANALYSES_URL}/{analysis_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["analysis_id"] == analysis_id
    _assert_history_privacy(fetched.json())

    deleted = client.delete(f"{_ANALYSES_URL}/{analysis_id}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""

    missing = client.get(f"{_ANALYSES_URL}/{analysis_id}", headers=headers)
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Analysis not found."}
    assert _analysis_count(session_factory) == 0
    assert provider.analyze.call_count == 1


def test_user_b_cannot_read_or_delete_user_a_analysis(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """Cross-user get and delete must return 404 and must not remove data."""
    client, session_factory = persisted_client
    headers_a = bearer_header(_authorized_token(private_key, _SUBJECT_A))
    headers_b = bearer_header(_authorized_token(private_key, _SUBJECT_B))

    created = client.post(_ANALYZE_URL, json=_valid_payload(), headers=headers_a)
    assert created.status_code == 200
    analysis_id = created.json()["analysis_id"]

    listed_b = client.get(_ANALYSES_URL, headers=headers_b)
    assert listed_b.status_code == 200
    assert listed_b.json()["items"] == []

    get_b = client.get(f"{_ANALYSES_URL}/{analysis_id}", headers=headers_b)
    assert get_b.status_code == 404
    assert get_b.json() == {"detail": "Analysis not found."}

    delete_b = client.delete(f"{_ANALYSES_URL}/{analysis_id}", headers=headers_b)
    assert delete_b.status_code == 404
    assert delete_b.json() == {"detail": "Analysis not found."}

    still_there = client.get(f"{_ANALYSES_URL}/{analysis_id}", headers=headers_a)
    assert still_there.status_code == 200
    assert still_there.json()["analysis_id"] == analysis_id
    assert _analysis_count(session_factory) == 1


def test_history_without_token_returns_401(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """History endpoints require a bearer token."""
    client, _session_factory = persisted_client
    provider = MagicMock(spec=AIProvider)
    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    analysis_id = uuid4()

    listed = client.get(_ANALYSES_URL)
    fetched = client.get(f"{_ANALYSES_URL}/{analysis_id}")
    deleted = client.delete(f"{_ANALYSES_URL}/{analysis_id}")

    for response in (listed, fetched, deleted):
        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}
        assert response.headers.get("www-authenticate") == "Bearer"
    provider.analyze.assert_not_called()
    assert _analysis_count(_session_factory) == 0


def test_history_without_permission_returns_403(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """History authorization must run before identity persistence."""
    client, session_factory = persisted_client
    provider = MagicMock(spec=AIProvider)
    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    headers = bearer_header(encode_test_token(private_key, subject=_SUBJECT_A))

    listed = client.get(_ANALYSES_URL, headers=headers)
    fetched = client.get(f"{_ANALYSES_URL}/{uuid4()}", headers=headers)
    deleted = client.delete(f"{_ANALYSES_URL}/{uuid4()}", headers=headers)
    analyze = client.post(_ANALYZE_URL, json=_valid_payload(), headers=headers)

    assert listed.status_code == 403
    assert fetched.status_code == 403
    assert deleted.status_code == 403
    assert analyze.status_code == 403
    provider.analyze.assert_not_called()
    assert _analysis_count(session_factory) == 0
    assert _user_count(session_factory) == 0


def test_auth_disabled_analyze_does_not_persist_and_history_is_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development auth-disabled mode must not expose or persist history."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(_ANALYZE_URL, json=_valid_payload())
        listed = client.get(_ANALYSES_URL)
        fetched = client.get(f"{_ANALYSES_URL}/{uuid4()}")
        deleted = client.delete(f"{_ANALYSES_URL}/{uuid4()}")

    assert created.status_code == 200
    assert "analysis_id" not in created.json()
    for response in (listed, fetched, deleted):
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"


def test_persistence_disabled_analyze_omits_id_and_history_is_503(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    """OIDC without DATABASE_URL keeps analyze working and history unavailable."""
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    headers = bearer_header(_authorized_token(private_key))

    with TestClient(application) as client:
        created = client.post(_ANALYZE_URL, json=_valid_payload(), headers=headers)
        listed = client.get(_ANALYSES_URL, headers=headers)
        fetched = client.get(f"{_ANALYSES_URL}/{uuid4()}", headers=headers)
        deleted = client.delete(f"{_ANALYSES_URL}/{uuid4()}", headers=headers)

    assert created.status_code == 200
    assert "analysis_id" not in created.json()
    for response in (listed, fetched, deleted):
        assert response.status_code == 503
        assert response.json() == {"detail": "Persistence is currently unavailable."}


def test_identity_failure_before_ai_returns_503(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """Database unavailability before inference must not call the provider."""
    client, _session_factory = persisted_client
    provider = MagicMock(spec=AIProvider)

    def _failing_factory() -> PersistenceUnitOfWork:
        raise PersistenceError("Could not persist identity.")

    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    client.app.dependency_overrides[get_unit_of_work_factory] = lambda: _failing_factory

    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(_authorized_token(private_key)),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Persistence is currently unavailable."}
    provider.analyze.assert_not_called()


def test_save_failure_after_ai_returns_200_without_analysis_id(
    log_events: list[dict],
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """A failed save keeps the AI result and does not retry the provider."""
    client, session_factory = persisted_client
    provider = MagicMock(wraps=MockAIProvider())

    class _FailingSaveUnitOfWork(SqlAlchemyPersistenceUnitOfWork):
        def __enter__(self) -> PersistenceUnitOfWork:
            super().__enter__()

            def _save(_analysis: object) -> object:
                raise PersistenceError("Could not persist analysis.")

            self.analysis_repository.save = _save  # type: ignore[method-assign]
            return self

    def _factory() -> PersistenceUnitOfWork:
        return _FailingSaveUnitOfWork(session_factory)
    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    client.app.dependency_overrides[get_unit_of_work_factory] = lambda: _factory

    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(_authorized_token(private_key)),
    )

    assert response.status_code == 200
    body = response.json()
    assert "analysis_id" not in body
    assert body["analysis"]["summary"]["text"]
    assert provider.analyze.call_count == 1
    assert _analysis_count(session_factory) == 0
    failed = [event for event in log_events if event.get("event") == "analysis_persistence_failed"]
    assert failed
    serialized = repr(log_events)
    assert TEST_ISSUER not in serialized
    assert _SUBJECT_A not in serialized
    assert "user_id" not in serialized
    assert all("issuer" not in event for event in failed)
    assert all("subject" not in event for event in failed)


def test_provider_failure_does_not_persist_analysis(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """Provider errors keep existing HTTP behavior and create no analysis row."""
    client, session_factory = persisted_client

    class _FailingProvider(AIProvider):
        def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
            raise RuntimeError("provider unreachable")

    client.app.dependency_overrides[get_ai_provider] = lambda: _FailingProvider()
    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload(),
        headers=bearer_header(_authorized_token(private_key)),
    )

    assert response.status_code == 500
    assert "failed to analyze" in response.json()["detail"].lower()
    assert _analysis_count(session_factory) == 0


def test_pagination_validation(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """History list query parameters are validated by the API."""
    client, _session_factory = persisted_client
    headers = bearer_header(_authorized_token(private_key))

    default = client.get(_ANALYSES_URL, headers=headers)
    assert default.status_code == 200
    assert default.json()["limit"] == 20
    assert default.json()["offset"] == 0

    valid = client.get(f"{_ANALYSES_URL}?limit=1&offset=0", headers=headers)
    assert valid.status_code == 200

    assert client.get(f"{_ANALYSES_URL}?limit=0", headers=headers).status_code == 422
    assert client.get(f"{_ANALYSES_URL}?limit=101", headers=headers).status_code == 422
    assert client.get(f"{_ANALYSES_URL}?offset=-1", headers=headers).status_code == 422


def test_history_read_does_not_create_identity(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """History GET/DELETE must not create a user merely because the caller authenticated."""
    client, session_factory = persisted_client
    headers = bearer_header(_authorized_token(private_key))

    listed = client.get(_ANALYSES_URL, headers=headers)
    fetched = client.get(f"{_ANALYSES_URL}/{uuid4()}", headers=headers)
    deleted = client.delete(f"{_ANALYSES_URL}/{uuid4()}", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert fetched.status_code == 404
    assert deleted.status_code == 404
    assert _user_count(session_factory) == 0
    assert _analysis_count(session_factory) == 0


def test_history_response_omits_identity_and_raw_content(
    persisted_client: tuple[TestClient, sessionmaker[Session]],
    private_key,
) -> None:
    """History JSON must not expose ownership identity or request body fields."""
    client, _session_factory = persisted_client
    headers = bearer_header(_authorized_token(private_key))
    created = client.post(_ANALYZE_URL, json=_valid_payload(), headers=headers)
    analysis_id = created.json()["analysis_id"]
    listed = client.get(_ANALYSES_URL, headers=headers).json()
    fetched = client.get(f"{_ANALYSES_URL}/{analysis_id}", headers=headers).json()
    _assert_history_privacy(listed)
    _assert_history_privacy(fetched)
    assert "Sharing the notes from today's standup" not in repr(listed)
    assert "Sharing the notes from today's standup" not in repr(fetched)
