"""Public connector-account collection schemas for the dashboard."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CommunicationCapability, ConnectorAccountStatus


class OwnedConnectorAccountItem(BaseModel):
    """Dashboard connector-account row. Omits durable identity and locator internals.

    ``display_identity`` is presentation-only and may be null. It is never the
    durable provider identity used for uniqueness or reconnect matching.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    provider: str
    status: ConnectorAccountStatus
    granted_capabilities: tuple[CommunicationCapability, ...] | None
    created_at: datetime
    updated_at: datetime
    display_identity: str | None = None


class OwnedConnectorAccountListResponse(BaseModel):
    """Bounded page of connector accounts owned by the authenticated caller."""

    model_config = ConfigDict(extra="forbid")

    items: list[OwnedConnectorAccountItem]
    limit: int
    offset: int
