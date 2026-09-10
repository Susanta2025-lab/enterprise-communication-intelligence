"""Gmail ephemeral attachmentId churn must not break explicit Analyze.

Listing exposes stable MIME partId as provider_attachment_id. Analyze must
resolve that listed id after a fresh messages.get that mints a new
body.attachmentId. Metadata listing must never download attachment bytes.
"""

from __future__ import annotations

import base64

import httpx

from app.application.services.attachment_inspection import AttachmentInspectionService
from app.domain.enums import AttachmentKind, AttachmentScanVerdict
from app.infrastructure.attachments import FakeAttachmentScanner
from app.infrastructure.connectors.gmail import GmailCommunicationConnector
from tests.unit.infrastructure.connectors.gmail.conftest import (
    GMAIL_API_PREFIX,
    GMAIL_TOKEN,
    GmailHttpStub,
    attachment_part,
    gmail_resource,
    header,
    text_part,
)


def _b64url_bytes(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _mixed_payload(*parts: object) -> dict:
    return {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
            header("Subject", "With attachments"),
        ],
        "parts": list(parts),
    }


def test_inspect_resolves_listed_part_id_after_attachment_id_churn() -> None:
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    stub = GmailHttpStub()
    generation = {"n": 0}

    def _resource_for_generation() -> dict:
        generation["n"] += 1
        ephemeral = f"ANGjdJ-ephemeral-{generation['n']}"
        resource = gmail_resource(
            "msg-1",
            payload=_mixed_payload(
                text_part("Visible body"),
                attachment_part(
                    attachment_id=ephemeral,
                    part_id="1",
                    filename="report.pdf",
                    mime_type="application/pdf",
                    size=len(pdf),
                ),
            ),
        )
        stub.attachment_payloads[("msg-1", ephemeral)] = {
            "size": len(pdf),
            "data": _b64url_bytes(pdf),
            "attachmentId": ephemeral,
        }
        return resource

    class _ChurningMessages(dict):
        def get(self, key, default=None):  # noqa: ANN001
            if key != "msg-1":
                return super().get(key, default)
            return _resource_for_generation()

        def __contains__(self, key: object) -> bool:
            return key == "msg-1" or super().__contains__(key)

    stub.messages = _ChurningMessages()
    client = httpx.Client(transport=httpx.MockTransport(stub))
    connector = GmailCommunicationConnector(
        http_client=client,
        access_token_provider=lambda: GMAIL_TOKEN,
    )
    try:
        listed = connector.list_attachments("msg-1")
        assert [item.provider_attachment_id for item in listed.items] == ["1"]
        assert stub.attachment_content_requests == []
        listed_id = listed.items[0].provider_attachment_id

        inspected = AttachmentInspectionService(FakeAttachmentScanner()).inspect(
            connector,
            "msg-1",
            listed_id,
        )

        assert inspected.kind is AttachmentKind.PDF
        assert inspected.scan.verdict is AttachmentScanVerdict.CLEAN
        assert inspected.content.content == pdf
        assert inspected.content.source_attachment_id == listed_id
        assert inspected.content.metadata.provider_attachment_id == listed_id
        assert generation["n"] >= 2
        assert [request.url.path for request in stub.attachment_content_requests] == [
            f"{GMAIL_API_PREFIX}/msg-1/attachments/ANGjdJ-ephemeral-{generation['n']}"
        ]
    finally:
        client.close()
