from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDMixin
from app.models.enums import AutomationRunStatus, AutomationRunTrigger, BrowserSessionStatus, IntegrationStatus, JobSourceType

if TYPE_CHECKING:
    from app.models.user import User


class AutomationConfig(UUIDMixin, TimestampMixin, Base):
    """Per-user daily automation settings with hard safety rails (spec §14)."""

    __tablename__ = "automation_configs"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_time: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)  # HH:MM 24h
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    daily_application_limit: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    per_platform_limit: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"LINKEDIN": 10, "NAUKRI": 10}
    min_match_score: Mapped[int] = mapped_column(Integer, default=75, nullable=False)
    prioritize_priority_companies: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    only_posted_within_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    enabled_sources: Mapped[list[Any]] = mapped_column(JSON, default=list)  # JobSourceType values; empty = all connected
    delay_between_actions_seconds: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    retry_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Auto-submit is OFF by default; only allowed for sources listed in auto_submit_sources
    auto_submit_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_submit_sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    auto_generate_cover_letters: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_on_input_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(back_populates="automation_config")


class AutomationRun(UUIDMixin, Base):
    """One execution of the daily pipeline (scheduled or manual)."""

    __tablename__ = "automation_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    trigger: Mapped[AutomationRunTrigger] = mapped_column(Enum(AutomationRunTrigger, native_enum=False, length=20), nullable=False)
    status: Mapped[AutomationRunStatus] = mapped_column(
        Enum(AutomationRunStatus, native_enum=False, length=20), default=AutomationRunStatus.RUNNING, nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    current_step: Mapped[str | None] = mapped_column(String(80))
    # {"jobs_found":0,"jobs_new":0,"duplicates_merged":0,"jobs_analyzed":0,"jobs_matched":0,"high_match":0,
    #  "queued":0,"prepared":0,"submitted":0,"requires_user":0,"failed":0,"skipped_limit":0}
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # [{"step":"search","status":"SUCCESS","started_at":..,"finished_at":..,"message":..,"data":{}}]
    steps: Mapped[list[Any]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ConnectedAccount(UUIDMixin, TimestampMixin, Base):
    """A job platform account the user connected (spec §1.13). Credentials, if any,
    are stored Fernet-encrypted and never returned by the API."""

    __tablename__ = "connected_accounts"
    __table_args__ = (UniqueConstraint("user_id", "source", name="uq_connected_account_user_source"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    source: Mapped[JobSourceType] = mapped_column(Enum(JobSourceType, native_enum=False, length=30), nullable=False)
    account_identifier: Mapped[str | None] = mapped_column(String(255))  # email/username shown in UI
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus, native_enum=False, length=20), default=IntegrationStatus.CONNECTED, nullable=False
    )
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="connected_accounts")


class BrowserSession(UUIDMixin, TimestampMixin, Base):
    """Isolated Playwright browser context state per (user, source). Storage state
    (cookies/localStorage) is encrypted at rest."""

    __tablename__ = "browser_sessions"
    __table_args__ = (UniqueConstraint("user_id", "source", name="uq_browser_session_user_source"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    source: Mapped[JobSourceType] = mapped_column(Enum(JobSourceType, native_enum=False, length=30), nullable=False)
    encrypted_storage_state: Mapped[str | None] = mapped_column(Text)
    status: Mapped[BrowserSessionStatus] = mapped_column(
        Enum(BrowserSessionStatus, native_enum=False, length=20), default=BrowserSessionStatus.ACTIVE, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    user_agent: Mapped[str | None] = mapped_column(String(512))
