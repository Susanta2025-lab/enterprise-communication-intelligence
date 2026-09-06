"""Gmail API v1 REST adapter that returns already-normalized messages."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.core.exceptions import (
    ConnectorAttachmentContentError,
    ConnectorAttachmentNotFoundError,
    ConnectorAuthenticationError,
    ConnectorError,
    ConnectorInvalidCursorError,
    ConnectorMessageNotFoundError,
    ConnectorPermissionError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
)
from app.domain.attachment_policy import MAX_ATTACHMENT_CONTENT_BYTES
from app.domain.interfaces import (
    AttachmentMetadataPage,
    CommunicationConnector,
    ConnectorMessageQuery,
    MessagePage,
)
from app.domain.models import AttachmentContent, AttachmentMetadata, CommunicationMessage
from app.infrastructure.connectors.common.auth import AccessTokenProvider, resolve_access_token
from app.infrastructure.connectors.gmail.normalization import (
    decode_gmail_base64url,
    gmail_rate_limit_reason,
    list_gmail_attachment_metadata,
    normalize_gmail_message,
    parse_list_page,
)

_GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
_LIST_URL = f"{_GMAIL_API_BASE}/users/me/messages"
_OPERATION_LIST = "list"
_OPERATION_FETCH = "fetch"
_OPERATION_LIST_ATTACHMENTS = "list_attachments"
_OPERATION_FETCH_ATTACHMENT = "fetch_attachment"
_ATTACHMENT_METADATA_MIME_DEPTH = 8
_ATTACHMENT_PART_FIELDS = "mimeType,filename,headers(name,value),body(size,attachmentId)"


def attachment_metadata_fields(depth: int = _ATTACHMENT_METADATA_MIME_DEPTH) -> str:
    """Gmail ``fields`` mask that keeps nested MIME metadata and omits ``body.data``.

    ``format=full`` still selects the MIME tree. The mask then excludes
    ``MessagePartBody.data`` at each unrolled ``parts`` level so metadata
    listing does not request embedded attachment bytes. Depth is finite
    because Gmail partial response cannot apply a recursive wildcard.
    """
    nested = _ATTACHMENT_PART_FIELDS
    for _ in range(max(depth, 0)):
        nested = f"{_ATTACHMENT_PART_FIELDS},parts({nested})"
    return f"id,payload({nested})"


_ATTACHMENT_METADATA_FIELDS = attachment_metadata_fields()


class GmailCommunicationConnector(CommunicationConnector):
    """Read-only Gmail REST connector.

    HTTP, MIME, and Gmail JSON stay inside this adapter. The caller owns the
    ``httpx.Client`` lifecycle and supplies an in-memory access-token callable.
    """

    def __init__(
        self,
        *,
        http_client: httpx.Client,
        access_token_provider: AccessTokenProvider,
    ) -> None:
        self._http = http_client
        self._access_token_provider = access_token_provider

    @property
    def provider(self) -> str:
        return "gmail"

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        """Return one Gmail list page, fetching each listed id sequentially."""
        params: dict[str, str | int] = {"maxResults": query.limit}
        has_cursor = query.cursor is not None
        if has_cursor:
            params["pageToken"] = query.cursor
        payload = self._get_json(
            _LIST_URL,
            params=params,
            operation=_OPERATION_LIST,
            has_cursor=has_cursor,
        )
        message_ids, next_cursor = parse_list_page(payload)
        items = [self.fetch_message(message_id) for message_id in message_ids]
        return MessagePage(items=items, next_cursor=next_cursor)

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        """Return one normalized message for a Gmail API message id.

        Uses ``format=full`` without a ``fields`` mask so text-part ``body.data``
        remains available. Gmail may also embed attachment-part ``body.data``
        in that same response. Those parts are not decoded as body or
        attachment content.
        """
        message_id = _validated_message_id(provider_message_id)
        payload = self._get_json(
            _message_url(message_id),
            params={"format": "full"},
            operation=_OPERATION_FETCH,
        )
        return normalize_gmail_message(payload)

    def list_attachments(self, provider_message_id: str) -> AttachmentMetadataPage:
        """Return MIME attachment metadata without requesting ``body.data``.

        Uses ``format=full`` so nested ``parts`` exist, plus a ``fields`` mask
        that omits ``body.data``. This is not ``users.messages.attachments.get``.
        """
        message_id = _validated_message_id(provider_message_id)
        payload = self._get_json(
            _message_url(message_id),
            params={"format": "full", "fields": _ATTACHMENT_METADATA_FIELDS},
            operation=_OPERATION_LIST_ATTACHMENTS,
        )
        items = list_gmail_attachment_metadata(payload)
        return AttachmentMetadataPage(items=items, truncated=False)

    def fetch_attachment_content(
        self,
        provider_message_id: str,
        provider_attachment_id: str,
    ) -> AttachmentContent:
        """Retrieve exactly one Gmail attachment via ``users.messages.attachments.get``.

        Revalidates metadata with the 18A fields mask (no ``body.data``) so
        the attachment id is bound to this message before the content GET.
        """
        message_id = _validated_message_id(provider_message_id)
        attachment_id = _validated_attachment_id(provider_attachment_id)
        metadata = _metadata_for_attachment(self.list_attachments(message_id).items, attachment_id)
        if metadata.reported_size > MAX_ATTACHMENT_CONTENT_BYTES:
            raise ConnectorAttachmentContentError()
        payload = self._get_json(
            _attachment_url(message_id, attachment_id),
            operation=_OPERATION_FETCH_ATTACHMENT,
        )
        if not isinstance(payload, dict):
            raise ConnectorAttachmentContentError()
        raw = payload.get("data")
        if not isinstance(raw, str) or not raw.strip():
            raise ConnectorAttachmentContentError()
        content = decode_gmail_base64url(raw.strip())
        if not content:
            raise ConnectorAttachmentContentError()
        if len(content) > MAX_ATTACHMENT_CONTENT_BYTES:
            raise ConnectorAttachmentContentError()
        returned_id = payload.get("attachmentId")
        if isinstance(returned_id, str) and returned_id.strip() and returned_id != attachment_id:
            raise ConnectorAttachmentContentError()
        return AttachmentContent(
            metadata=metadata,
            content=content,
            source_message_id=message_id,
            source_attachment_id=attachment_id,
        )

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        operation: str,
        has_cursor: bool = False,
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {resolve_access_token(self._access_token_provider)}",
            "Accept": "application/json",
        }
        try:
            response = self._http.get(
                url,
                params=params,
                headers=headers,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise ConnectorUnavailableError() from None
        except httpx.RequestError:
            raise ConnectorUnavailableError() from None
        _raise_for_status(response, operation=operation, has_cursor=has_cursor)
        try:
            payload = response.json()
        except ValueError:
            raise ConnectorUnavailableError() from None
        return payload


def _validated_message_id(provider_message_id: str) -> str:
    if not isinstance(provider_message_id, str):
        raise ConnectorMessageNotFoundError()
    message_id = provider_message_id.strip()
    if not message_id:
        raise ConnectorMessageNotFoundError()
    return message_id


def _validated_attachment_id(provider_attachment_id: str) -> str:
    if not isinstance(provider_attachment_id, str):
        raise ConnectorAttachmentNotFoundError()
    attachment_id = provider_attachment_id.strip()
    if not attachment_id:
        raise ConnectorAttachmentNotFoundError()
    return attachment_id


def _message_url(message_id: str) -> str:
    return f"{_LIST_URL}/{quote(message_id, safe='')}"


def _attachment_url(message_id: str, attachment_id: str) -> str:
    return f"{_message_url(message_id)}/attachments/{quote(attachment_id, safe='')}"


def _metadata_for_attachment(
    items: list[AttachmentMetadata],
    attachment_id: str,
) -> AttachmentMetadata:
    matches = [item for item in items if item.provider_attachment_id == attachment_id]
    if len(matches) != 1:
        raise ConnectorAttachmentNotFoundError()
    return matches[0]


def _raise_for_status(
    response: httpx.Response,
    *,
    operation: str,
    has_cursor: bool,
) -> None:
    status = response.status_code
    if status == 200:
        return
    if status == 401:
        raise ConnectorAuthenticationError() from None
    if status == 403:
        if _is_rate_limited_forbidden(response):
            raise ConnectorRateLimitError() from None
        raise ConnectorPermissionError() from None
    if status == 404:
        if operation == _OPERATION_FETCH_ATTACHMENT:
            raise ConnectorAttachmentNotFoundError() from None
        if operation in {_OPERATION_FETCH, _OPERATION_LIST_ATTACHMENTS}:
            raise ConnectorMessageNotFoundError() from None
        raise ConnectorUnavailableError() from None
    if status == 429:
        raise ConnectorRateLimitError() from None
    if status == 400 and operation == _OPERATION_LIST and has_cursor:
        raise ConnectorInvalidCursorError() from None
    if 500 <= status <= 599:
        raise ConnectorUnavailableError() from None
    raise ConnectorError("Connector request failed.") from None


def _is_rate_limited_forbidden(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    return gmail_rate_limit_reason(payload)
