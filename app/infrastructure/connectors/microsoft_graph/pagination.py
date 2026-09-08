"""Microsoft Graph list pagination token encoding.

Graph ``@odata.nextLink`` URLs stay inside this adapter. The connector
boundary exposes only an opaque continuation token that can reconstruct the
fixed ``/me/messages`` list query.
"""

from __future__ import annotations

from urllib.parse import ParseResult, parse_qs, quote, unquote, urlparse

from app.core.exceptions import ConnectorInvalidCursorError, ConnectorUnavailableError
from app.domain.interfaces import ConnectorMessageQuery

_GRAPH_HOST = "graph.microsoft.com"
_LIST_PATH = "/v1.0/me/messages"
_ALLOWED_PORTS = frozenset({None, 443})
_SKIPTOKEN_PREFIX = "st."
_SKIP_PREFIX = "sk."
# Base ``attachment`` properties only. Derived ``fileAttachment`` fields such as
# ``contentId`` / ``contentBytes`` are invalid on the collection ``$select``.
_ATTACHMENT_SELECT = "id,name,contentType,size,isInline"


def attachment_list_query_params() -> dict[str, str]:
    """Build the metadata-only Graph attachment list query.

    ``$select`` uses only base ``attachment`` properties. Derived fields
    (``contentId``, ``contentBytes``) and the ``@odata.type`` annotation must
    not appear in ``$select`` — Graph returns ``400 Bad Request``.
    """
    return {"$select": _ATTACHMENT_SELECT}


def attachment_pagination_params_from_next_link(
    next_link: str,
    provider_message_id: str,
) -> dict[str, str]:
    """Rebuild a safe attachment-list query from a Graph ``@odata.nextLink``.

    The nextLink host and path are validated. ``$select`` is always replaced
    with the metadata-only base-field list so a provider nextLink cannot
    reintroduce ``contentBytes``, ``contentId``, or ``@odata.type``.
    """
    parsed = _parsed_graph_attachment_list_url(next_link, provider_message_id)
    if parsed is None:
        raise ConnectorUnavailableError() from None
    params = parse_qs(parsed.query, keep_blank_values=False)
    rebuilt = attachment_list_query_params()
    skiptoken = _first_query_value(params.get("$skiptoken"))
    if skiptoken is not None:
        rebuilt["$skiptoken"] = skiptoken
        return rebuilt
    skip = _first_query_value(params.get("$skip"))
    if skip is not None:
        rebuilt["$skip"] = skip
        return rebuilt
    raise ConnectorUnavailableError() from None


def list_query_params(query: ConnectorMessageQuery) -> dict[str, str | int]:
    """Build the fixed Graph list query, including an opaque continuation token."""
    params: dict[str, str | int] = {"$top": query.limit, "$select": "id"}
    if query.cursor is not None:
        params.update(pagination_params_from_cursor(query.cursor))
    return params


def pagination_params_from_cursor(cursor: str) -> dict[str, str]:
    """Decode an opaque Graph list cursor into pagination query parameters.

    Provider hostnames and ``@odata.nextLink`` URLs are rejected before HTTP.
    """
    if _looks_like_url(cursor):
        raise ConnectorInvalidCursorError() from None
    if cursor.startswith(_SKIPTOKEN_PREFIX):
        token = unquote(cursor.removeprefix(_SKIPTOKEN_PREFIX))
        if not token.strip():
            raise ConnectorInvalidCursorError() from None
        return {"$skiptoken": token}
    if cursor.startswith(_SKIP_PREFIX):
        skip = unquote(cursor.removeprefix(_SKIP_PREFIX))
        if not skip.strip():
            raise ConnectorInvalidCursorError() from None
        return {"$skip": skip}
    raise ConnectorInvalidCursorError() from None


def opaque_cursor_from_next_link(next_link: str | None) -> str | None:
    """Extract an opaque continuation token from a Graph ``@odata.nextLink``.

    Unsafe or unusable provider nextLinks become connector unavailability
    rather than a public URL.
    """
    if next_link is None:
        return None
    parsed = _parsed_graph_list_url(next_link)
    if parsed is None:
        raise ConnectorUnavailableError() from None
    params = parse_qs(parsed.query, keep_blank_values=False)
    skiptoken = _first_query_value(params.get("$skiptoken"))
    if skiptoken is not None:
        return f"{_SKIPTOKEN_PREFIX}{quote(skiptoken, safe='')}"
    skip = _first_query_value(params.get("$skip"))
    if skip is not None:
        return f"{_SKIP_PREFIX}{quote(skip, safe='')}"
    raise ConnectorUnavailableError() from None


def _looks_like_url(value: str) -> bool:
    stripped = value.strip()
    lowered = stripped.lower()
    return "://" in stripped or lowered.startswith("//") or lowered.startswith("http")


def _parsed_graph_attachment_list_url(
    value: str,
    provider_message_id: str,
) -> ParseResult | None:
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https":
        return None
    if parsed.hostname is None or parsed.hostname.lower() != _GRAPH_HOST:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.port not in _ALLOWED_PORTS:
        return None
    if parsed.fragment:
        return None
    if parsed.params:
        return None
    expected = f"/v1.0/me/messages/{provider_message_id}/attachments"
    if unquote(parsed.path).rstrip("/") != expected:
        return None
    return parsed


def _parsed_graph_list_url(value: str) -> ParseResult | None:
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https":
        return None
    if parsed.hostname is None or parsed.hostname.lower() != _GRAPH_HOST:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.port not in _ALLOWED_PORTS:
        return None
    if parsed.fragment:
        return None
    if parsed.params:
        return None
    if parsed.path.rstrip("/") != _LIST_PATH:
        return None
    return parsed


def _first_query_value(values: list[str] | None) -> str | None:
    if not values:
        return None
    token = values[0]
    if not isinstance(token, str) or not token.strip():
        return None
    return token
