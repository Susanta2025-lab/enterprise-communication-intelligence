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

    ``ACTIVE`` means the credential is operational and the account is eligible
    subject to later capability checks. ``DISCONNECTED`` means the user
    intentionally disconnected. ``REAUTH_REQUIRED`` means the provider
    credential was later determined permanently unusable and user consent is
    required again. Phase 13A stores the state only; it does not automatically
    transition accounts from token-refresh failures.
    """

    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    REAUTH_REQUIRED = "reauth_required"


class CommunicationCapability(StrEnum):
    """Provider-neutral mailbox grant. Not a Google or Microsoft scope string."""

    MAIL_READ = "mail.read"
    MAIL_SEND = "mail.send"


class MailboxAuthorizationProvider(StrEnum):
    """Mailbox consent providers that may start an authorization session."""

    GMAIL = "gmail"
    MICROSOFT_GRAPH = "microsoft_graph"


class MailboxAuthorizationPurpose(StrEnum):
    """Why a mailbox authorization session exists. This is not ECI login."""

    CONNECT = "connect"
    REAUTHORIZE = "reauthorize"


class WorkflowActionType(StrEnum):
    """Kind of approval-gated workflow action.

    Distinct from ``ActionItem``, which is AI-extracted analysis output.
    Phase 11 supports ``REPLY`` only.
    """

    REPLY = "reply"


class WorkflowActionStatus(StrEnum):
    """Lifecycle of a ``WorkflowAction``.

    Terminal in Phase 11: ``REJECTED``, ``EXECUTED``, ``FAILED``.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"
