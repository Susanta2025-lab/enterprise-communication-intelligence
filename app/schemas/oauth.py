"""API schemas for mailbox OAuth start and callback responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CommunicationCapability, ConnectorAccountStatus


class GmailAuthorizationStartResponse(BaseModel):
    """Browser redirect target. Omits state, PKCE, and credential locators."""

    model_config = ConfigDict(extra="forbid")

    authorization_url: str
    expires_at: datetime


class GmailAuthorizationCallbackResponse(BaseModel):
    """Sanitized Gmail connection result. Omits tokens and credential locators."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    connector_account_id: UUID
    external_account_id: str
    status: ConnectorAccountStatus
    granted_capabilities: tuple[CommunicationCapability, ...]


class MicrosoftAuthorizationStartResponse(BaseModel):
    """Browser redirect target. Omits state, PKCE, and credential locators."""

    model_config = ConfigDict(extra="forbid")

    authorization_url: str
    expires_at: datetime


class MicrosoftAuthorizationCallbackResponse(BaseModel):
    """Sanitized Microsoft connection result. Omits tokens and credential locators."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    connector_account_id: UUID
    external_account_id: str
    status: ConnectorAccountStatus
    granted_capabilities: tuple[CommunicationCapability, ...]
