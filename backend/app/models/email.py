from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SCHEMA_MASTER, SCHEMA_TRANSACTION, Base, StandardColumnsMixin, UTCDateTime
from app.models.enums import EmailClassification, EmailProvider, IntegrationStatus

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.user import User


class EmailIntegration(StandardColumnsMixin, Base):
    """Gmail connection via OAuth. Only the *encrypted* OAuth token bundle is stored,
    never a password. Scopes are least-privilege (gmail.readonly)."""

    __tablename__ = "email_integrations"
    __table_args__ = {"schema": SCHEMA_MASTER}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), unique=True, nullable=False)
    provider: Mapped[EmailProvider] = mapped_column(Enum(EmailProvider, native_enum=False, length=20), default=EmailProvider.GMAIL, nullable=False)
    email_address: Mapped[str | None] = mapped_column(String(255))
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted JSON {token, refresh_token, expiry, ...}
    scopes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus, native_enum=False, length=20), default=IntegrationStatus.DISCONNECTED, nullable=False
    )
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_history_id: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    oauth_state: Mapped[str | None] = mapped_column(String(128))  # CSRF state for the in-flight OAuth flow

    user: Mapped[User] = relationship(back_populates="email_integration", foreign_keys=lambda: [EmailIntegration.user_id])


class EmailMessage(StandardColumnsMixin, Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "provider_message_id", name="uq_email_user_provider_msg"),
        # GET /emails is "this user's messages, newest first".
        Index("ix_email_messages_user_received_at", "user_id", "received_at"),
        {"schema": SCHEMA_TRANSACTION},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    integration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("master.email_integrations.id", ondelete="SET NULL"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transaction.applications.id", ondelete="SET NULL"), index=True)

    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(255))
    sender: Mapped[str] = mapped_column(String(500), nullable=False)
    sender_domain: Mapped[str | None] = mapped_column(String(255), index=True)
    recipient: Mapped[str | None] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)

    classification: Mapped[EmailClassification] = mapped_column(
        Enum(EmailClassification, native_enum=False, length=30), default=EmailClassification.OTHER, nullable=False, index=True
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    classified_by: Mapped[str | None] = mapped_column(String(20))  # RULES / AI / USER
    classification_reason: Mapped[str | None] = mapped_column(Text)
    matched_by: Mapped[str | None] = mapped_column(String(120))  # how it was linked: DOMAIN / COMPANY_NAME / JOB_TITLE / MANUAL
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # demo emails injected without Gmail
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # did this email move the application status
    raw_headers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    application: Mapped[Application | None] = relationship(back_populates="emails")
