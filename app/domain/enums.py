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
    intentionally disconnected and ECI no longer possesses delegated
    credential material. ``REAUTH_REQUIRED`` means a permanent provider
    refresh failure was confirmed and user consent is required again. The
    locator may remain for controlled cleanup. Execution is rejected until
    reauthorization.
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
    """Why a mailbox authorization session exists. This is not ECI login.

    ``CONNECT`` is first-time mailbox authorization for a provider.
    ``REAUTHORIZE`` restores the exact same durable mailbox on an existing
    connector row. ``CONNECT_ANOTHER`` starts a distinct account-selection
    flow and persists a different provider account as its own row.
    """

    CONNECT = "connect"
    REAUTHORIZE = "reauthorize"
    CONNECT_ANOTHER = "connect_another"


class WorkflowActionType(StrEnum):
    """Kind of approval-gated workflow action.

    Distinct from ``ActionItem``, which is AI-extracted analysis output.
    Phase 11 supports ``REPLY`` only.
    """

    REPLY = "reply"


class AttachmentDisposition(StrEnum):
    """How a provider presented an attachment part. Not an authorization signal."""

    ATTACHMENT = "attachment"
    INLINE = "inline"
    UNKNOWN = "unknown"


class AttachmentKind(StrEnum):
    """Phase 18 allowlisted attachment kinds. Extension alone is never sufficient."""

    PDF = "pdf"
    DOCX = "docx"
    JPEG = "jpeg"
    PNG = "png"
    TXT = "txt"


class AttachmentScanVerdict(StrEnum):
    """Malware-scan outcome. Only CLEAN may proceed to later parse/AI slices.

    ``ERROR`` is an operational scanner failure. ``UNKNOWN`` is a completed
    but inconclusive scan. Both fail closed.
    """

    CLEAN = "clean"
    MALICIOUS = "malicious"
    UNKNOWN = "unknown"
    ERROR = "error"


class AttachmentExtractedContentStatus(StrEnum):
    """What extractable content a CLEAN attachment yielded for AI.

    Scanned or empty documents are errors, not a successful empty status.
    """

    TEXT = "text"
    TRUNCATED_TEXT = "truncated_text"
    IMAGE = "image"


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
