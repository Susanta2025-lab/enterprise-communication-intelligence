"""Strongly typed enumerations for the communication domain."""

from enum import StrEnum


class SourceType(StrEnum):
    """Origin channel for a communication message."""

    EMAIL = "email"
    TEAMS = "teams"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    CRM = "crm"
    ERP = "erp"
    DOCUMENT = "document"
    CALENDAR = "calendar"
    OTHER = "other"


class PriorityLevel(StrEnum):
    """Business priority assigned to a communication or action item."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MessageCategory(StrEnum):
    """High-level classification of a communication's intent."""

    GENERAL = "general"
    REQUEST = "request"
    INCIDENT = "incident"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    INQUIRY = "inquiry"
    OTHER = "other"


class ConnectorAccountStatus(StrEnum):
    """Lifecycle of a user-owned connector account.

    Stored as portable text. This is not a PostgreSQL enum and is not SourceType.
    """

    ACTIVE = "active"
    DISCONNECTED = "disconnected"
