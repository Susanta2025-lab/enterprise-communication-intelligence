"""Microsoft Graph REST v1.0 adapter that returns already-normalized messages."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.core.exceptions import (
    ConnectorAttachmentContentError,
    ConnectorAttachmentMetadataError,
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
from app.infrastructure.connectors.microsoft_graph.normalization import (
    normalize_graph_attachment,
    normalize_graph_attachment_content,
    normalize_graph_message,
    parse_attachment_page,
    parse_list_page,
)
from app.infrastructure.connectors.microsoft_graph.pagination import (
    attachment_list_query_params,
    attachment_pagination_params_from_next_link,
    list_query_params,
    opaque_cursor_from_next_link,
)

_GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
_LIST_URL = f"{_GRAPH_API_BASE}/me/messages"
_FETCH_SELECT = (
    "id,conversationId,subject,body,from,sender,"
    "toRecipients,ccRecipients,bccRecipients,"
    "sentDateTime,receivedDateTime,categories"
)
_PREFER_TEXT_BODY = 'outlook.body-content-type="text"'
_OPERATION_LIST = "list"
_OPERATION_FETCH = "fetch"
_OPERATION_LIST_ATTACHMENTS = "list_attachments"
_OPERATION_FETCH_ATTACHMENT = "fetch_attachment"
_MAX_LISTED_ATTACHMENTS = 50
_ATTACHMENT_ITEM_SELECT = "id,name,contentType,size,isInline,contentId"
_ATTACHMENT_CONTENT_SELECT = f"{_ATTACHMENT_ITEM_SELECT},contentBytes"


class MicrosoftGraphCommunicationConnector(CommunicationConnector):
    """Read-only Microsoft Graph mail connector.

    HTTP and Graph JSON stay inside this adapter. The caller owns the
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
        return "microsoft_graph"

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        """Return one Graph collection page, fetching each listed id sequentially."""
        params = list_query_params(query)
        payload = self._get_json(
            _LIST_URL,
            params=params,
            operation=_OPERATION_LIST,
            has_cursor=query.cursor is not None,
        )
        message_ids, next_link = parse_list_page(payload)
        items = [self.fetch_message(message_id) for message_id in message_ids]
        return MessagePage(items=items, next_cursor=opaque_cursor_from_next_link(next_link))

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        """Return one normalized message for a Graph message resource id."""
        message_id = _validated_message_id(provider_message_id)
        payload = self._get_json(
            _message_url(message_id),
            params={"$select": _FETCH_SELECT},
            operation=_OPERATION_FETCH,
            prefer_text_body=True,
        )
        return normalize_graph_message(payload)

    def list_attachments(self, provider_message_id: str) -> AttachmentMetadataPage:
        """List file-attachment metadata without ``contentBytes`` or ``$value``."""
        message_id = _validated_message_id(provider_message_id)
        items: list[AttachmentMetadata] = []
        seen_ids: set[str] = set()
        params: dict[str, str | int] = attachment_list_query_params()
        url = _attachments_url(message_id)
        truncated = False
        while True:
            payload = self._get_json(
                url,
                params=params,
                operation=_OPERATION_LIST_ATTACHMENTS,
            )
            raw_items, next_link = parse_attachment_page(payload)
            for raw in raw_items:
                if len(items) >= _MAX_LISTED_ATTACHMENTS:
                    truncated = True
                    break
                metadata = normalize_graph_attachment(raw)
                if metadata is None:
                    continue
                if metadata.provider_attachment_id in seen_ids:
                    raise ConnectorAttachmentMetadataError()
                seen_ids.add(metadata.provider_attachment_id)
                items.append(metadata)
            else:
                if next_link is None:
                    break
                if len(items) >= _MAX_LISTED_ATTACHMENTS:
                    truncated = True
                    break
                params = attachment_pagination_params_from_next_link(next_link, message_id)
                continue
            break
        return AttachmentMetadataPage(items=items, truncated=truncated)

    def fetch_attachment_content(
        self,
        provider_message_id: str,
        provider_attachment_id: str,
    ) -> AttachmentContent:
        """Retrieve exactly one Graph file attachment, decoding ``contentBytes``.

        Uses the JSON attachment resource (not ``$value``) so returned
        ``@odata.type`` and id can be fail-closed before bytes are accepted.
        ``@odata.type`` is never placed in ``$select`` (Graph annotation).
        Metadata listing still omits ``contentBytes``.
        """
        message_id = _validated_message_id(provider_message_id)
        attachment_id = _validated_attachment_id(provider_attachment_id)
        metadata_payload = self._get_json(
            _attachment_item_url(message_id, attachment_id),
            params={"$select": _ATTACHMENT_ITEM_SELECT},
            operation=_OPERATION_FETCH_ATTACHMENT,
        )
        metadata = normalize_graph_attachment(metadata_payload)
        if metadata is None:
            raise ConnectorAttachmentNotFoundError()
        if metadata.provider_attachment_id != attachment_id:
            raise ConnectorAttachmentContentError()
        if metadata.reported_size > MAX_ATTACHMENT_CONTENT_BYTES:
            raise ConnectorAttachmentContentError()
        payload = self._get_json(
            _attachment_item_url(message_id, attachment_id),
            params={"$select": _ATTACHMENT_CONTENT_SELECT},
            operation=_OPERATION_FETCH_ATTACHMENT,
        )
        content = normalize_graph_attachment_content(
            payload,
            requested_attachment_id=attachment_id,
            source_message_id=message_id,
        )
        if len(content.content) > MAX_ATTACHMENT_CONTENT_BYTES:
            raise ConnectorAttachmentContentError()
        if len(content.content) > metadata.reported_size:
            raise ConnectorAttachmentContentError()
        return content

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        operation: str,
        has_cursor: bool = False,
        prefer_text_body: bool = False,
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {resolve_access_token(self._access_token_provider)}",
            "Accept": "application/json",
        }
        if prefer_text_body:
            headers["Prefer"] = _PREFER_TEXT_BODY
        request_kwargs: dict[str, Any] = {
            "headers": headers,
            "follow_redirects": False,
        }
        if params is not None:
            request_kwargs["params"] = params
        try:
            response = self._http.get(url, **request_kwargs)
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


def _attachments_url(message_id: str) -> str:
    return f"{_message_url(message_id)}/attachments"


def _attachment_item_url(message_id: str, attachment_id: str) -> str:
    return f"{_attachments_url(message_id)}/{quote(attachment_id, safe='')}"


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
