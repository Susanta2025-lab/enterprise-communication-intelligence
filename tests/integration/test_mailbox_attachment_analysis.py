"""HTTP tests for explicit attachment analysis, ownership, and isolation."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_ai_provider,
    get_attachment_scanner,
    get_communication_action_executor_factory,
    get_communication_connector_factory,
    get_token_validator,
    get_unit_of_work_factory,
)
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.security import (
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticatedPrincipal,
)
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.communication_action_executor_factory import (
    CommunicationActionExecutorFactory,
)
from app.domain.models import AttachmentMetadata
from app.infrastructure.attachments.fake_scanner import (
    FAILURE_FIXTURE_LABEL,
    MALICIOUS_FIXTURE_LABEL,
    UNKNOWN_FIXTURE_LABEL,
    FakeAttachmentScanner,
)
from app.infrastructure.connectors.fake import FakeCommunicationConnector
from app.main import create_app
from app.providers.mock.provider import MockAIProvider
from tests.support.connector_factory import StaticCommunicationConnectorFactory
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.support.jwt_tokens import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    TEST_JWKS_URL,
    TEST_PERMISSION,
    TEST_SUBJECT,
    bearer_header,
    encode_test_token,
    generate_test_rsa_private_key,
    make_test_validator,
)
from tests.unit.infrastructure.attachments.fixtures import (
    docx_with_text,
    pdf_blank_pages,
    pdf_encrypted,
    pdf_with_text,
    png_with_dimensions,
    tiny_jpeg,
)

_ANALYZE = "/api/v1/connector-accounts/{connector_account_id}/messages/attachments/analyze"
_EMAIL_ANALYZE = "/api/v1/communications/analyze"
_MAILBOX_EMAIL_ANALYZE = "/api/v1/connector-accounts/{connector_account_id}/messages/analyze"
_HISTORY = "/api/v1/attachment-analyses"
_WORKFLOW = "/api/v1/workflow-actions"
_ANALYSES = "/api/v1/analyses"
_READ_ANALYZE = f"{COMMUNICATIONS_READ_PERMISSION} {TEST_PERMISSION}"
_ALL_SCOPES = (
    f"{COMMUNICATIONS_READ_PERMISSION} {TEST_PERMISSION} "
    f"{COMMUNICATIONS_WORKFLOW_PERMISSION} {COMMUNICATIONS_SEND_PERMISSION}"
)
_SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "LOG_LEVEL",
    "API_V1_PREFIX",
    "AI_PROVIDER",
    "AI_IMAGE_INPUT_ENABLED",
    "ATTACHMENT_SCANNER_BACKEND",
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


class _ForbiddenExecutorFactory(CommunicationActionExecutorFactory):
    def create_for_account(self, account):  # noqa: ANN001
        raise AssertionError("attachment analyze must not construct a write executor")


class _CountingConnector(FakeCommunicationConnector):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fetch_content_calls: list[tuple[str, str]] = []
        self.list_attachment_calls: list[str] = []

    def list_attachments(self, provider_message_id: str):
        self.list_attachment_calls.append(provider_message_id)
        return super().list_attachments(provider_message_id)

    def fetch_attachment_content(self, provider_message_id: str, provider_attachment_id: str):
        self.fetch_content_calls.append((provider_message_id, provider_attachment_id))
        return super().fetch_attachment_content(provider_message_id, provider_attachment_id)


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


def _token(private_key, scp: str, *, subject: str = TEST_SUBJECT) -> str:
    return encode_test_token(private_key, subject=subject, extra_claims={"scp": scp})


def _metadata(attachment_id: str, filename: str, media_type: str, size: int) -> AttachmentMetadata:
    return AttachmentMetadata(
        provider_attachment_id=attachment_id,
        filename=filename,
        media_type=media_type,
        reported_size=size,
    )


def _connector_for(
    filename: str,
    media_type: str,
    payload: bytes,
    *,
    attachment_id: str = "att-1",
    extra: list[tuple[str, str, str, bytes]] | None = None,
) -> _CountingConnector:
    items = [_metadata(attachment_id, filename, media_type, len(payload))]
    contents = {("fake-msg-001", attachment_id): payload}
    for extra_id, extra_name, extra_type, extra_payload in extra or []:
        items.append(_metadata(extra_id, extra_name, extra_type, len(extra_payload)))
        contents[("fake-msg-001", extra_id)] = extra_payload
    return _CountingConnector(
        attachments={"fake-msg-001": tuple(items)},
        attachment_contents=contents,
    )


def _seed_owner(unit: InMemoryUnitOfWork, *, subject: str = TEST_SUBJECT):
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION, COMMUNICATIONS_READ_PERMISSION}),
    )
    return IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)


def _usable_account(user_id, **kwargs):
    return sample_connector_account(
        user_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
        **kwargs,
    )


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def api(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> Iterator[tuple[TestClient, InMemoryUnitOfWork, _CountingConnector]]:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    payload = pdf_with_text("Budget totals remain within plan.")
    connector = _connector_for("report.pdf", "application/pdf", payload)
    factory = StaticCommunicationConnectorFactory(connector)
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = lambda: factory
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    with TestClient(application) as test_client:
        yield test_client, unit, connector


def test_unauthenticated_attachment_analyze_returns_401(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
) -> None:
    client, _unit, connector = api
    response = client.post(
        _ANALYZE.format(connector_account_id=uuid4()),
        json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
    )
    assert response.status_code == 401
    assert connector.fetch_content_calls == []


def test_partial_permissions_return_403(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, _unit, connector = api
    response = client.post(
        _ANALYZE.format(connector_account_id=uuid4()),
        json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
        headers=bearer_header(_token(private_key, TEST_PERMISSION)),
    )
    assert response.status_code == 403
    assert connector.fetch_content_calls == []


def test_successful_text_attachment_persists_structured_result(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, connector = api
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    response = client.post(
        _ANALYZE.format(connector_account_id=account.id),
        json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
        headers=bearer_header(_token(private_key, _READ_ANALYZE)),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["attachment_analysis_id"]
    assert "analysis_id" not in payload
    assert payload["provider_attachment_id"] == "att-1"
    assert payload["kind"] == "pdf"
    assert payload["summary"]["text"]
    assert payload["truncated"] is False
    assert "draft_reply" not in payload
    assert "extracted_text" not in payload
    stored = unit.attachment_analysis_store[UUID(payload["attachment_analysis_id"])]
    assert stored.user_id == owner_id
    assert stored.connector_account_id == account.id
    assert stored.summary_text
    assert not hasattr(stored, "extracted_text")
    assert connector.fetch_content_calls == [("fake-msg-001", "att-1")]
    assert unit.workflow_action_store == {}
    assert unit.analyses == {}


def test_repeated_explicit_analyze_creates_two_records(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, connector = api
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    headers = bearer_header(_token(private_key, _READ_ANALYZE))
    body = {"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"}
    first = client.post(
        _ANALYZE.format(connector_account_id=account.id),
        json=body,
        headers=headers,
    )
    second = client.post(
        _ANALYZE.format(connector_account_id=account.id), json=body, headers=headers
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["attachment_analysis_id"] != second.json()["attachment_analysis_id"]
    assert len(unit.attachment_analysis_store) == 2
    assert connector.fetch_content_calls == [
        ("fake-msg-001", "att-1"),
        ("fake-msg-001", "att-1"),
    ]


def test_only_requested_attachment_is_retrieved(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    unit = InMemoryUnitOfWork()
    primary = pdf_with_text("Primary statement")
    sibling = pdf_with_text("Sibling statement")
    connector = _connector_for(
        "primary.pdf",
        "application/pdf",
        primary,
        extra=[("att-2", "sibling.pdf", "application/pdf", sibling)],
    )
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: make_test_validator(private_key)
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = (
        lambda: StaticCommunicationConnectorFactory(connector)
    )
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        response = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=bearer_header(_token(private_key, _READ_ANALYZE)),
        )
    assert response.status_code == 200
    assert connector.fetch_content_calls == [("fake-msg-001", "att-1")]


def test_default_scanner_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    unit = InMemoryUnitOfWork()
    connector = _connector_for("report.pdf", "application/pdf", pdf_with_text("x"))
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: make_test_validator(private_key)
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = (
        lambda: StaticCommunicationConnectorFactory(connector)
    )
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        response = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=bearer_header(_token(private_key, _READ_ANALYZE)),
        )
    assert response.status_code == 503
    assert response.json() == {"detail": "Attachment scanner is unavailable."}
    assert unit.attachment_analysis_store == {}


@pytest.mark.parametrize(
    ("suffix", "status", "detail"),
    [
        (MALICIOUS_FIXTURE_LABEL, 422, "Attachment could not be processed."),
        (UNKNOWN_FIXTURE_LABEL, 422, "Attachment could not be processed."),
        (FAILURE_FIXTURE_LABEL, 503, "Attachment scanner is unavailable."),
    ],
)
def test_non_clean_scan_does_not_persist(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    suffix: bytes,
    status: int,
    detail: str,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    unit = InMemoryUnitOfWork()
    connector = _connector_for(
        "report.pdf",
        "application/pdf",
        pdf_with_text("clean narrative") + suffix,
    )
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: make_test_validator(private_key)
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = (
        lambda: StaticCommunicationConnectorFactory(connector)
    )
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        response = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=bearer_header(_token(private_key, _READ_ANALYZE)),
        )
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert unit.attachment_analysis_store == {}


@pytest.mark.parametrize(
    ("filename", "media_type", "payload", "status", "detail"),
    [
        ("archive.zip", "application/zip", b"PK\x03\x04", 422, "Attachment is not supported."),
        (
            "huge.pdf",
            "application/pdf",
            pdf_with_text("x"),
            422,
            "Attachment exceeds limits.",
        ),
        ("secret.pdf", "application/pdf", pdf_encrypted(), 422, "Attachment is not supported."),
        ("empty.pdf", "application/pdf", pdf_blank_pages(1), 422, "Attachment is not supported."),
        (
            "notes.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"not-a-docx",
            422,
            "Attachment is not supported.",
        ),
        (
            "bomb.png",
            "image/png",
            png_with_dimensions(9000, 9000),
            422,
            "Attachment exceeds limits.",
        ),
    ],
)
def test_policy_and_parser_failures_do_not_persist(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    filename: str,
    media_type: str,
    payload: bytes,
    status: int,
    detail: str,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    unit = InMemoryUnitOfWork()
    if filename == "huge.pdf":
        metadata = _metadata("att-1", filename, media_type, 6 * 1024 * 1024)
        connector = _CountingConnector(
            attachments={"fake-msg-001": (metadata,)},
            attachment_contents={("fake-msg-001", "att-1"): payload},
        )
    else:
        connector = _connector_for(filename, media_type, payload)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: make_test_validator(private_key)
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = (
        lambda: StaticCommunicationConnectorFactory(connector)
    )
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        response = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=bearer_header(_token(private_key, _READ_ANALYZE)),
        )
    assert response.status_code == status
    assert response.json()["detail"] == detail
    assert unit.attachment_analysis_store == {}


def test_ai_failure_does_not_persist(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    unit = InMemoryUnitOfWork()
    connector = _connector_for("notes.txt", "text/plain", b"hello attachment")
    provider = MagicMock()
    provider.supports_image_input.return_value = False
    provider.analyze.side_effect = RuntimeError("provider down")
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: make_test_validator(private_key)
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = (
        lambda: StaticCommunicationConnectorFactory(connector)
    )
    application.dependency_overrides[get_ai_provider] = lambda: provider
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        response = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=bearer_header(_token(private_key, _READ_ANALYZE)),
        )
    assert response.status_code == 500
    assert unit.attachment_analysis_store == {}
    assert isinstance(provider.analyze.call_args, tuple) or provider.analyze.called


def test_image_requires_capability_flag(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    unit = InMemoryUnitOfWork()
    connector = _connector_for("photo.jpg", "image/jpeg", tiny_jpeg())
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: make_test_validator(private_key)
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = (
        lambda: StaticCommunicationConnectorFactory(connector)
    )
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider(
        supports_image_input=True
    )
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        disabled = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=bearer_header(_token(private_key, _READ_ANALYZE)),
        )
    assert disabled.status_code == 409
    assert disabled.json() == {"detail": "Image analysis is not available."}
    assert unit.attachment_analysis_store == {}

    monkeypatch.setenv("AI_IMAGE_INPUT_ENABLED", "true")
    get_settings.cache_clear()
    with TestClient(application) as client:
        enabled = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=bearer_header(_token(private_key, _READ_ANALYZE)),
        )
    assert enabled.status_code == 200
    assert enabled.json()["kind"] == "jpeg"
    assert enabled.json()["extracted_content_status"] == "image"


def test_cross_user_connector_message_attachment_and_history_are_404(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    unit = InMemoryUnitOfWork()
    owner_id = _seed_owner(unit)
    other_id = _seed_owner(unit, subject="other-subject")
    owned = _usable_account(owner_id)
    foreign = _usable_account(other_id, external_account_id="mailbox-other")
    unit.connector_account_store[owned.id] = owned
    unit.connector_account_store[foreign.id] = foreign
    owner_connector = _connector_for("report.pdf", "application/pdf", pdf_with_text("owned"))
    other_connector = FakeCommunicationConnector()

    class _OwnedOnlyFactory:
        calls: list[UUID] = []

        def create_for_account(self, account):  # noqa: ANN001
            self.calls.append(account.id)
            if account.id == owned.id:
                return owner_connector
            return other_connector

    factory = _OwnedOnlyFactory()
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: make_test_validator(private_key)
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = lambda: factory
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    owner_headers = bearer_header(_token(private_key, _ALL_SCOPES))
    other_headers = bearer_header(_token(private_key, _ALL_SCOPES, subject="other-subject"))
    with TestClient(application) as client:
        created = client.post(
            _ANALYZE.format(connector_account_id=owned.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=owner_headers,
        )
        assert created.status_code == 200
        analysis_id = created.json()["attachment_analysis_id"]
        stolen_connector = client.post(
            _ANALYZE.format(connector_account_id=owned.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=other_headers,
        )
        stolen_ids = client.post(
            _ANALYZE.format(connector_account_id=foreign.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=other_headers,
        )
        stolen_history = client.get(f"{_HISTORY}/{analysis_id}", headers=other_headers)
        stolen_list = client.get(_HISTORY, headers=other_headers)
    assert stolen_connector.status_code == 404
    assert stolen_connector.json() == {"detail": "Connector account not found."}
    assert stolen_ids.status_code == 404
    assert stolen_ids.json() == {"detail": "Mailbox attachment not found."}
    assert stolen_history.status_code == 404
    assert stolen_history.json() == {"detail": "Attachment analysis not found."}
    assert stolen_list.status_code == 200
    assert stolen_list.json()["items"] == []
    assert "owned" not in stolen_connector.text.lower()


def test_inactive_or_unreadable_mailbox_is_409(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, connector = api
    owner_id = _seed_owner(unit)
    disconnected = _usable_account(owner_id, status=ConnectorAccountStatus.DISCONNECTED)
    no_read = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(),
    )
    unit.connector_account_store[disconnected.id] = disconnected
    unit.connector_account_store[no_read.id] = no_read
    headers = bearer_header(_token(private_key, _READ_ANALYZE))
    first = client.post(
        _ANALYZE.format(connector_account_id=disconnected.id),
        json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
        headers=headers,
    )
    second = client.post(
        _ANALYZE.format(connector_account_id=no_read.id),
        json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
        headers=headers,
    )
    assert first.status_code == 409
    assert second.status_code == 409
    assert first.json() == second.json() == {"detail": "Connected mailbox is not available."}
    assert connector.fetch_content_calls == []


def test_history_list_and_get_are_owner_scoped(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, _connector = api
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    headers = bearer_header(_token(private_key, _READ_ANALYZE))
    created = client.post(
        _ANALYZE.format(connector_account_id=account.id),
        json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
        headers=headers,
    )
    analysis_id = created.json()["attachment_analysis_id"]
    listed = client.get(
        _HISTORY,
        params={"connector_account_id": str(account.id), "provider_message_id": "fake-msg-001"},
        headers=headers,
    )
    fetched = client.get(f"{_HISTORY}/{analysis_id}", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["attachment_analysis_id"] == analysis_id
    assert fetched.status_code == 200
    assert fetched.json()["attachment_analysis_id"] == analysis_id


def test_attachment_analysis_is_not_a_workflow_source(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, _connector = api
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    headers = bearer_header(_token(private_key, _ALL_SCOPES))
    created = client.post(
        _ANALYZE.format(connector_account_id=account.id),
        json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
        headers=headers,
    )
    analysis_id = created.json()["attachment_analysis_id"]
    proposed = client.post(_WORKFLOW, json={"analysis_id": analysis_id}, headers=headers)
    email_history = client.get(f"{_ANALYSES}/{analysis_id}", headers=headers)
    assert proposed.status_code == 404
    assert proposed.json() == {"detail": "Analysis not found."}
    assert email_history.status_code == 404
    assert unit.workflow_action_store == {}


def test_email_analyze_routes_remain_attachment_free(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, connector = api
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    headers = bearer_header(_token(private_key, _READ_ANALYZE))
    rejected = client.post(
        _EMAIL_ANALYZE,
        json={
            "message": {
                "body": "Sharing standup notes.",
                "message_id": "direct-msg-001",
                "metadata": {
                    "source_type": "email",
                    "sender": "alice@example.com",
                    "recipients": ["bob@example.com"],
                    "subject": "Standup",
                },
            },
            "attachment_images": [
                {"media_type": "image/png", "content": "QQ=="},
            ],
        },
        headers=headers,
    )
    mailbox = client.post(
        _MAILBOX_EMAIL_ANALYZE.format(connector_account_id=account.id),
        json={"provider_message_id": "fake-msg-001"},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "Attachment analysis is not available on this endpoint."
    assert mailbox.status_code == 200
    assert "analysis_id" in mailbox.json()
    assert connector.fetch_content_calls == []


def test_docx_success_and_missing_attachment_404(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    unit = InMemoryUnitOfWork()
    connector = _connector_for(
        "memo.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        docx_with_text("Please review the attached memo."),
    )
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: make_test_validator(private_key)
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = (
        lambda: StaticCommunicationConnectorFactory(connector)
    )
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    owner_id = _seed_owner(unit)
    account = _usable_account(owner_id)
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        headers = bearer_header(_token(private_key, _READ_ANALYZE))
        success = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
            headers=headers,
        )
        missing = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "missing"},
            headers=headers,
        )
        unknown_message = client.post(
            _ANALYZE.format(connector_account_id=account.id),
            json={"provider_message_id": "no-such-message", "provider_attachment_id": "att-1"},
            headers=headers,
        )
    assert success.status_code == 200
    assert success.json()["kind"] == "docx"
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Mailbox attachment not found."}
    assert unknown_message.status_code == 404
    assert unknown_message.json() == {"detail": "Mailbox message not found."}
