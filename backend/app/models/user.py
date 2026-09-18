from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.automation import AutomationConfig, ConnectedAccount
    from app.models.email import EmailIntegration
    from app.models.notification import Notification
    from app.models.profile import CompanyPreference, JobPreference, UserProfile
    from app.models.resume import Resume


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=20), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped[UserProfile | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    job_preference: Mapped[JobPreference | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    company_preferences: Mapped[list[CompanyPreference]] = relationship(back_populates="user", cascade="all, delete-orphan")
    resumes: Mapped[list[Resume]] = relationship(back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[list[Application]] = relationship(back_populates="user", cascade="all, delete-orphan")
    automation_config: Mapped[AutomationConfig | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    email_integration: Mapped[EmailIntegration | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    connected_accounts: Mapped[list[ConnectedAccount]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list[Notification]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RefreshToken(UUIDMixin, Base):
    """Opaque refresh tokens, stored hashed. Rotated on every refresh."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_hash: Mapped[str | None] = mapped_column(String(128))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
