from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SCHEMA_AUDIT, Base, LifecycleMixin, UTCDateTime, UUIDMixin
from app.models.enums import Actor, AuditLevel


class AuditLog(UUIDMixin, LifecycleMixin, Base):
    """Every automated action is logged here (spec §27). Also records security
    relevant user actions (login, credential changes, integration connects)."""

    __tablename__ = "audit_logs"
    #: The activity feed and GET /audit both read "this user, newest first".
    __table_args__ = (Index("ix_audit_logs_user_created_at", "user_id", "created_at"), {"schema": SCHEMA_AUDIT})

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("master.users.id", ondelete="SET NULL"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transaction.applications.id", ondelete="SET NULL"), index=True)
    automation_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transaction.automation_runs.id", ondelete="SET NULL"), index=True)
    actor: Mapped[Actor] = mapped_column(Enum(Actor, native_enum=False, length=20), default=Actor.SYSTEM, nullable=False)
    level: Mapped[AuditLevel] = mapped_column(Enum(AuditLevel, native_enum=False, length=10), default=AuditLevel.INFO, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)  # e.g. "job.found", "application.paused"
    message: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
