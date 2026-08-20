"""SQLAlchemy ORM models for user-associated persistence.

These types stay inside infrastructure. Domain and application code must use
repository interfaces instead.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

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

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
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
            "status IN ('active', 'disconnected')",
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
