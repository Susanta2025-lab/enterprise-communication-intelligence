"""Owned connector-account OAuth reauthorization start.

Disconnect remains on ConnectorAccountService. This service only chooses the
account's stored provider and starts a REAUTHORIZE session.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.exceptions import ConnectorAccountConflictError
from app.application.services.connector_accounts import ConnectorAccountService
from app.application.services.gmail_mailbox_oauth import GmailMailboxOAuthService
from app.application.services.microsoft_mailbox_oauth import MicrosoftMailboxOAuthService
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import ConnectorAccountStatus, MailboxAuthorizationProvider


@dataclass(frozen=True, slots=True)
class ConnectorAccountReauthorizationStartResult:
    """Browser redirect target. Omits state, PKCE, and credential locators."""

    authorization_url: str
    expires_at: datetime


class ConnectorAccountOAuthService:
    """Start provider OAuth reauthorization for an owned connector account."""

    def __init__(
        self,
        accounts: ConnectorAccountService,
        gmail_oauth_factory: Callable[[], GmailMailboxOAuthService],
        microsoft_oauth_factory: Callable[[], MicrosoftMailboxOAuthService],
    ) -> None:
        self._accounts = accounts
        self._gmail_oauth_factory = gmail_oauth_factory
        self._microsoft_oauth_factory = microsoft_oauth_factory

    def start_reauthorization(
        self,
        principal: AuthenticatedPrincipal,
        connector_account_id: UUID,
    ) -> ConnectorAccountReauthorizationStartResult:
        """Return the provider authorization URL for an owned reauthorize session."""
        account = self._accounts.get_owned(principal, connector_account_id)
        if account.status is ConnectorAccountStatus.ACTIVE:
            raise ConnectorAccountConflictError()
        if account.status not in {
            ConnectorAccountStatus.DISCONNECTED,
            ConnectorAccountStatus.REAUTH_REQUIRED,
        }:
            raise ConnectorAccountConflictError()
        if account.provider == MailboxAuthorizationProvider.GMAIL.value:
            started = self._gmail_oauth_factory().start_reauthorization(
                principal,
                connector_account_id,
            )
        elif account.provider == MailboxAuthorizationProvider.MICROSOFT_GRAPH.value:
            started = self._microsoft_oauth_factory().start_reauthorization(
                principal,
                connector_account_id,
            )
        else:
            raise ConnectorAccountConflictError()
        return ConnectorAccountReauthorizationStartResult(
            authorization_url=started.authorization_url,
            expires_at=started.expires_at,
        )
