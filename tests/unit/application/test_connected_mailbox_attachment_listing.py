"""Unit tests for ConnectedMailboxAttachmentListingService."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    AttachmentNotSupportedError,
    ConnectedMailboxNotAvailableError,
    ConnectorAccountNotFoundError,
    MailboxMessageNotFoundError,
)
from app.application.services.connected_mailbox_attachment_listing import (
    ConnectedMailboxAttachmentListingService,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import (
    CommunicationConnectorNotAvailableError,
    ConnectorMessageNotFoundError,
    ConnectorUnsupportedAttachmentError,
)
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import (
    AttachmentDisposition,
    CommunicationCapability,
    ConnectorAccountStatus,
)
from app.domain.interfaces import CommunicationConnector
from app.domain.interfaces.communication_connector import AttachmentMetadataPage
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.models import AttachmentContent, AttachmentMetadata, CommunicationMessage
from app.infrastructure.connectors.fake import FakeCommunicationConnector
from tests.support.connector_factory import StaticCommunicationConnectorFactory
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION, TEST_SUBJECT

_LIST_FIELDS = frozenset(
    {
        "provider_attachment_id",
        "filename",
        "media_type",
        "reported_size",
        "is_inline",
        "disposition",
    }
)


class _RecordingConnector:
    def __init__(
        self,
        inner: CommunicationConnector,
        *,
        error: Exception | None = None,
    ) -> None:
        self.inner = inner
        self.error = error
        self.list_ids: list[str] = []
        self.fetch_message_ids: list[str] = []
        self.fetch_content_ids: list[tuple[str, str]] = []

    @property
    def provider(self) -> str:
        return self.inner.provider

    def list_messages(self, query):  # noqa: ANN001
        raise AssertionError("attachment listing must not list mailbox messages")

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        self.fetch_message_ids.append(provider_message_id)
        raise AssertionError("attachment listing must not fetch message bodies")

    def list_attachments(self, provider_message_id: str) -> AttachmentMetadataPage:
        self.list_ids.append(provider_message_id)
        if self.error is not None:
            raise self.error
        return self.inner.list_attachments(provider_message_id)

    def fetch_attachment_content(
        self,
        provider_message_id: str,
        provider_attachment_id: str,
    ) -> AttachmentContent:
        self.fetch_content_ids.append((provider_message_id, provider_attachment_id))
        raise AssertionError("attachment listing must not fetch attachment content")


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _seed_user(unit: InMemoryUnitOfWork) -> UUID:
    return IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(_principal())


def _seed_account(
    unit: InMemoryUnitOfWork,
    user_id: UUID,
    *,
    status: ConnectorAccountStatus = ConnectorAccountStatus.ACTIVE,
    granted_capabilities: tuple[CommunicationCapability, ...] | None = (
        CommunicationCapability.MAIL_READ,
    ),
) -> ConnectorAccountRecord:
    account = sample_connector_account(
        user_id,
        provider="gmail",
        status=status,
        granted_capabilities=granted_capabilities,
    )
    unit.connector_account_store[account.id] = account
    return account


def _service(
    unit: InMemoryUnitOfWork,
    connector: CommunicationConnector,
) -> tuple[ConnectedMailboxAttachmentListingService, StaticCommunicationConnectorFactory]:
    uow_factory = UnitOfWorkFactory(unit)
    factory = StaticCommunicationConnectorFactory(connector)
    service = ConnectedMailboxAttachmentListingService(
        IdentityResolver(uow_factory),
        uow_factory,
        factory,
    )
    return service, factory


def test_owned_account_lists_public_metadata_without_bytes() -> None:
    unit = InMemoryUnitOfWork()
    account = _seed_account(unit, _seed_user(unit))
    metadata = AttachmentMetadata(
        provider_attachment_id="att-1",
        filename="Contract.pdf",
        media_type="application/pdf",
        reported_size=1_800_000,
        is_inline=False,
        disposition=AttachmentDisposition.ATTACHMENT,
    )
    connector = _RecordingConnector(
        FakeCommunicationConnector(attachments={"fake-msg-001": (metadata,)})
    )
    service, factory = _service(unit, connector)

    response = service.list_attachments(_principal(), account.id, "fake-msg-001")

    assert factory.calls == 1
    assert connector.list_ids == ["fake-msg-001"]
    assert connector.fetch_message_ids == []
    assert connector.fetch_content_ids == []
    assert response.truncated is False
    assert len(response.items) == 1
    item = response.items[0]
    assert item.filename == "Contract.pdf"
    assert item.media_type == "application/pdf"
    assert item.reported_size == 1_800_000
    assert item.is_inline is False
    assert set(item.model_dump()) == _LIST_FIELDS
    serialized = repr(response.model_dump())
    assert "content_id" not in serialized
    assert "content" not in item.model_dump()
    assert unit.attachment_analyses.list_for_user(account.user_id, limit=10, offset=0) == []


def test_unknown_message_is_not_found() -> None:
    unit = InMemoryUnitOfWork()
    account = _seed_account(unit, _seed_user(unit))
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorMessageNotFoundError(),
    )
    service, _ = _service(unit, connector)

    with pytest.raises(MailboxMessageNotFoundError):
        service.list_attachments(_principal(), account.id, "missing-msg")
    assert connector.fetch_content_ids == []


def test_unsupported_metadata_surface_fails_closed() -> None:
    unit = InMemoryUnitOfWork()
    account = _seed_account(unit, _seed_user(unit))
    connector = _RecordingConnector(
        FakeCommunicationConnector(),
        error=ConnectorUnsupportedAttachmentError(),
    )
    service, _ = _service(unit, connector)

    with pytest.raises(AttachmentNotSupportedError):
        service.list_attachments(_principal(), account.id, "fake-msg-001")
    assert connector.fetch_content_ids == []


def test_unknown_account_is_not_found() -> None:
    unit = InMemoryUnitOfWork()
    _seed_user(unit)
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, _ = _service(unit, connector)

    with pytest.raises(ConnectorAccountNotFoundError):
        service.list_attachments(_principal(), uuid4(), "fake-msg-001")
    assert connector.list_ids == []


def test_disconnected_account_is_unavailable() -> None:
    unit = InMemoryUnitOfWork()
    account = _seed_account(
        unit,
        _seed_user(unit),
        status=ConnectorAccountStatus.DISCONNECTED,
        granted_capabilities=(),
    )
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, _ = _service(unit, connector)

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.list_attachments(_principal(), account.id, "fake-msg-001")
    assert connector.list_ids == []


def test_unroutable_connector_is_unavailable() -> None:
    unit = InMemoryUnitOfWork()
    account = _seed_account(unit, _seed_user(unit))
    factory = StaticCommunicationConnectorFactory(FakeCommunicationConnector())

    class _FailingFactory(StaticCommunicationConnectorFactory):
        def create_for_account(self, account: ConnectorAccountRecord) -> CommunicationConnector:
            raise CommunicationConnectorNotAvailableError()

    service = ConnectedMailboxAttachmentListingService(
        IdentityResolver(UnitOfWorkFactory(unit)),
        UnitOfWorkFactory(unit),
        _FailingFactory(FakeCommunicationConnector()),
    )

    with pytest.raises(ConnectedMailboxNotAvailableError):
        service.list_attachments(_principal(), account.id, "fake-msg-001")
    assert factory.calls == 0


def test_empty_attachment_list_is_valid() -> None:
    unit = InMemoryUnitOfWork()
    account = _seed_account(unit, _seed_user(unit))
    connector = _RecordingConnector(FakeCommunicationConnector())
    service, _ = _service(unit, connector)

    response = service.list_attachments(_principal(), account.id, "fake-msg-001")

    assert response.items == []
    assert response.truncated is False
    assert connector.fetch_content_ids == []
