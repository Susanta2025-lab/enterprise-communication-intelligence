"""Microsoft Graph REST write adapter for authorized reply actions.

This adapter implements ``CommunicationActionExecutor``. It does not fetch mail,
look up mailbox locators, or own OAuth. The caller injects ``httpx.Client``
and an on-demand ``AccessTokenProvider``.
"""

from __future__ import annotations

import time
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

_GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_PROVIDER = "microsoft_graph"
_UNAVAILABLE = "Communication action execution is currently unavailable."
_FAILED = "Communication action execution failed."


class MicrosoftGraphCommunicationActionExecutor(CommunicationActionExecutor):
    """Send an approved reply through Microsoft Graph's native reply operation.

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

    def execute(self, command: CommunicationActionExecution) -> None:
        """POST the approved reply snapshot to Graph ``/me/messages/{id}/reply``."""
        started_at = time.perf_counter()
        self._require_supported_command(command, started_at)
        token = self._current_access_token(command, started_at)
        try:
            response = self._http.post(
                _reply_url(command.provider_message_id),
                headers={"Authorization": f"Bearer {token}"},
                json={"comment": command.approved_reply_body},
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(command, started_at, unavailable, status_class="unavailable")
            raise unavailable from None
        except httpx.RequestError:
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(command, started_at, unavailable, status_class="unavailable")
            raise unavailable from None
        _raise_for_status(response, command, started_at)
        logger.info(
            "communication_action_executed",
            operation="execute",
            workflow_action_id=str(command.action_id),
            connector_account_id=str(command.connector_account_id),
            provider=_GRAPH_PROVIDER,
            duration_ms=elapsed_ms(started_at),
            status_class="accepted",
        )

    def _require_supported_command(
        self,
        command: CommunicationActionExecution,
        started_at: float,
    ) -> None:
        if command.provider != _GRAPH_PROVIDER:
            failed = CommunicationActionExecutionError(_FAILED)
            _log_failure(command, started_at, failed, status_class="rejected")
            raise failed
        if command.action_type is not WorkflowActionType.REPLY:
            failed = CommunicationActionExecutionError(_FAILED)
            _log_failure(command, started_at, failed, status_class="rejected")
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
            _log_failure(command, started_at, unavailable, status_class="unavailable")
            raise unavailable from None
        if not isinstance(token, str) or not token.strip():
            unavailable = ServiceUnavailableError(_UNAVAILABLE)
            _log_failure(command, started_at, unavailable, status_class="unavailable")
            raise unavailable
        return token.strip()


def _reply_url(provider_message_id: str) -> str:
    return f"{_GRAPH_API_BASE}/me/messages/{quote(provider_message_id, safe='')}/reply"


def _raise_for_status(
    response: httpx.Response,
    command: CommunicationActionExecution,
    started_at: float,
) -> None:
    status = response.status_code
    if status == 202:
        return
    if status == 408 or 500 <= status <= 599 or 200 <= status <= 299:
        unavailable = ServiceUnavailableError(_UNAVAILABLE)
        _log_failure(command, started_at, unavailable, status_class="unavailable")
        raise unavailable from None
    failed = CommunicationActionExecutionError(_FAILED)
    _log_failure(command, started_at, failed, status_class="rejected")
    raise failed from None


def _log_failure(
    command: CommunicationActionExecution,
    started_at: float,
    exc: Exception,
    *,
    status_class: str,
) -> None:
    logger.warning(
        "communication_action_execution_failed",
        operation="execute",
        workflow_action_id=str(command.action_id),
        connector_account_id=str(command.connector_account_id),
        provider=command.provider,
        duration_ms=elapsed_ms(started_at),
        error_class=error_class(exc),
        status_class=status_class,
    )
