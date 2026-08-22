"""Integration tests for POST /workflow-actions/{id}/execute."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import (
    get_communication_action_executor_factory,
    get_communication_credential_resolver,
    get_communication_http_client,
    get_execution_unit_of_work_factory,
    get_token_validator,
    get_unit_of_work_factory,
    require_authenticated_communications_send,
)
from app.core.config import get_settings
from app.core.security import (
    COMMUNICATIONS_SEND_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticatedPrincipal,
)
from app.domain.enums import ConnectorAccountStatus
from app.domain.interfaces import PersistenceUnitOfWork
from app.domain.interfaces.analysis_repository import NewAnalysis
from app.domain.interfaces.communication_action_executor import CommunicationActionExecutor
from app.domain.interfaces.communication_credential_resolver import (
    CommunicationCredentialResolver,
)
from app.domain.interfaces.connector_account_repository import (
    ConnectorAccountRecord,
    NewConnectorAccount,
)
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.infrastructure.executors.factory import ProviderCommunicationActionExecutorFactory
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
from tests.unit.infrastructure.executors.gmail.conftest import (
    MAILBOX_ADDRESS,
    GmailReplyHttpStub,
)
from tests.unit.infrastructure.executors.microsoft_graph.conftest import GraphReplyHttpStub

_WORKFLOW_URL = "/api/v1/workflow-actions"
_ANALYSES_URL = "/api/v1/analyses"
_SUBJECT_A = "user-a-subject"
_SUBJECT_B = "user-b-subject"
_DRAFT_BODY = "Thanks, I will review the report and respond by Friday."
_PROVIDER_MESSAGE_ID = "provider-msg-execute-001"
_CREDENTIAL_REF = "demo-account"
_SECRET_CREDENTIAL_REF_12E = "SECRET_CREDENTIAL_REF_12E"
_SECRET_MAILBOX = "secret-mailbox@example.test"
_GMAIL_TOKEN = "fake-gmail-execute-token"
_GRAPH_TOKEN = "fake-graph-execute-token"
_GMAIL_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_DEMO_ACCOUNT_ACCESS_TOKEN"
_GRAPH_ENV = "ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_DEMO_ACCOUNT_ACCESS_TOKEN"
_FORBIDDEN_RESPONSE_KEYS = {
    "user_id",
    "owner_user_id",
    "issuer",
    "subject",
    "credential_ref",
    "connector_account_id",
    "provider_message_id",
    "access_token",
    "refresh_token",
    "mailbox_address",
    "recipient",
    "Authorization",
}
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


class CountingResolver(EnvironmentCommunicationCredentialResolver):
    """Environment resolver that counts resolve and token invocations."""

    def __init__(self, environ: dict[str, str]) -> None:
        super().__init__(environ)
        self.resolve_calls = 0
        self.token_calls = 0

    def resolve(self, *, credential_ref: str, provider: str):
        self.resolve_calls += 1
        inner = super().resolve(credential_ref=credential_ref, provider=provider)

        def counted() -> str:
            self.token_calls += 1
            return inner()

        return counted


class CountingUnitOfWorkFactory:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls = 0
        self.executor_factory_constructed = 0
        self.executor_factory_create_calls = 0
        self.http_clients_created = 0
        self.http_clients_closed = 0

    def __call__(self) -> PersistenceUnitOfWork:
        self.calls += 1
        return self._inner()


class CountingExecutorFactory:
    def __init__(
        self,
        inner: ProviderCommunicationActionExecutorFactory,
        probe: CountingUnitOfWorkFactory,
    ) -> None:
        self._inner = inner
        self._probe = probe
        probe.executor_factory_constructed += 1

    def create_for_account(
        self,
        account: ConnectorAccountRecord,
    ) -> CommunicationActionExecutor | None:
        self._probe.executor_factory_create_calls += 1
        return self._inner.create_for_account(account)


def _reject_network(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(599, json={"error": "offline tests must not use the network"})


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


def _sqlite_session_factory() -> sessionmaker[Session]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def _uow_factory_for(session_factory: sessionmaker[Session]):
    def _factory() -> PersistenceUnitOfWork:
        return SqlAlchemyPersistenceUnitOfWork(session_factory)

    return _factory


def _token(private_key, subject: str, *permissions: str, extra_claims: dict | None = None) -> str:
    claims: dict[str, Any] = extra_claims.copy() if extra_claims else {"scp": " ".join(permissions)}
    return encode_test_token(private_key, subject=subject, extra_claims=claims)


def _headers(
    private_key,
    subject: str,
    *permissions: str,
    extra_claims: dict | None = None,
) -> dict[str, str]:
    return bearer_header(
        _token(private_key, subject, *permissions, extra_claims=extra_claims),
    )


def _send_headers(private_key, subject: str = _SUBJECT_A) -> dict[str, str]:
    return _headers(private_key, subject, COMMUNICATIONS_SEND_PERMISSION)


def _setup_headers(private_key, subject: str = _SUBJECT_A) -> dict[str, str]:
    return _headers(
        private_key,
        subject,
        COMMUNICATIONS_WORKFLOW_PERMISSION,
        COMMUNICATIONS_SEND_PERMISSION,
    )


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


def _assert_execute_privacy(payload: object) -> None:
    keys = _collect_keys(payload)
    assert keys.isdisjoint(_FORBIDDEN_RESPONSE_KEYS)
    serialized = repr(payload)
    assert _GMAIL_TOKEN not in serialized
    assert _GRAPH_TOKEN not in serialized
    assert _CREDENTIAL_REF not in serialized
    assert MAILBOX_ADDRESS not in serialized
    assert _SECRET_CREDENTIAL_REF_12E not in serialized
    assert _SECRET_MAILBOX not in serialized


def _seed_owned_workflow(
    session_factory: sessionmaker[Session],
    *,
    subject: str,
    provider: str,
    credential_ref: str | None = _CREDENTIAL_REF,
    account_status: ConnectorAccountStatus = ConnectorAccountStatus.ACTIVE,
    draft_body: str = _DRAFT_BODY,
) -> tuple[UUID, UUID]:
    uow = SqlAlchemyPersistenceUnitOfWork(session_factory)
    with uow:
        user_id = uow.identity_repository.create_user_with_external_identity(
            TEST_ISSUER,
            subject,
        )
        account = uow.connector_accounts.create(
            NewConnectorAccount(
                user_id=user_id,
                provider=provider,
                external_account_id="opaque-mailbox-locator-not-email",
                credential_ref=credential_ref,
            )
        )
        if account_status is ConnectorAccountStatus.DISCONNECTED:
            disconnected = uow.connector_accounts.disconnect_owned(account.id, user_id)
            assert disconnected is not None
            account = disconnected
        analysis = uow.analysis_repository.save(
            NewAnalysis(
                user_id=user_id,
                provider="mock",
                priority="medium",
                category="general",
                source_type="email",
                summary_text="Status summary",
                action_items=[{"description": "Review notes"}],
                message_id=_PROVIDER_MESSAGE_ID,
                summary_confidence=0.9,
                draft_reply={"body": draft_body, "tone": "professional", "confidence": 0.8},
                connector_account_id=account.id,
            )
        )
        uow.commit()
    return analysis.id, account.id


def _approve_action(
    client: TestClient,
    private_key,
    analysis_id: UUID,
    *,
    subject: str = _SUBJECT_A,
) -> dict:
    created = client.post(
        _WORKFLOW_URL,
        json={"analysis_id": str(analysis_id)},
        headers=_setup_headers(private_key, subject),
    )
    assert created.status_code == 201
    approved = client.post(
        f"{_WORKFLOW_URL}/{created.json()['id']}/approve",
        headers=_setup_headers(private_key, subject),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    return approved.json()


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    *,
    session_factory: sessionmaker[Session] | None = None,
    transport: httpx.MockTransport | None = None,
    environ: dict[str, str] | None = None,
    uow_factory: CountingUnitOfWorkFactory | None = None,
    resolver: CountingResolver | None = None,
) -> tuple[TestClient, CountingUnitOfWorkFactory, CountingResolver]:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    sessions = session_factory or _sqlite_session_factory()
    counted_uow = uow_factory or CountingUnitOfWorkFactory(_uow_factory_for(sessions))
    counted_resolver = resolver or CountingResolver(environ or {})
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: counted_uow

    def _execution_uow(
        _principal: Annotated[
            AuthenticatedPrincipal,
            Depends(require_authenticated_communications_send),
        ],
    ) -> CountingUnitOfWorkFactory:
        return counted_uow

    application.dependency_overrides[get_execution_unit_of_work_factory] = _execution_uow

    def _resolver(
        _principal: Annotated[
            AuthenticatedPrincipal,
            Depends(require_authenticated_communications_send),
        ],
    ) -> CommunicationCredentialResolver:
        return counted_resolver

    application.dependency_overrides[get_communication_credential_resolver] = _resolver

    def _http_client(
        _principal: Annotated[
            AuthenticatedPrincipal,
            Depends(require_authenticated_communications_send),
        ],
    ) -> Iterator[httpx.Client]:
        counted_uow.http_clients_created += 1
        client = httpx.Client(
            transport=transport or httpx.MockTransport(_reject_network),
            follow_redirects=False,
        )
        try:
            yield client
            assert not client.is_closed
        finally:
            client.close()
            counted_uow.http_clients_closed += 1

    application.dependency_overrides[get_communication_http_client] = _http_client

    def _executor_factory(
        _principal: Annotated[
            AuthenticatedPrincipal,
            Depends(require_authenticated_communications_send),
        ],
        http_client: Annotated[httpx.Client, Depends(get_communication_http_client)],
        credential_resolver: Annotated[
            CommunicationCredentialResolver,
            Depends(get_communication_credential_resolver),
        ],
    ) -> CountingExecutorFactory:
        return CountingExecutorFactory(
            ProviderCommunicationActionExecutorFactory(
                credential_resolver=credential_resolver,
                http_client=http_client,
            ),
            counted_uow,
        )

    application.dependency_overrides[get_communication_action_executor_factory] = (
        _executor_factory
    )
    return TestClient(application), counted_uow, counted_resolver


def _build_production_path_client(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    *,
    session_factory: sessionmaker[Session],
    transport: httpx.MockTransport,
    token_env: dict[str, str],
) -> tuple[TestClient, CountingUnitOfWorkFactory]:
    """Compose the real factory and environment resolver; override only HTTP."""
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    for name, value in token_env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    counted_uow = CountingUnitOfWorkFactory(_uow_factory_for(session_factory))
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: counted_uow

    def _execution_uow(
        _principal: Annotated[
            AuthenticatedPrincipal,
            Depends(require_authenticated_communications_send),
        ],
    ) -> CountingUnitOfWorkFactory:
        return counted_uow

    application.dependency_overrides[get_execution_unit_of_work_factory] = _execution_uow

    def _http_client(
        _principal: Annotated[
            AuthenticatedPrincipal,
            Depends(require_authenticated_communications_send),
        ],
    ) -> Iterator[httpx.Client]:
        counted_uow.http_clients_created += 1
        client = httpx.Client(transport=transport, follow_redirects=False)
        try:
            yield client
            assert not client.is_closed
        finally:
            client.close()
            counted_uow.http_clients_closed += 1

    application.dependency_overrides[get_communication_http_client] = _http_client
    return TestClient(application), counted_uow


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


def test_graph_execute_reaches_executed(monkeypatch: pytest.MonkeyPatch, private_key) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, uow_factory = _build_production_path_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        token_env={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        uow_before = uow_factory.calls
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "executed"
    assert body["executed_at"] is not None
    assert body["failed_at"] is None
    assert body["approved_reply_body"] == _DRAFT_BODY
    _assert_execute_privacy(body)
    assert len(stub.requests) == 1
    assert stub.requests[0].method == "POST"
    assert stub.requests[0].url.path.endswith("/reply")
    assert stub.requests[0].headers.get("authorization") == f"Bearer {_GRAPH_TOKEN}"
    assert uow_factory.calls > uow_before
    assert uow_factory.http_clients_created == 1
    assert uow_factory.http_clients_closed == 1


def test_gmail_execute_reaches_executed(monkeypatch: pytest.MonkeyPatch, private_key) -> None:
    stub = GmailReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="gmail",
    )
    client, uow_factory = _build_production_path_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        token_env={_GMAIL_ENV: _GMAIL_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "executed"
    _assert_execute_privacy(body)
    assert len(stub.profile_requests()) == 1
    assert len(stub.metadata_requests()) == 1
    assert len(stub.send_requests()) == 1
    assert stub.profile_requests()[0].headers.get("authorization") == f"Bearer {_GMAIL_TOKEN}"
    assert stub.metadata_requests()[0].headers.get("authorization") == f"Bearer {_GMAIL_TOKEN}"
    assert stub.send_requests()[0].headers.get("authorization") == f"Bearer {_GMAIL_TOKEN}"
    assert uow_factory.http_clients_created == 1
    assert uow_factory.http_clients_closed == 1


def test_provider_definite_rejection_returns_200_failed(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    stub.status = 400
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, _uow, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_at"] is not None
    assert body["executed_at"] is None
    _assert_execute_privacy(body)
    assert len(stub.requests) == 1
    assert resolver.token_calls == 1


def test_provider_unavailable_returns_503_executing(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    stub.status = 503
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, _uow, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Communication action execution is currently unavailable."
    }
    assert stored.status_code == 200
    assert stored.json()["status"] == "executing"
    assert len(stub.requests) == 1
    assert resolver.token_calls == 1


def test_missing_secret_returns_503_executing_without_provider_http(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, _uow, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )

    assert response.status_code == 503
    assert stored.json()["status"] == "executing"
    assert resolver.resolve_calls == 1
    assert resolver.token_calls == 1
    assert stub.requests == []
    serialized = f"{response.json()}{stored.json()}"
    assert _CREDENTIAL_REF not in serialized
    assert _GRAPH_ENV not in serialized
    assert "ECI_COMMUNICATION_CREDENTIAL" not in serialized


def test_missing_credential_ref_returns_409_approved(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
        credential_ref=None,
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        uow_before = uow_factory.calls
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Workflow action is not executable."}
    assert stored.json()["status"] == "approved"
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert stub.requests == []
    assert uow_factory.calls > uow_before


def test_unsupported_provider_returns_409_approved(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="fake",
    )
    client, _uow, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Workflow action is not executable."}
    assert "fake" not in response.json()["detail"].lower()
    assert stored.json()["status"] == "approved"
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert stub.requests == []


def test_disconnected_account_returns_409_approved(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
        account_status=ConnectorAccountStatus.DISCONNECTED,
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )

    assert response.status_code == 409
    assert stored.json()["status"] == "approved"
    assert resolver.token_calls == 0
    assert stub.requests == []
    assert uow_factory.executor_factory_create_calls == 0
    assert uow_factory.executor_factory_create_calls == 0


def test_unknown_workflow_returns_404_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    missing_id = uuid4()
    with client:
        uow_before = uow_factory.calls
        response = client.post(
            f"{_WORKFLOW_URL}/{missing_id}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Workflow action not found."}
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert stub.requests == []
    assert uow_factory.calls > uow_before
    assert uow_factory.executor_factory_create_calls == 0


def test_cross_user_workflow_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_B,
        provider="microsoft_graph",
        credential_ref="other-account",
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id, subject=_SUBJECT_A)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key, _SUBJECT_B),
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Workflow action not found."}
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert stub.requests == []
    assert uow_factory.executor_factory_create_calls == 0


@pytest.mark.parametrize(
    "setup",
    ["pending", "rejected", "executing", "executed", "failed"],
)
def test_non_approved_states_do_not_call_provider(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    setup: str,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        created = client.post(
            _WORKFLOW_URL,
            json={"analysis_id": str(analysis_id)},
            headers=_setup_headers(private_key),
        )
        assert created.status_code == 201
        action_id = created.json()["id"]
        if setup == "rejected":
            rejected = client.post(
                f"{_WORKFLOW_URL}/{action_id}/reject",
                headers=_setup_headers(private_key),
            )
            assert rejected.status_code == 200
        elif setup != "pending":
            approved = client.post(
                f"{_WORKFLOW_URL}/{action_id}/approve",
                headers=_setup_headers(private_key),
            )
            assert approved.status_code == 200
            if setup == "failed":
                stub.status = 400
            elif setup == "executing":
                stub.status = 500
            first = client.post(
                f"{_WORKFLOW_URL}/{action_id}/execute",
                headers=_send_headers(private_key),
            )
            if setup == "executed":
                assert first.status_code == 200
            elif setup == "failed":
                assert first.status_code == 200
            else:
                assert first.status_code == 503
            stub.requests.clear()
            resolver.token_calls = 0
            stub.status = 202
        factory_create_before = uow_factory.executor_factory_create_calls
        response = client.post(
            f"{_WORKFLOW_URL}/{action_id}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 409
    assert stub.requests == []
    assert resolver.token_calls == 0
    assert uow_factory.executor_factory_create_calls == factory_create_before


def test_second_execute_does_not_call_provider_again(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, _uow, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        first = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        second = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert first.status_code == 200
    assert first.json()["status"] == "executed"
    assert second.status_code == 409
    assert len(stub.requests) == 1
    assert resolver.token_calls == 1


def test_analysis_delete_does_not_block_execute(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, _uow, _resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        deleted = client.delete(
            f"{_ANALYSES_URL}/{analysis_id}",
            headers=_headers(private_key, _SUBJECT_A, TEST_PERMISSION),
        )
        assert deleted.status_code == 204
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    assert response.json()["analysis_id"] == str(analysis_id)
    assert len(stub.requests) == 1


def test_missing_token_is_401_without_execution_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        uow_before = uow_factory.calls
        resolve_before = resolver.resolve_calls
        token_before = resolver.token_calls
        http_before = len(stub.requests)
        factory_constructed_before = uow_factory.executor_factory_constructed
        factory_create_before = uow_factory.executor_factory_create_calls
        response = client.post(f"{_WORKFLOW_URL}/{approved['id']}/execute")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert uow_factory.calls == uow_before
    assert uow_factory.executor_factory_constructed == factory_constructed_before
    assert uow_factory.executor_factory_create_calls == factory_create_before
    assert uow_factory.http_clients_created == 0
    assert uow_factory.http_clients_closed == 0
    assert resolver.resolve_calls == resolve_before
    assert resolver.token_calls == token_before
    assert len(stub.requests) == http_before


def test_invalid_token_is_401_without_execution_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        uow_before = uow_factory.calls
        factory_constructed_before = uow_factory.executor_factory_constructed
        factory_create_before = uow_factory.executor_factory_create_calls
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers={"Authorization": "Bearer not-a-jwt"},
        )

    assert response.status_code == 401
    assert uow_factory.calls == uow_before
    assert uow_factory.executor_factory_constructed == factory_constructed_before
    assert uow_factory.executor_factory_create_calls == factory_create_before
    assert uow_factory.http_clients_created == 0
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert stub.requests == []


def test_workflow_permission_is_403_without_execution_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        uow_before = uow_factory.calls
        factory_constructed_before = uow_factory.executor_factory_constructed
        factory_create_before = uow_factory.executor_factory_create_calls
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_headers(private_key, _SUBJECT_A, COMMUNICATIONS_WORKFLOW_PERMISSION),
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}
    assert uow_factory.calls == uow_before
    assert uow_factory.executor_factory_constructed == factory_constructed_before
    assert uow_factory.executor_factory_create_calls == factory_create_before
    assert uow_factory.http_clients_created == 0
    assert uow_factory.http_clients_closed == 0
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert stub.requests == []


@pytest.mark.parametrize(
    "extra_claims",
    [
        {"scp": COMMUNICATIONS_SEND_PERMISSION},
        {"scope": COMMUNICATIONS_SEND_PERMISSION},
        {"roles": [COMMUNICATIONS_SEND_PERMISSION]},
    ],
)
def test_send_permission_claim_representations(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    extra_claims: dict[str, object],
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, _uow, _resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_headers(
                private_key,
                _SUBJECT_A,
                extra_claims=extra_claims,
            ),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    assert len(stub.requests) == 1


def test_send_only_principal_cannot_create_or_approve(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, _uow, _resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    send_headers = _send_headers(private_key)
    with client:
        created = client.post(
            _WORKFLOW_URL,
            json={"analysis_id": str(analysis_id)},
            headers=send_headers,
        )
        listed = client.get(_WORKFLOW_URL, headers=send_headers)

    assert created.status_code == 403
    assert listed.status_code == 403


def test_auth_disabled_execute_returns_401(monkeypatch: pytest.MonkeyPatch, private_key) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    constructed = {"http_clients": 0, "uow_factories": 0}
    real_client = httpx.Client

    def _counting_client(*args, **kwargs):
        constructed["http_clients"] += 1
        return real_client(*args, **kwargs)

    monkeypatch.setattr("app.api.dependencies.httpx.Client", _counting_client)
    import app.api.dependencies as deps

    original_uow_factory = deps.get_unit_of_work_factory

    def _counting_uow_factory() -> object:
        constructed["uow_factories"] += 1
        return original_uow_factory()

    monkeypatch.setattr(deps, "get_unit_of_work_factory", _counting_uow_factory)
    application = create_app()
    with TestClient(application) as client:
        response = client.post(f"{_WORKFLOW_URL}/{uuid4()}/execute")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert constructed["http_clients"] == 0
    assert constructed["uow_factories"] == 0


def test_malformed_credential_locator_returns_409_approved(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    log_events: list[dict],
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
        credential_ref=_SECRET_CREDENTIAL_REF_12E,
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Workflow action is not executable."}
    assert stored.json()["status"] == "approved"
    assert resolver.token_calls == 0
    assert stub.requests == []
    assert uow_factory.executor_factory_create_calls == 1
    blob = f"{response.json()}{stored.json()}{log_events!r}"
    assert _SECRET_CREDENTIAL_REF_12E not in blob
    assert _GRAPH_ENV not in blob


def test_gmail_provider_definite_rejection_returns_200_failed(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GmailReplyHttpStub()
    stub.send_status = 400
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="gmail",
    )
    client, uow_factory = _build_production_path_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        token_env={_GMAIL_ENV: _GMAIL_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_at"] is not None
    _assert_execute_privacy(body)
    assert len(stub.profile_requests()) == 1
    assert len(stub.metadata_requests()) == 1
    assert len(stub.send_requests()) == 1
    assert uow_factory.http_clients_closed == 1


def test_unauthorized_execute_does_not_construct_production_http_client(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, uow_factory, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    constructed = {"count": 0}
    real_client = httpx.Client

    def _counting_client(*args, **kwargs):
        constructed["count"] += 1
        return real_client(*args, **kwargs)

    monkeypatch.setattr("app.api.dependencies.httpx.Client", _counting_client)
    del client.app.dependency_overrides[get_communication_http_client]
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        uow_before = uow_factory.calls
        response = client.post(f"{_WORKFLOW_URL}/{approved['id']}/execute")

    assert response.status_code == 401
    assert uow_factory.calls == uow_before
    assert constructed["count"] == 0
    assert resolver.resolve_calls == 0
    assert stub.requests == []


@pytest.mark.parametrize(
    ("fail_stage", "expected_profile", "expected_metadata", "expected_send"),
    [
        ("profile", 1, 0, 0),
        ("metadata", 1, 1, 0),
    ],
)
def test_gmail_presend_unavailable_returns_503_executing_without_send(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    fail_stage: str,
    expected_profile: int,
    expected_metadata: int,
    expected_send: int,
) -> None:
    stub = GmailReplyHttpStub()
    if fail_stage == "profile":
        stub.profile_status = 500
    else:
        stub.metadata_status = 500
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="gmail",
    )
    client, _uow_factory = _build_production_path_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        token_env={_GMAIL_ENV: _GMAIL_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )
        retry = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 503
    assert stored.json()["status"] == "executing"
    assert retry.status_code == 409
    assert len(stub.profile_requests()) == expected_profile
    assert len(stub.metadata_requests()) == expected_metadata
    assert len(stub.send_requests()) == expected_send


def test_gmail_send_unavailable_returns_503_executing_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GmailReplyHttpStub()
    stub.send_status = 500
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="gmail",
    )
    client, _uow_factory = _build_production_path_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        token_env={_GMAIL_ENV: _GMAIL_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )
        retry = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Communication action execution is currently unavailable."
    }
    assert stored.json()["status"] == "executing"
    assert retry.status_code == 409
    assert len(stub.profile_requests()) == 1
    assert len(stub.metadata_requests()) == 1
    assert len(stub.send_requests()) == 1


def test_graph_timeout_returns_503_executing_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphReplyHttpStub()
    stub.transport_error = httpx.TimeoutException("timed out contacting Graph")
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
    )
    client, _uow, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: _GRAPH_TOKEN},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )
        retry = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )

    assert response.status_code == 503
    assert stored.json()["status"] == "executing"
    assert retry.status_code == 409
    assert len(stub.requests) == 1
    assert resolver.token_calls == 1
    assert "timed out" not in response.json()["detail"]


def test_execute_privacy_markers_are_absent_from_http_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    log_events: list[dict],
) -> None:
    token = "SUPER_SECRET_PHASE12_TOKEN"
    reply_body = "SUPER_SECRET_PHASE12_REPLY_BODY"
    mailbox = "secret-mailbox-phase12@example.test"
    provider_error = "SUPER_SECRET_PHASE12_PROVIDER_ERROR"
    stub = GmailReplyHttpStub()
    stub.profile_json = {"emailAddress": mailbox}
    stub.send_status = 403
    stub.send_json = {"error": {"message": provider_error}}
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="gmail",
        draft_body=reply_body,
    )
    client, _uow = _build_production_path_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        token_env={_GMAIL_ENV: token},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    blob = f"{response.json()}{stored.json()}{log_events!r}"
    assert token not in blob
    assert mailbox not in blob
    assert provider_error not in blob
    assert "SUPER_SECRET_PHASE12_CREDENTIAL_REF" not in blob
    assert "Authorization" not in blob
    assert "Bearer " not in blob
    assert _GMAIL_ENV not in blob
    _assert_execute_privacy(response.json())
    assert stored.json()["approved_reply_body"] == reply_body
    assert reply_body not in repr(log_events)


def test_malformed_phase12_credential_ref_is_absent_from_http_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    log_events: list[dict],
) -> None:
    marker = "SUPER_SECRET_PHASE12_CREDENTIAL_REF"
    stub = GraphReplyHttpStub()
    session_factory = _sqlite_session_factory()
    analysis_id, _account_id = _seed_owned_workflow(
        session_factory,
        subject=_SUBJECT_A,
        provider="microsoft_graph",
        credential_ref=marker,
    )
    client, _uow, resolver = _build_client(
        monkeypatch,
        private_key,
        session_factory=session_factory,
        transport=httpx.MockTransport(stub),
        environ={_GRAPH_ENV: "SUPER_SECRET_PHASE12_TOKEN"},
    )
    with client:
        approved = _approve_action(client, private_key, analysis_id)
        response = client.post(
            f"{_WORKFLOW_URL}/{approved['id']}/execute",
            headers=_send_headers(private_key),
        )
        stored = client.get(
            f"{_WORKFLOW_URL}/{approved['id']}",
            headers=_setup_headers(private_key),
        )

    assert response.status_code == 409
    assert stored.json()["status"] == "approved"
    assert resolver.token_calls == 0
    assert stub.requests == []
    blob = f"{response.json()}{stored.json()}{log_events!r}"
    assert marker not in blob
    assert "SUPER_SECRET_PHASE12_TOKEN" not in blob
    assert _GRAPH_ENV not in blob

