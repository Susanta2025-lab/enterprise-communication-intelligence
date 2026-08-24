"""Gmail REST write adapter for authorized reply actions.

This adapter implements ``CommunicationActionExecutor``. It does not fetch mail
bodies, look up mailbox locators, or own OAuth. The caller injects
``httpx.Client`` and an on-demand ``AccessTokenProvider``. Sender identity is
read from Gmail ``users.me.profile`` using the same access token.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from email.errors import MessageError
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import getaddresses
from urllib.parse import quote

import httpx

from app.core.exceptions import (
    CommunicationActionExecutionError,
    CommunicationCredentialReauthorizationRequiredError,
    ServiceUnavailableError,
)
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import WorkflowActionType
from app.domain.interfaces.communication_action_executor import (
    CommunicationActionExecution,
    CommunicationActionExecutor,
)
from app.domain.interfaces.communication_credential_resolver import AccessTokenProvider

logger = get_logger(__name__)

_GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
_PROFILE_URL = f"{_GMAIL_API_BASE}/users/me/profile"
_MESSAGES_URL = f"{_GMAIL_API_BASE}/users/me/messages"
_SEND_URL = f"{_MESSAGES_URL}/send"
_GMAIL_PROVIDER = "gmail"
_METADATA_HEADERS = ("From", "Reply-To", "Subject", "Message-ID", "References")
_UNAVAILABLE = "Communication action execution is currently unavailable."
_FAILED = "Communication action execution failed."


@dataclass(frozen=True)
class _ReplyPreparation:
    thread_id: str
    recipient: str
    subject: str
    message_id: str
    references: str


class GmailCommunicationActionExecutor(CommunicationActionExecutor):
    """Send an approved reply through Gmail ``users.messages.send``.

    HTTP, Gmail JSON, and RFC construction stay inside this adapter. The caller
    owns the ``httpx.Client`` lifecycle and supplies an in-memory access-token
    callable. The authenticated mailbox ``emailAddress`` is discovered at
    execute time and is not persisted.
    """

    def __init__(
        self,
        *,
        http_client: httpx.Client,
        access_token_provider: AccessTokenProvider,
    ) -> None:
        self._http = http_client
        self._access_token_provider = access_token_provider

    def execute(self, command: CommunicationActionExecution) -> None:
        """Fetch profile and original metadata, then POST the RFC reply to Gmail."""
        started_at = time.perf_counter()
        self._require_supported_command(command, started_at)
        token = self._current_access_token(command, started_at)
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        mailbox_address = self._fetch_mailbox_address(command, auth_headers, started_at)
        preparation = self._fetch_reply_preparation(command, auth_headers, started_at)
        raw = _encode_rfc_reply(
            mailbox_address=mailbox_address,
            recipient=preparation.recipient,
            subject=preparation.subject,
            message_id=preparation.message_id,
            references=preparation.references,
            body=command.approved_reply_body,
        )
        if raw is None:
            failed = CommunicationActionExecutionError(_FAILED)
            _log_failure(command, started_at, failed, operation="send", status_class="rejected")
            raise failed
        self._send_reply(
            command,
            auth_headers,
            raw=raw,
            thread_id=preparation.thread_id,
            started_at=started_at,
        )
        logger.info(
            "communication_action_executed",
            operation="send",
            workflow_action_id=str(command.action_id),
            connector_account_id=str(command.connector_account_id),
            provider=_GMAIL_PROVIDER,
            duration_ms=elapsed_ms(started_at),
            status_class="accepted",
        )

    def _require_supported_command(
        self,
        command: CommunicationActionExecution,
        started_at: float,
    ) -> None:
        if command.provider != _GMAIL_PROVIDER:
            failed = CommunicationActionExecutionError(_FAILED)
            _log_failure(command, started_at, failed, operation="execute", status_class="rejected")
            raise failed
        if command.action_type is not WorkflowActionType.REPLY:
            failed = CommunicationActionExecutionError(_FAILED)
            _log_failure(command, started_at, failed, operation="execute", status_class="rejected")
            raise failed

    def _current_access_token(
        self,
        command: CommunicationActionExecution,
        started_at: float,
    ) -> str:
        try:
            token = self._access_token_provider()
        except CommunicationCredentialReauthorizationRequiredError:
            raise
        except Exception:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="execute",
                status_class="unavailable",
            )
            raise unavailable from None
        if not isinstance(token, str) or not token.strip():
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="execute",
                status_class="unavailable",
            )
            raise unavailable
        return token.strip()

    def _fetch_mailbox_address(
        self,
        command: CommunicationActionExecution,
        auth_headers: dict[str, str],
        started_at: float,
    ) -> str:
        try:
            response = self._http.get(
                _PROFILE_URL,
                headers=auth_headers,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="profile_fetch",
                status_class="unavailable",
            )
            raise unavailable from None
        except httpx.RequestError:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="profile_fetch",
                status_class="unavailable",
            )
            raise unavailable from None
        _raise_for_status(response, command, started_at, operation="profile_fetch")
        try:
            payload = response.json()
        except ValueError:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="profile_fetch",
                status_class="unavailable",
            )
            raise unavailable from None
        mailbox_address = _parse_profile_mailbox(payload)
        if mailbox_address is None:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="profile_fetch",
                status_class="unavailable",
            )
            raise unavailable
        return mailbox_address

    def _fetch_reply_preparation(
        self,
        command: CommunicationActionExecution,
        auth_headers: dict[str, str],
        started_at: float,
    ) -> _ReplyPreparation:
        params: list[tuple[str, str]] = [("format", "metadata")]
        params.extend(("metadataHeaders", name) for name in _METADATA_HEADERS)
        try:
            response = self._http.get(
                _metadata_url(command.provider_message_id),
                params=params,
                headers=auth_headers,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="metadata_fetch",
                status_class="unavailable",
            )
            raise unavailable from None
        except httpx.RequestError:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="metadata_fetch",
                status_class="unavailable",
            )
            raise unavailable from None
        _raise_for_status(response, command, started_at, operation="metadata_fetch")
        try:
            payload = response.json()
        except ValueError:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="metadata_fetch",
                status_class="unavailable",
            )
            raise unavailable from None
        try:
            return _parse_reply_preparation(payload)
        except CommunicationActionExecutionError as failed:
            _log_failure(
                command,
                started_at,
                failed,
                operation="metadata_fetch",
                status_class="rejected",
            )
            raise
        except ServiceUnavailableError as unavailable:
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="metadata_fetch",
                status_class="unavailable",
            )
            raise

    def _send_reply(
        self,
        command: CommunicationActionExecution,
        auth_headers: dict[str, str],
        *,
        raw: str,
        thread_id: str,
        started_at: float,
    ) -> None:
        try:
            response = self._http.post(
                _SEND_URL,
                headers=auth_headers,
                json={"raw": raw, "threadId": thread_id},
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="send",
                status_class="unavailable",
            )
            raise unavailable from None
        except httpx.RequestError:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(
                command,
                started_at,
                unavailable,
                operation="send",
                status_class="unavailable",
            )
            raise unavailable from None
        _raise_for_status(response, command, started_at, operation="send")


def _metadata_url(provider_message_id: str) -> str:
    return f"{_MESSAGES_URL}/{quote(provider_message_id, safe='')}"


def _raise_for_status(
    response: httpx.Response,
    command: CommunicationActionExecution,
    started_at: float,
    *,
    operation: str,
) -> None:
    status = response.status_code
    if status == 200:
        return
    if status == 408 or 500 <= status <= 599 or 200 <= status <= 299:
        unavailable = ServiceUnavailableError(_UNAVAILABLE)
        _log_failure(
            command,
            started_at,
            unavailable,
            operation=operation,
            status_class="unavailable",
        )
        raise unavailable from None
    failed = CommunicationActionExecutionError(_FAILED)
    _log_failure(command, started_at, failed, operation=operation, status_class="rejected")
    raise failed from None


def _parse_profile_mailbox(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    email_address = payload.get("emailAddress")
    if not isinstance(email_address, str):
        return None
    return _parse_single_mailbox(email_address)


def _parse_reply_preparation(payload: object) -> _ReplyPreparation:
    if not isinstance(payload, dict):
        raise ServiceUnavailableError(_UNAVAILABLE)
    thread_id = payload.get("threadId")
    if thread_id is not None and not isinstance(thread_id, str):
        raise ServiceUnavailableError(_UNAVAILABLE)
    mime_payload = payload.get("payload")
    if mime_payload is None:
        raise CommunicationActionExecutionError(_FAILED)
    if not isinstance(mime_payload, dict):
        raise ServiceUnavailableError(_UNAVAILABLE)
    raw_headers = mime_payload.get("headers")
    if raw_headers is None:
        headers: dict[str, list[str]] = {}
    elif not isinstance(raw_headers, list):
        raise ServiceUnavailableError(_UNAVAILABLE)
    else:
        headers = _header_values(raw_headers)

    if thread_id is None or not _is_usable_thread_id(thread_id):
        raise CommunicationActionExecutionError(_FAILED)

    from_header = _unique_header(headers, "from", required=True)
    reply_to_header = _unique_header(headers, "reply-to", required=False)
    subject = _unique_header(headers, "subject", required=True)
    message_id = _unique_header(headers, "message-id", required=True)
    references_header = _unique_header(headers, "references", required=False)

    if reply_to_header is None:
        recipient = _parse_single_mailbox(from_header)
    else:
        recipient = _parse_single_mailbox(reply_to_header)
    if recipient is None:
        raise CommunicationActionExecutionError(_FAILED)
    if _has_unsafe_header_chars(subject) or not subject.strip():
        raise CommunicationActionExecutionError(_FAILED)
    if not _is_usable_message_id(message_id):
        raise CommunicationActionExecutionError(_FAILED)
    parent_id = message_id.strip()
    if references_header is not None and not _is_usable_references(references_header):
        raise CommunicationActionExecutionError(_FAILED)

    return _ReplyPreparation(
        thread_id=thread_id.strip(),
        recipient=recipient,
        subject=subject,
        message_id=parent_id,
        references=_outgoing_references(references_header, parent_id),
    )


def _header_values(raw_headers: list[object]) -> dict[str, list[str]]:
    collected: dict[str, list[str]] = {}
    for item in raw_headers:
        if not isinstance(item, dict):
            raise ServiceUnavailableError(_UNAVAILABLE)
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise ServiceUnavailableError(_UNAVAILABLE)
        collected.setdefault(name.lower(), []).append(value)
    return collected


def _unique_header(headers: dict[str, list[str]], name: str, *, required: bool) -> str | None:
    values = headers.get(name)
    if not values:
        if required:
            raise CommunicationActionExecutionError(_FAILED)
        return None
    if len(values) > 1:
        raise CommunicationActionExecutionError(_FAILED)
    value = values[0]
    if required and not value.strip():
        raise CommunicationActionExecutionError(_FAILED)
    if not required and not value.strip():
        if name == "reply-to":
            raise CommunicationActionExecutionError(_FAILED)
        return None
    return value


def _parse_single_mailbox(value: str) -> str | None:
    if not isinstance(value, str) or _has_unsafe_header_chars(value):
        return None
    stripped = value.strip()
    if not stripped or stripped.endswith(";"):
        return None
    mailboxes: list[str] = []
    for _display, address in getaddresses([stripped]):
        mailbox = address.strip()
        if not mailbox:
            continue
        if _has_unsafe_header_chars(mailbox):
            return None
        mailboxes.append(mailbox)
    if len(mailboxes) != 1:
        return None
    mailbox = mailboxes[0]
    if mailbox.count("@") != 1:
        return None
    local, domain = mailbox.split("@", 1)
    if not local or not domain:
        return None
    return mailbox


def _outgoing_references(existing: str | None, message_id: str) -> str:
    if existing is None or not existing.strip():
        return message_id
    refs = existing.strip()
    tokens = refs.split()
    if tokens and _canonical_message_id(tokens[-1]) == _canonical_message_id(message_id):
        return refs
    return f"{refs} {message_id}"


def _canonical_message_id(value: str) -> str:
    return value.strip().strip("<>")


def _is_usable_thread_id(value: str) -> bool:
    stripped = value.strip()
    if not stripped or _has_control_chars(value):
        return False
    return True


def _is_usable_message_id(value: str) -> bool:
    if _has_unsafe_header_chars(value):
        return False
    token = value.strip()
    if len(token) < 5 or not token.startswith("<") or not token.endswith(">"):
        return False
    inner = token[1:-1]
    if not inner or "<" in inner or ">" in inner:
        return False
    if any(ch.isspace() for ch in inner):
        return False
    if inner.count("@") != 1:
        return False
    local, domain = inner.split("@", 1)
    return bool(local) and bool(domain)


def _is_usable_references(value: str) -> bool:
    if _has_unsafe_header_chars(value):
        return False
    tokens = value.split()
    return bool(tokens) and all(_is_usable_message_id(token) for token in tokens)


def _has_unsafe_header_chars(value: str) -> bool:
    return "\r" in value or "\n" in value


def _has_control_chars(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def _encode_rfc_reply(
    *,
    mailbox_address: str,
    recipient: str,
    subject: str,
    message_id: str,
    references: str,
    body: str,
) -> str | None:
    try:
        message = EmailMessage(policy=SMTP)
        message["From"] = mailbox_address
        message["To"] = recipient
        message["Subject"] = subject
        message["In-Reply-To"] = message_id
        message["References"] = references
        message.set_content(body)
        return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    except (TypeError, ValueError, UnicodeError, MessageError):
        return None


def _log_failure(
    command: CommunicationActionExecution,
    started_at: float,
    exc: Exception,
    *,
    operation: str,
    status_class: str,
) -> None:
    logger.warning(
        "communication_action_execution_failed",
        operation=operation,
        workflow_action_id=str(command.action_id),
        connector_account_id=str(command.connector_account_id),
        provider=command.provider,
        duration_ms=elapsed_ms(started_at),
        error_class=error_class(exc),
        status_class=status_class,
    )
