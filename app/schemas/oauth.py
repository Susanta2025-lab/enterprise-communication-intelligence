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
    """Sanitized Gmail connection result. Omits durable identity, tokens, and locators."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    connector_account_id: UUID
    status: ConnectorAccountStatus
    granted_capabilities: tuple[CommunicationCapability, ...]


class MicrosoftAuthorizationStartResponse(BaseModel):
    """Browser redirect target. Omits state, PKCE, and credential locators."""

    model_config = ConfigDict(extra="forbid")

    authorization_url: str
    expires_at: datetime


class MicrosoftAuthorizationCallbackResponse(BaseModel):
    """Sanitized Microsoft connection result. Omits durable identity, tokens, and locators."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    connector_account_id: UUID
    status: ConnectorAccountStatus
    granted_capabilities: tuple[CommunicationCapability, ...]


class ConnectorAccountResponse(BaseModel):
    """Safe connector-account metadata. Omits durable identity, locators, and tokens."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    provider: str
    status: ConnectorAccountStatus
    granted_capabilities: tuple[CommunicationCapability, ...] | None
    created_at: datetime
    updated_at: datetime


class ConnectorAccountReauthorizeResponse(BaseModel):
    """Browser redirect target for reauthorization. Omits state, PKCE, and locators."""

    model_config = ConfigDict(extra="forbid")

    authorization_url: str
    expires_at: datetime
