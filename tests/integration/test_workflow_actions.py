"""Integration tests for workflow proposal and approval HTTP endpoints."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import (
    get_token_validator,
    get_unit_of_work_factory,
    get_workflow_action_service,
)
from app.application.exceptions import WorkflowActionConflictError
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.security import COMMUNICATIONS_WORKFLOW_PERMISSION
from app.domain.interfaces import PersistenceUnitOfWork
from app.infrastructure.storage.database import (
    create_database_engine,
    create_session_factory,
)
from app.infrastructure.storage.models import Base
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork
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
_ANALYSES_URL = "/api/v1/analyses"
_WORKFLOW_URL = "/api/v1/workflow-actions"
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
    "owner_user_id",
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
    "credential_ref",
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


def _valid_payload(*, include_draft_reply: bool = True) -> dict:
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
        "include_draft_reply": include_draft_reply,
        "include_action_items": True,
    }


def _token(private_key, subject: str, *permissions: str) -> str:
    return encode_test_token(
        private_key,
        subject=subject,
        extra_claims={"scp": " ".join(permissions)},
    )


def _headers(private_key, subject: str, *permissions: str) -> dict[str, str]:
    return bearer_header(_token(private_key, subject, *permissions))


def _both_headers(private_key, subject: str = _SUBJECT_A) -> dict[str, str]:
    return _headers(private_key, subject, TEST_PERMISSION, COMMUNICATIONS_WORKFLOW_PERMISSION)


def _sqlite_session_factory() -> sessionmaker[Session]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def _uow_factory_for(session_factory: sessionmaker[Session]):
    def _factory() -> PersistenceUnitOfWork:
        return SqlAlchemyPersistenceUnitOfWork(session_factory)

    return _factory


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


def _assert_workflow_privacy(payload: object) -> None:
    keys = _collect_keys(payload)
    assert keys.isdisjoint(_FORBIDDEN_RESPONSE_KEYS)


def _create_analysis(
    client: TestClient,
    private_key,
    *,
    subject: str = _SUBJECT_A,
    include_draft_reply: bool = True,
) -> tuple[str, str | None]:
    created = client.post(
        _ANALYZE_URL,
        json=_valid_payload(include_draft_reply=include_draft_reply),
        headers=_both_headers(private_key, subject),
    )
    assert created.status_code == 200
    body = created.json()
    analysis_id = body["analysis_id"]
    UUID(analysis_id)
    draft = None
    if include_draft_reply:
        draft = body["analysis"]["draft_reply"]["body"]
        assert draft
    return analysis_id, draft


def _create_action(
    client: TestClient,
    private_key,
    analysis_id: str,
    *,
    subject: str = _SUBJECT_A,
) -> dict:
    response = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": analysis_id},
        headers=_both_headers(private_key, subject),
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def persisted_client(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> Iterator[TestClient]:
    """OIDC TestClient with in-memory SQLite persistence."""
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
        yield test_client


def test_create_owned_analysis_with_draft_returns_pending_snapshot(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Create snapshots the owned draft reply into a PENDING reply action."""
    client = persisted_client
    analysis_id, draft = _create_analysis(client, private_key)
    created = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": analysis_id},
        headers=_both_headers(private_key),
    )

    assert created.status_code == 201
    body = created.json()
    UUID(body["id"])
    assert body["action_type"] == "reply"
    assert body["status"] == "pending"
    assert body["analysis_id"] == analysis_id
    assert body["proposed_reply_body"] == draft
    assert body["approved_reply_body"] is None
    assert body["created_at"]
    assert body["approved_at"] is None
    assert body["rejected_at"] is None
    assert body["executed_at"] is None
    assert body["failed_at"] is None
    _assert_workflow_privacy(body)


def test_create_unknown_analysis_returns_404(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Unknown analyses are indistinguishable from cross-user analyses."""
    client = persisted_client
    response = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": str(uuid4())},
        headers=_both_headers(private_key),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Analysis not found."}


def test_create_cross_user_analysis_returns_same_404(
    persisted_client: TestClient,
    private_key,
) -> None:
    """A caller cannot propose a workflow from another user's analysis."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key, subject=_SUBJECT_A)
    response = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": analysis_id},
        headers=_both_headers(private_key, _SUBJECT_B),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Analysis not found."}


def test_create_analysis_without_draft_returns_409(
    persisted_client: TestClient,
    private_key,
) -> None:
    """An owned analysis without a usable draft cannot produce a proposal."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key, include_draft_reply=False)
    response = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": analysis_id},
        headers=_both_headers(private_key),
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Analysis has no usable draft reply."}


def test_create_rejects_invalid_uuid_and_extra_fields(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Create accepts only analysis_id and rejects extra caller-supplied fields."""
    client = persisted_client
    headers = _both_headers(private_key)
    analysis_id = str(uuid4())

    invalid = client.post(_WORKFLOW_URL, json={"analysis_id": "not-a-uuid"}, headers=headers)
    extra_body = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": analysis_id, "proposed_reply_body": "Hello"},
        headers=headers,
    )
    extra_status = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": analysis_id, "status": "pending"},
        headers=headers,
    )
    extra_type = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": analysis_id, "action_type": "reply"},
        headers=headers,
    )

    assert invalid.status_code == 422
    assert extra_body.status_code == 422
    assert extra_status.status_code == 422
    assert extra_type.status_code == 422


def test_same_analysis_can_create_multiple_workflow_actions(
    persisted_client: TestClient,
    private_key,
) -> None:
    """The same analysis_id may produce multiple independent workflow rows."""
    client = persisted_client
    analysis_id, draft = _create_analysis(client, private_key)
    first = _create_action(client, private_key, analysis_id)
    second = _create_action(client, private_key, analysis_id)

    assert first["id"] != second["id"]
    assert first["analysis_id"] == second["analysis_id"] == analysis_id
    assert first["proposed_reply_body"] == second["proposed_reply_body"] == draft
    assert first["status"] == second["status"] == "pending"


def test_list_returns_owned_actions_newest_first_with_pagination(
    persisted_client: TestClient,
    private_key,
) -> None:
    """List excludes other users, wraps items, and honors limit/offset."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key, subject=_SUBJECT_A)
    other_analysis_id, _other_draft = _create_analysis(client, private_key, subject=_SUBJECT_B)
    first = _create_action(client, private_key, analysis_id, subject=_SUBJECT_A)
    second = _create_action(client, private_key, analysis_id, subject=_SUBJECT_A)
    _create_action(client, private_key, other_analysis_id, subject=_SUBJECT_B)

    listed = client.get(_WORKFLOW_URL, headers=_both_headers(private_key, _SUBJECT_A))
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]
    _assert_workflow_privacy(body)

    limited = client.get(
        f"{_WORKFLOW_URL}?limit=1&offset=0",
        headers=_both_headers(private_key, _SUBJECT_A),
    )
    assert limited.status_code == 200
    limited_body = limited.json()
    assert limited_body["limit"] == 1
    assert limited_body["offset"] == 0
    assert [item["id"] for item in limited_body["items"]] == [second["id"]]

    offset = client.get(
        f"{_WORKFLOW_URL}?limit=1&offset=1",
        headers=_both_headers(private_key, _SUBJECT_A),
    )
    assert offset.status_code == 200
    assert [item["id"] for item in offset.json()["items"]] == [first["id"]]

    other = client.get(_WORKFLOW_URL, headers=_both_headers(private_key, _SUBJECT_B))
    assert [item["analysis_id"] for item in other.json()["items"]] == [other_analysis_id]


def test_list_query_parameter_validation(
    persisted_client: TestClient,
    private_key,
) -> None:
    """List pagination uses the same bounds as analysis history."""
    client = persisted_client
    headers = _both_headers(private_key)
    assert client.get(f"{_WORKFLOW_URL}?limit=0", headers=headers).status_code == 422
    assert client.get(f"{_WORKFLOW_URL}?limit=101", headers=headers).status_code == 422
    assert client.get(f"{_WORKFLOW_URL}?offset=-1", headers=headers).status_code == 422


def test_get_owned_unknown_cross_user_and_invalid_id(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Get returns owned actions and uses the same 404 for unknown and cross-user ids."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key)
    created = _create_action(client, private_key, analysis_id)

    owned = client.get(f"{_WORKFLOW_URL}/{created['id']}", headers=_both_headers(private_key))
    assert owned.status_code == 200
    assert owned.json()["id"] == created["id"]
    _assert_workflow_privacy(owned.json())

    unknown = client.get(f"{_WORKFLOW_URL}/{uuid4()}", headers=_both_headers(private_key))
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "Workflow action not found."}

    cross_user = client.get(
        f"{_WORKFLOW_URL}/{created['id']}",
        headers=_both_headers(private_key, _SUBJECT_B),
    )
    assert cross_user.status_code == 404
    assert cross_user.json() == {"detail": "Workflow action not found."}

    invalid = client.get(f"{_WORKFLOW_URL}/not-a-uuid", headers=_both_headers(private_key))
    assert invalid.status_code == 422


def test_get_remains_available_after_analysis_delete(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Dangling analysis provenance does not invalidate a stored workflow action."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key)
    created = _create_action(client, private_key, analysis_id)
    headers = _both_headers(private_key)

    deleted = client.delete(f"{_ANALYSES_URL}/{analysis_id}", headers=headers)
    assert deleted.status_code == 204

    fetched = client.get(f"{_WORKFLOW_URL}/{created['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["analysis_id"] == analysis_id
    assert fetched.json()["id"] == created["id"]


def test_approve_pending_copies_proposal_and_sets_approved_at(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Approve has no request body and snapshots the proposed reply."""
    client = persisted_client
    analysis_id, draft = _create_analysis(client, private_key)
    created = _create_action(client, private_key, analysis_id)

    approved = client.post(
        f"{_WORKFLOW_URL}/{created['id']}/approve",
        headers=_both_headers(private_key),
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved"
    assert body["proposed_reply_body"] == draft
    assert body["approved_reply_body"] == draft
    assert body["approved_at"] is not None
    assert body["rejected_at"] is None
    _assert_workflow_privacy(body)


def test_approve_after_analysis_delete_succeeds(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Approval does not reload the source analysis."""
    client = persisted_client
    analysis_id, draft = _create_analysis(client, private_key)
    created = _create_action(client, private_key, analysis_id)
    headers = _both_headers(private_key)
    assert client.delete(f"{_ANALYSES_URL}/{analysis_id}", headers=headers).status_code == 204

    approved = client.post(f"{_WORKFLOW_URL}/{created['id']}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_reply_body"] == draft


def test_approve_illegal_transitions_and_cross_user(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Repeated approve is not idempotent; cross-user approve is not-found."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key)
    pending = _create_action(client, private_key, analysis_id)
    rejected_source = _create_action(client, private_key, analysis_id)
    headers = _both_headers(private_key)

    assert client.post(
        f"{_WORKFLOW_URL}/{pending['id']}/approve",
        headers=headers,
    ).status_code == 200
    repeated = client.post(f"{_WORKFLOW_URL}/{pending['id']}/approve", headers=headers)
    assert repeated.status_code == 409
    assert repeated.json() == {"detail": "Invalid workflow state transition."}

    assert client.post(
        f"{_WORKFLOW_URL}/{rejected_source['id']}/reject",
        headers=headers,
    ).status_code == 200
    rejected_then_approve = client.post(
        f"{_WORKFLOW_URL}/{rejected_source['id']}/approve",
        headers=headers,
    )
    assert rejected_then_approve.status_code == 409
    assert rejected_then_approve.json() == {"detail": "Invalid workflow state transition."}

    other = _create_action(client, private_key, analysis_id)
    cross_user = client.post(
        f"{_WORKFLOW_URL}/{other['id']}/approve",
        headers=_both_headers(private_key, _SUBJECT_B),
    )
    assert cross_user.status_code == 404
    assert cross_user.json() == {"detail": "Workflow action not found."}


def test_reject_pending_retains_proposal_and_sets_rejected_at(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Reject has no request body and does not copy an approved snapshot."""
    client = persisted_client
    analysis_id, draft = _create_analysis(client, private_key)
    created = _create_action(client, private_key, analysis_id)

    rejected = client.post(
        f"{_WORKFLOW_URL}/{created['id']}/reject",
        headers=_both_headers(private_key),
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["status"] == "rejected"
    assert body["proposed_reply_body"] == draft
    assert body["approved_reply_body"] is None
    assert body["rejected_at"] is not None
    assert body["approved_at"] is None
    _assert_workflow_privacy(body)


def test_reject_after_analysis_delete_succeeds(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Rejection does not depend on the source analysis remaining."""
    client = persisted_client
    analysis_id, draft = _create_analysis(client, private_key)
    created = _create_action(client, private_key, analysis_id)
    headers = _both_headers(private_key)
    assert client.delete(f"{_ANALYSES_URL}/{analysis_id}", headers=headers).status_code == 204

    rejected = client.post(f"{_WORKFLOW_URL}/{created['id']}/reject", headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["proposed_reply_body"] == draft
    assert rejected.json()["approved_reply_body"] is None


def test_reject_illegal_transitions_and_cross_user(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Repeated reject is not idempotent; cross-user reject is not-found."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key)
    pending = _create_action(client, private_key, analysis_id)
    approved_source = _create_action(client, private_key, analysis_id)
    headers = _both_headers(private_key)

    assert client.post(
        f"{_WORKFLOW_URL}/{pending['id']}/reject",
        headers=headers,
    ).status_code == 200
    repeated = client.post(f"{_WORKFLOW_URL}/{pending['id']}/reject", headers=headers)
    assert repeated.status_code == 409
    assert repeated.json() == {"detail": "Invalid workflow state transition."}

    assert client.post(
        f"{_WORKFLOW_URL}/{approved_source['id']}/approve",
        headers=headers,
    ).status_code == 200
    approved_then_reject = client.post(
        f"{_WORKFLOW_URL}/{approved_source['id']}/reject",
        headers=headers,
    )
    assert approved_then_reject.status_code == 409
    assert approved_then_reject.json() == {"detail": "Invalid workflow state transition."}

    other = _create_action(client, private_key, analysis_id)
    cross_user = client.post(
        f"{_WORKFLOW_URL}/{other['id']}/reject",
        headers=_both_headers(private_key, _SUBJECT_B),
    )
    assert cross_user.status_code == 404
    assert cross_user.json() == {"detail": "Workflow action not found."}


def test_concurrency_conflict_maps_to_409(
    persisted_client: TestClient,
    private_key,
) -> None:
    """WorkflowActionConflictError is mapped at the HTTP boundary without retries."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key)
    created = _create_action(client, private_key, analysis_id)

    class _ConflictService:
        def approve(self, *_args: object, **_kwargs: object) -> None:
            raise WorkflowActionConflictError()

    client.app.dependency_overrides[get_workflow_action_service] = lambda: _ConflictService()
    response = client.post(
        f"{_WORKFLOW_URL}/{created['id']}/approve",
        headers=_both_headers(private_key),
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Workflow action was updated concurrently."}


def test_service_unavailable_maps_to_503(
    persisted_client: TestClient,
    private_key,
) -> None:
    """Persistence unavailability uses the generic 503 body."""
    client = persisted_client

    class _UnavailableService:
        def list(self, *_args: object, **_kwargs: object) -> None:
            raise ServiceUnavailableError("Persistence is currently unavailable.")

    client.app.dependency_overrides[get_workflow_action_service] = lambda: _UnavailableService()
    response = client.get(_WORKFLOW_URL, headers=_both_headers(private_key))
    assert response.status_code == 503
    assert response.json() == {"detail": "Persistence is currently unavailable."}
    serialized = repr(response.json())
    assert "postgresql" not in serialized.lower()
    assert "sqlite" not in serialized.lower()
    assert "DATABASE_URL" not in serialized


def test_workflow_without_persistence_returns_503(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    """OIDC without DATABASE_URL cannot serve workflow routes."""
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    headers = _both_headers(private_key)

    with TestClient(application) as client:
        listed = client.get(_WORKFLOW_URL, headers=headers)
        created = client.post(
            _WORKFLOW_URL,
            json={"analysis_id": str(uuid4())},
            headers=headers,
        )

    assert listed.status_code == 503
    assert created.status_code == 503
    assert listed.json() == {"detail": "Persistence is currently unavailable."}
    assert created.json() == {"detail": "Persistence is currently unavailable."}


def test_auth_disabled_workflow_routes_return_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUTH_MODE=disabled must not invent a local workflow principal."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()
    action_id = uuid4()

    with TestClient(create_app()) as client:
        listed = client.get(_WORKFLOW_URL)
        created = client.post(_WORKFLOW_URL, json={"analysis_id": str(uuid4())})
        fetched = client.get(f"{_WORKFLOW_URL}/{action_id}")
        approved = client.post(f"{_WORKFLOW_URL}/{action_id}/approve")
        rejected = client.post(f"{_WORKFLOW_URL}/{action_id}/reject")

    for response in (listed, created, fetched, approved, rejected):
        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}
        assert response.headers.get("www-authenticate") == "Bearer"


def test_missing_and_invalid_tokens_return_401(
    persisted_client: TestClient,
) -> None:
    """Missing and malformed bearer tokens are rejected before the service."""
    client = persisted_client
    missing = client.get(_WORKFLOW_URL)
    invalid = client.get(_WORKFLOW_URL, headers=bearer_header("not-a-jwt"))
    for response in (missing, invalid):
        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}
        assert response.headers.get("www-authenticate") == "Bearer"


def test_analyze_only_token_is_forbidden_on_workflow_routes(
    persisted_client: TestClient,
    private_key,
) -> None:
    """communications:analyze does not authorize workflow endpoints."""
    client = persisted_client
    headers = _headers(private_key, _SUBJECT_A, TEST_PERMISSION)
    listed = client.get(_WORKFLOW_URL, headers=headers)
    created = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": str(uuid4())},
        headers=headers,
    )
    assert listed.status_code == 403
    assert created.status_code == 403
    assert listed.json() == {"detail": "Not authorized"}
    assert created.json() == {"detail": "Not authorized"}


def test_workflow_only_token_allows_workflow_and_denies_analyze(
    persisted_client: TestClient,
    private_key,
) -> None:
    """communications:workflow authorizes workflow routes and not analyze."""
    client = persisted_client
    analysis_id, _draft = _create_analysis(client, private_key)
    workflow_headers = _headers(private_key, _SUBJECT_A, COMMUNICATIONS_WORKFLOW_PERMISSION)

    created = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": analysis_id},
        headers=workflow_headers,
    )
    listed = client.get(_WORKFLOW_URL, headers=workflow_headers)
    analyze = client.post(_ANALYZE_URL, json=_valid_payload(), headers=workflow_headers)

    assert created.status_code == 201
    assert listed.status_code == 200
    assert analyze.status_code == 403
    assert analyze.json() == {"detail": "Not authorized"}


def test_both_permissions_allow_analyze_and_workflow(
    persisted_client: TestClient,
    private_key,
) -> None:
    """A principal holding both capabilities can analyze and create a proposal."""
    client = persisted_client
    analysis_id, draft = _create_analysis(client, private_key)
    created = _create_action(client, private_key, analysis_id)
    assert created["proposed_reply_body"] == draft


def test_create_does_not_log_proposal_body(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    log_events: list[dict],
) -> None:
    """Proposal and approved reply bodies must not appear in structured logs."""
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
    with TestClient(application) as client:
        analysis_id, draft = _create_analysis(client, private_key)
        created = _create_action(client, private_key, analysis_id)
        client.post(
            f"{_WORKFLOW_URL}/{created['id']}/approve",
            headers=_both_headers(private_key),
        )

    serialized = repr(log_events)
    assert draft not in serialized
    assert "owner_user_id" not in serialized
    assert TEST_ISSUER not in serialized
    assert _SUBJECT_A not in serialized
    assert "communications:send" not in serialized
