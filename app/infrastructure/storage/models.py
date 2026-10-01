"""SQLAlchemy ORM models for user-associated persistence.

These types stay inside infrastructure. Domain and application code must use
repository interfaces instead.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeEngine

PORTABLE_JSON: TypeEngine[object] = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    """Return the current UTC time as an aware datetime."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for application persistence models."""


class User(Base):
    """Internal opaque user identity. No PII columns."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "application_role IN ('user', 'owner')",
            name="ck_users_application_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="user",
        server_default="user",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    identities: Mapped[list["ExternalIdentity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    connector_accounts: Mapped[list["ConnectorAccount"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    mailbox_authorization_sessions: Mapped[list["MailboxAuthorizationSession"]] = (
        relationship(
            back_populates="user",
            cascade="all, delete-orphan",
        )
    )
    workflow_actions: Mapped[list["WorkflowAction"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    attachment_analyses: Mapped[list["AttachmentAnalysisRow"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    business_contexts: Mapped[list["BusinessContextRow"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    business_context_communication_links: Mapped[
        list["BusinessContextCommunicationLinkRow"]
    ] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ExternalIdentity(Base):
    """OIDC issuer + subject mapping onto an internal user."""

    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "subject",
            name="uq_external_identities_issuer_subject",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    user: Mapped[User] = relationship(back_populates="identities")


class Analysis(Base):
    """User-owned analysis history row. Does not store raw communication body."""

    __tablename__ = "analyses"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    request_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_confidence: Mapped[float | None] = mapped_column(nullable=True)
    action_items: Mapped[list[dict[str, Any]]] = mapped_column(PORTABLE_JSON, nullable=False)
    draft_reply: Mapped[dict[str, Any] | None] = mapped_column(PORTABLE_JSON, nullable=True)
    connector_account_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    user: Mapped[User] = relationship(back_populates="analyses")


class ConnectorAccount(Base):
    """User-owned connector account. Stores an opaque credential reference only."""

    __tablename__ = "connector_accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "external_account_id",
            name="uq_connector_accounts_user_provider_external_account",
        ),
        CheckConstraint(
            "status IN ('active', 'disconnected', 'reauth_required')",
            name="ck_connector_accounts_status",
        ),
        Index(
            "ix_connector_accounts_user_id_created_at_id",
            "user_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    granted_capabilities: Mapped[list[str] | None] = mapped_column(
        PORTABLE_JSON,
        nullable=True,
    )
    display_identity: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    user: Mapped[User] = relationship(back_populates="connector_accounts")
    mailbox_authorization_sessions: Mapped[list["MailboxAuthorizationSession"]] = (
        relationship(
            back_populates="connector_account",
            passive_deletes=True,
        )
    )


class MailboxAuthorizationSession(Base):
    """Short-lived mailbox consent session. Stores state hash, never raw state."""

    __tablename__ = "mailbox_authorization_sessions"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('gmail', 'microsoft_graph')",
            name="ck_mailbox_authorization_sessions_provider",
        ),
        CheckConstraint(
            "purpose IN ('connect', 'reauthorize', 'connect_another')",
            name="ck_mailbox_authorization_sessions_purpose",
        ),
        CheckConstraint(
            "(purpose IN ('connect', 'connect_another') AND connector_account_id IS NULL) OR "
            "(purpose = 'reauthorize' AND connector_account_id IS NOT NULL)",
            name="ck_mailbox_authorization_sessions_purpose_account",
        ),
        UniqueConstraint(
            "state_hash",
            name="uq_mailbox_authorization_sessions_state_hash",
        ),
        Index("ix_mailbox_authorization_sessions_expires_at", "expires_at"),
        Index(
            "ix_mailbox_authorization_sessions_user_id_created_at",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    connector_account_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("connector_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    state_hash: Mapped[str] = mapped_column(Text, nullable=False)
    pkce_verifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_capabilities: Mapped[list[str]] = mapped_column(
        PORTABLE_JSON,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="mailbox_authorization_sessions")
    connector_account: Mapped[ConnectorAccount | None] = relationship(
        back_populates="mailbox_authorization_sessions",
    )


class WorkflowAction(Base):
    """User-owned workflow action. Snapshots proposed/approved reply text only."""

    __tablename__ = "workflow_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('reply')",
            name="ck_workflow_actions_action_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'executing', 'executed', 'failed')",
            name="ck_workflow_actions_status",
        ),
        CheckConstraint(
            "(connector_account_id IS NULL) = (provider_message_id IS NULL)",
            name="ck_workflow_actions_execution_target",
        ),
        Index(
            "ix_workflow_actions_user_id_created_at_id",
            "user_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_reply_body: Mapped[str] = mapped_column(Text, nullable=False)
    approved_reply_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    connector_account_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="workflow_actions")


class AttachmentAnalysisRow(Base):
    """User-owned attachment-analysis history. Structured result only.

    Distinct from ``analyses``. ``workflow_actions.analysis_id`` must not
    reference this table. Raw bytes, extracted document text, image bytes,
    prompts, tokens, and credentials are not stored.
    """

    __tablename__ = "attachment_analyses"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('pdf', 'docx', 'jpeg', 'png', 'txt', 'xlsx')",
            name="ck_attachment_analyses_kind",
        ),
        CheckConstraint(
            "extracted_content_status IN ('text', 'truncated_text', 'image')",
            name="ck_attachment_analyses_extracted_content_status",
        ),
        Index(
            "ix_attachment_analyses_user_id_created_at_id",
            "user_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_attachment_analyses_user_connector_message",
            "user_id",
            "connector_account_id",
            "provider_message_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    connector_account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_attachment_id: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False, default="")
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_content_status: Mapped[str] = mapped_column(Text, nullable=False)
    truncated: Mapped[bool] = mapped_column(nullable=False)
    warnings: Mapped[list[str]] = mapped_column(PORTABLE_JSON, nullable=False)
    reported_size: Mapped[int | None] = mapped_column(nullable=True)
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    character_count: Mapped[int | None] = mapped_column(nullable=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_confidence: Mapped[float | None] = mapped_column(nullable=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    action_items: Mapped[list[dict[str, Any]]] = mapped_column(
        PORTABLE_JSON,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    user: Mapped[User] = relationship(back_populates="attachment_analyses")

    tabular_result: Mapped[dict[str, Any] | None] = mapped_column(
        PORTABLE_JSON, nullable=True,
    )


class BusinessContextRow(Base):
    """User-owned BusinessContext. Flat organizational container only.

    Does not store communication bodies, attachment bytes, vendor ids, or
    tenancy columns. Provenance associations live in
    ``business_context_communication_links``.
    """

    __tablename__ = "business_contexts"
    __table_args__ = (
        CheckConstraint(
            "type IN ("
            "'matter', 'case', 'project', 'client', 'transaction', 'account', 'other'"
            ")",
            name="ck_business_contexts_type",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_business_contexts_status",
        ),
        CheckConstraint(
            "(status = 'active' AND archived_at IS NULL) OR "
            "(status = 'archived' AND archived_at IS NOT NULL)",
            name="ck_business_contexts_status_archived_at",
        ),
        Index(
            "ix_business_contexts_user_id_created_at_id",
            "user_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_business_contexts_user_id_status_updated_at",
            "user_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    user: Mapped[User] = relationship(back_populates="business_contexts")
    communication_links: Mapped[list["BusinessContextCommunicationLinkRow"]] = (
        relationship(
            back_populates="business_context",
            cascade="all, delete-orphan",
        )
    )


class BusinessContextCommunicationLinkRow(Base):
    """Authoritative BusinessContext ↔ provider-message provenance link.

    Identity is ``(connector_account_id, provider_message_id)`` scoped to a
    context. ``connector_account_id`` and ``analysis_id`` are provenance UUIDs
    without database foreign keys. Never stores message bodies or attachment
    bytes. Never cascades to analyses, workflows, or connector accounts.
    """

    __tablename__ = "business_context_communication_links"
    __table_args__ = (
        UniqueConstraint(
            "business_context_id",
            "connector_account_id",
            "provider_message_id",
            name="uq_bcc_links_context_connector_message",
        ),
        CheckConstraint(
            "association_source IN ('manual')",
            name="ck_business_context_communication_links_association_source",
        ),
        CheckConstraint(
            "length(trim(provider_message_id)) > 0",
            name="ck_business_context_communication_links_provider_message_id",
        ),
        Index(
            "ix_bcc_links_context_associated_at_id",
            "business_context_id",
            "associated_at",
            "id",
        ),
        Index(
            "ix_bcc_links_user_connector_message",
            "user_id",
            "connector_account_id",
            "provider_message_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_context_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("business_contexts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    connector_account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    associated_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    associated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    association_source: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(
        back_populates="business_context_communication_links"
    )
    business_context: Mapped[BusinessContextRow] = relationship(
        back_populates="communication_links"
    )


_WORK_ITEM_SQL_WHITESPACE = (
    " \t\n\r\v\f\x1c\x1d\x1e\x1f\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


def _tracking_sql_check(sql: str) -> str:
    for field in ("title", "description", "provider_message_id", "provider_attachment_id"):
        sql = sql.replace(f"trim({field})", f"trim({field}, '{_WORK_ITEM_SQL_WHITESPACE}')")
    return sql


class BusinessWorkItemRow(Base):
    """ADR-030 persistence row; repository owns every write."""

    __table__ = sa.Table(
        "business_work_items",
        Base.metadata,
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_context_id", sa.Uuid(), nullable=True),
        sa.Column("due_kind", sa.Text(), nullable=False, server_default="none"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_timezone", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("creation_origin", sa.Text(), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creation_key", sa.Text(), nullable=False),
        sa.Column("creation_request_hash", sa.Text(), nullable=False),
        sa.Column("origin_candidate_key", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('action','obligation')", name="ck_bwi_kind"),
        sa.CheckConstraint(
            "status IN ('open','in_progress','completed','cancelled')", name="ck_bwi_status"
        ),
        sa.CheckConstraint(
            _tracking_sql_check("length(trim(title)) BETWEEN 1 AND 200 AND title = trim(title)"),
            name="ck_bwi_title",
        ),
        sa.CheckConstraint(
            _tracking_sql_check(
                "description IS NULL OR (length(trim(description)) BETWEEN 1 AND 4000 AND "
                "description = trim(description))"
            ),
            name="ck_bwi_description",
        ),
        sa.CheckConstraint(
            "(due_kind = 'none' AND due_date IS NULL AND due_at IS NULL AND due_timezone "
            "IS NULL) OR (due_kind = 'date' AND due_date IS NOT NULL AND due_at IS NULL "
            "AND due_timezone IS NOT NULL AND length(trim(due_timezone)) BETWEEN 1 AND "
            "64) OR (due_kind = 'datetime' AND due_date IS NULL AND due_at IS NOT NULL "
            "AND due_timezone IS NOT NULL AND length(trim(due_timezone)) BETWEEN 1 AND "
            "64)",
            name="ck_bwi_due",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR (status <> "
            "'completed' AND completed_at IS NULL)",
            name="ck_bwi_completed",
        ),
        sa.CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL) OR (status <> "
            "'cancelled' AND cancelled_at IS NULL)",
            name="ck_bwi_cancelled",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at AND (completed_at IS NULL OR completed_at >= "
            "created_at) AND (cancelled_at IS NULL OR cancelled_at >= created_at) AND "
            "(archived_at IS NULL OR archived_at >= created_at)",
            name="ck_bwi_times",
        ),
        sa.CheckConstraint("version >= 1", name="ck_bwi_version"),
        sa.CheckConstraint(
            "(creation_origin = 'manual' AND confirmed_by_user_id IS NULL AND "
            "confirmed_at IS NULL AND origin_candidate_key IS NULL) OR (creation_origin "
            "= 'ai_confirmed' AND confirmed_by_user_id IS NOT NULL AND "
            "confirmed_by_user_id = user_id AND confirmed_at IS NOT NULL AND "
            "confirmed_at >= created_at AND origin_candidate_key IS NOT NULL)",
            name="ck_bwi_confirmation",
        ),
        sa.CheckConstraint(
            "length(creation_request_hash) = 64 AND "
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(repl"
            "ace(replace(replace(replace(replace(replace(replace(creation_request_hash, "
            "'0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', "
            "''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), "
            "'f', '') = ''",
            name="ck_bwi_request_hash",
        ),
        sa.CheckConstraint(
            "origin_candidate_key IS NULL OR (length(origin_candidate_key) = 64 AND "
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(repl"
            "ace(replace(replace(replace(replace(replace(replace(origin_candidate_key, "
            "'0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', "
            "''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), "
            "'f', '') = '')",
            name="ck_bwi_candidate_key",
        ),
        sa.CheckConstraint(
            "length(creation_key) BETWEEN 1 AND 128", name="ck_bwi_creation_key_length"
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_bwi_id_user"),
        sa.UniqueConstraint("user_id", "creation_key", name="uq_bwi_creation"),
        sa.UniqueConstraint("user_id", "origin_candidate_key", name="uq_bwi_candidate"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_context_id"], ["business_contexts.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "creation_key NOT GLOB '*[^A-Za-z0-9._~-]*'", name="ck_bwi_key_ascii_sqlite"
        ).ddl_if(dialect="sqlite"),
        sa.CheckConstraint("creation_key !~ '[^A-Za-z0-9._~-]'", name="ck_bwi_key_ascii_pg").ddl_if(
            dialect="postgresql"
        ),
        sa.Index("ix_bwi_owner_created", "user_id", "created_at", "id"),
        sa.Index("ix_bwi_owner_status_at", "user_id", "status", "due_at", "id"),
        sa.Index("ix_bwi_owner_status_date", "user_id", "status", "due_date", "id"),
        sa.Index("ix_bwi_owner_context", "user_id", "business_context_id", "created_at", "id"),
    )


class BusinessWorkItemSourceRow(Base):
    """ADR-030 persistence row; repository owns every write."""

    __table__ = sa.Table(
        "business_work_item_sources",
        Base.metadata,
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("attachment_analysis_id", sa.Uuid(), nullable=True),
        sa.Column("connector_account_id", sa.Uuid(), nullable=True),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("provider_attachment_id", sa.Text(), nullable=True),
        sa.Column("candidate_field", sa.Text(), nullable=True),
        sa.Column("candidate_index", sa.Integer(), nullable=True),
        sa.Column("candidate_digest", sa.Text(), nullable=True),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('communication','communication_analysis','attachment_analysis')",
            name="ck_bwis_kind",
        ),
        sa.CheckConstraint(
            "(connector_account_id IS NULL AND provider_message_id IS NULL) OR "
            "(connector_account_id IS NOT NULL AND provider_message_id IS NOT NULL)",
            name="ck_bwis_pair",
        ),
        sa.CheckConstraint(
            "(candidate_field IS NULL AND candidate_index IS NULL AND candidate_digest "
            "IS NULL) OR (candidate_field IS NOT NULL AND candidate_field IN "
            "('action_items','potential_action_mentions','potential_dates') AND "
            "candidate_index IS NOT NULL AND candidate_index >= 0 AND candidate_digest "
            "IS NOT NULL AND length(candidate_digest) = 64 AND "
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(repl"
            "ace(replace(replace(replace(replace(replace(replace(candidate_digest, '0', "
            "''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), "
            "'8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', "
            "'') = '')",
            name="ck_bwis_locator",
        ),
        sa.CheckConstraint(
            "(source_kind = 'communication' AND connector_account_id IS NOT NULL AND "
            "provider_message_id IS NOT NULL AND analysis_id IS NULL AND "
            "attachment_analysis_id IS NULL AND provider_attachment_id IS NULL AND "
            "candidate_field IS NULL) OR (source_kind = 'communication_analysis' AND "
            "analysis_id IS NOT NULL AND attachment_analysis_id IS NULL AND "
            "provider_attachment_id IS NULL AND (candidate_field IS NULL OR "
            "candidate_field = 'action_items')) OR (source_kind = 'attachment_analysis' "
            "AND analysis_id IS NULL AND attachment_analysis_id IS NOT NULL AND "
            "connector_account_id IS NOT NULL AND provider_message_id IS NOT NULL AND "
            "provider_attachment_id IS NOT NULL)",
            name="ck_bwis_reference",
        ),
        sa.CheckConstraint(
            "length(source_key) = 64 AND "
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(repl"
            "ace(replace(replace(replace(replace(replace(replace(source_key, '0', ''), "
            "'1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', "
            "''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = "
            "''",
            name="ck_bwis_key",
        ),
        sa.CheckConstraint(
            _tracking_sql_check(
                "provider_message_id IS NULL OR (length(trim(provider_message_id)) >= 1 AND "
                "length(provider_message_id) <= 2048)"
            ),
            name="ck_bwis_provider_message_id",
        ),
        sa.CheckConstraint(
            _tracking_sql_check(
                "provider_attachment_id IS NULL OR (length(trim(provider_attachment_id)) >= "
                "1 AND length(provider_attachment_id) <= 2048)"
            ),
            name="ck_bwis_provider_attachment_id",
        ),
        sa.UniqueConstraint("work_item_id", "source_key", name="uq_bwis_source"),
        sa.ForeignKeyConstraint(
            ["work_item_id", "user_id"],
            ["business_work_items.id", "business_work_items.user_id"],
            ondelete="CASCADE",
        ),
    )


class BusinessWorkItemEventRow(Base):
    """ADR-030 persistence row; repository owns every write."""

    __table__ = sa.Table(
        "business_work_item_events",
        Base.metadata,
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_version", sa.Integer(), nullable=False),
        sa.Column("event_ordinal", sa.Integer(), nullable=False),
        sa.Column("context_at_event_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
        sa.CheckConstraint(
            "event_type IN "
            "('created','edited','status_changed','archived','restored','context_associat"
            "ed','context_disassociated')",
            name="ck_bwie_type",
        ),
        sa.CheckConstraint("actor_user_id = user_id", name="ck_bwie_actor"),
        sa.CheckConstraint("item_version >= 1 AND event_ordinal >= 0", name="ck_bwie_version"),
        sa.UniqueConstraint("work_item_id", "item_version", "event_ordinal", name="uq_bwie_order"),
        sa.ForeignKeyConstraint(
            ["work_item_id", "user_id"],
            ["business_work_items.id", "business_work_items.user_id"],
            ondelete="CASCADE",
        ),
        sa.Index("ix_bwie_owner_item", "user_id", "work_item_id", "occurred_at", "id"),
        sa.Index("ix_bwie_owner_context", "user_id", "context_at_event_id", "occurred_at", "id"),
    )
