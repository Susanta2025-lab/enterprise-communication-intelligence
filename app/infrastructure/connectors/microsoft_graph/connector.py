"""Microsoft Graph REST v1.0 adapter that returns already-normalized messages."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.exceptions import (
    ConnectorAuthenticationError,
    ConnectorError,
    ConnectorInvalidCursorError,
    ConnectorMessageNotFoundError,
    ConnectorPermissionError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
)
from app.domain.interfaces import CommunicationConnector, ConnectorMessageQuery, MessagePage
from app.domain.models import CommunicationMessage
from app.infrastructure.connectors.common.auth import AccessTokenProvider, resolve_access_token
from app.infrastructure.connectors.microsoft_graph.normalization import (
    normalize_graph_message,
    parse_list_page,
)

_GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_HOST = "graph.microsoft.com"
_LIST_PATH = "/v1.0/me/messages"
_LIST_URL = f"{_GRAPH_API_BASE}/me/messages"
_FETCH_SELECT = (
    "id,conversationId,subject,body,from,sender,"
    "toRecipients,ccRecipients,bccRecipients,"
    "sentDateTime,receivedDateTime,categories"
)
_PREFER_TEXT_BODY = 'outlook.body-content-type="text"'
_ALLOWED_PORTS = frozenset({None, 443})
_OPERATION_LIST = "list"
_OPERATION_FETCH = "fetch"


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
        if query.cursor is not None:
            url = _validated_graph_next_link(query.cursor)
            params: dict[str, str | int] | None = None
            has_cursor = True
        else:
            url = _LIST_URL
            params = {"$top": query.limit, "$select": "id"}
            has_cursor = False
        payload = self._get_json(
            url,
            params=params,
            operation=_OPERATION_LIST,
            has_cursor=has_cursor,
        )
        message_ids, next_cursor = parse_list_page(payload)
        items = [self.fetch_message(message_id) for message_id in message_ids]
        return MessagePage(items=items, next_cursor=next_cursor)

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


def _message_url(message_id: str) -> str:
    return f"{_LIST_URL}/{quote(message_id, safe='')}"


def _validated_graph_next_link(cursor: str) -> str:
    """Accept only an https Graph v1.0 ``/me/messages`` collection URL.

    The original cursor string is returned unchanged so Graph continuation
    query values are not rewritten. Validation happens before HTTP so a
    malicious cursor cannot receive the bearer token.
    """
    try:
        parsed = urlparse(cursor)
    except ValueError:
        raise ConnectorInvalidCursorError() from None
    if parsed.scheme.lower() != "https":
        raise ConnectorInvalidCursorError() from None
    if parsed.hostname is None or parsed.hostname.lower() != _GRAPH_HOST:
        raise ConnectorInvalidCursorError() from None
    if parsed.username is not None or parsed.password is not None:
        raise ConnectorInvalidCursorError() from None
    if parsed.port not in _ALLOWED_PORTS:
        raise ConnectorInvalidCursorError() from None
    if parsed.fragment:
        raise ConnectorInvalidCursorError() from None
    if parsed.params:
        raise ConnectorInvalidCursorError() from None
    if parsed.path.rstrip("/") != _LIST_PATH:
        raise ConnectorInvalidCursorError() from None
    return cursor


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
        if operation == _OPERATION_FETCH:
            raise ConnectorMessageNotFoundError() from None
        raise ConnectorUnavailableError() from None
    if status == 429:
        raise ConnectorRateLimitError() from None
    if status == 400 and operation == _OPERATION_LIST and has_cursor:
        raise ConnectorInvalidCursorError() from None
    if 500 <= status <= 599:
        raise ConnectorUnavailableError() from None
    raise ConnectorError("Connector request failed.") from None
