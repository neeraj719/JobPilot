from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDMixin
from app.models.enums import InterviewStatus, InterviewType

if TYPE_CHECKING:
    from app.models.application import Application


class Interview(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "interviews"
    #: "My upcoming interviews" is a (owner, scheduled_at) range scan.
    __table_args__ = (Index("ix_interviews_user_scheduled_at", "user_id", "scheduled_at"),)

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    interview_type: Mapped[InterviewType] = mapped_column(Enum(InterviewType, native_enum=False, length=20), default=InterviewType.OTHER, nullable=False)
    status: Mapped[InterviewStatus] = mapped_column(Enum(InterviewStatus, native_enum=False, length=20), default=InterviewStatus.SCHEDULED, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    location_or_link: Mapped[str | None] = mapped_column(String(1000))
    interviewer: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String(50))  # PASSED / FAILED / PENDING
    # AI-generated preparation: {technical:[], behavioral:[], company_specific:[], job_specific:[], resume_based:[], generated_at}
    prep_material: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_email_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_messages.id", ondelete="SET NULL"))

    application: Mapped[Application] = relationship(back_populates="interviews")
