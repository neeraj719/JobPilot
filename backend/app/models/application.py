from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDMixin
from app.models.enums import (
    Actor,
    AnswerSource,
    AnswerStatus,
    ApplicationEventType,
    ApplicationStatus,
    AutomationState,
    CompanyPriority,
    DocumentType,
    FieldType,
    JobSourceType,
    PauseReason,
)

if TYPE_CHECKING:
    from app.models.email import EmailMessage
    from app.models.interview import Interview
    from app.models.job import Job
    from app.models.resume import Resume
    from app.models.user import User


class Application(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),
        # The queue / list / dashboard all filter on (owner, status) and the daily
        # automation budget counts (owner, applied_at) inside a day window.
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_user_applied_at", "user_id", "applied_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    automation_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("automation_runs.id", ondelete="SET NULL"))

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=30), default=ApplicationStatus.DISCOVERED, nullable=False, index=True
    )
    priority: Mapped[CompanyPriority] = mapped_column(Enum(CompanyPriority, native_enum=False, length=10), default=CompanyPriority.P2, nullable=False)
    match_score: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[JobSourceType | None] = mapped_column(Enum(JobSourceType, native_enum=False, length=30))  # channel used to apply
    queue_position: Mapped[int | None] = mapped_column(Integer)

    # Automation bookkeeping (spec §28)
    automation_state: Mapped[AutomationState] = mapped_column(
        Enum(AutomationState, native_enum=False, length=20), default=AutomationState.IDLE, nullable=False
    )
    pause_reason: Mapped[PauseReason | None] = mapped_column(Enum(PauseReason, native_enum=False, length=40))
    pause_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    # Snapshot of the detected form + mapped values, shown in the Approval Center
    # {"url":..., "fields":[{key,label,selector,field_type,mapped_to,value,status,required}], "blockers":[...]}
    form_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    auto_submit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cover_letter: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    submitted_via: Mapped[str | None] = mapped_column(String(50))  # AUTOMATION / MANUAL / EXTERNAL
    external_application_id: Mapped[str | None] = mapped_column(String(255))
    external_url: Mapped[str | None] = mapped_column(String(1024))
    confirmation_message: Mapped[str | None] = mapped_column(Text)

    last_update_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_response_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_action: Mapped[str | None] = mapped_column(String(500))
    next_action_due: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    skipped_reason: Mapped[str | None] = mapped_column(String(500))

    user: Mapped[User] = relationship(back_populates="applications")
    job: Mapped[Job] = relationship(back_populates="applications", lazy="joined")
    resume: Mapped[Resume | None] = relationship()
    answers: Mapped[list[ApplicationAnswer]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="ApplicationAnswer.order")
    events: Mapped[list[ApplicationEvent]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.created_at")
    documents: Mapped[list[ApplicationDocument]] = relationship(back_populates="application", cascade="all, delete-orphan")
    emails: Mapped[list[EmailMessage]] = relationship(back_populates="application")
    interviews: Mapped[list[Interview]] = relationship(back_populates="application", cascade="all, delete-orphan")


class ApplicationAnswer(UUIDMixin, TimestampMixin, Base):
    """One answer to one form question. ``status=NEEDS_USER_INPUT`` means the engine
    refused to guess (missing facts) and the user must fill it in."""

    __tablename__ = "application_answers"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question_key: Mapped[str] = mapped_column(String(120), nullable=False)  # canonical key e.g. "phone", "expected_salary", "custom:why_us"
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    field_type: Mapped[FieldType] = mapped_column(Enum(FieldType, native_enum=False, length=20), default=FieldType.TEXT, nullable=False)
    options: Mapped[list[Any]] = mapped_column(JSON, default=list)  # for SELECT/RADIO
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    answer_source: Mapped[AnswerSource | None] = mapped_column(Enum(AnswerSource, native_enum=False, length=20))
    status: Mapped[AnswerStatus] = mapped_column(Enum(AnswerStatus, native_enum=False, length=20), default=AnswerStatus.NEEDS_USER_INPUT, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    rationale: Mapped[str | None] = mapped_column(Text)  # why the engine chose this answer
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # legal / eligibility / demographic
    field_selector: Mapped[str | None] = mapped_column(String(500))  # DOM selector when detected from a live form
    mapped_profile_field: Mapped[str | None] = mapped_column(String(120))  # e.g. "profile.phone"

    application: Mapped[Application] = relationship(back_populates="answers")


class ApplicationEvent(UUIDMixin, Base):
    __tablename__ = "application_events"
    #: Timelines are always read per application, oldest first.
    __table_args__ = (
        Index("ix_application_events_application_created", "application_id", "created_at"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type: Mapped[ApplicationEventType] = mapped_column(Enum(ApplicationEventType, native_enum=False, length=30), nullable=False)
    actor: Mapped[Actor] = mapped_column(Enum(Actor, native_enum=False, length=20), default=Actor.SYSTEM, nullable=False)
    from_status: Mapped[ApplicationStatus | None] = mapped_column(Enum(ApplicationStatus, native_enum=False, length=30))
    to_status: Mapped[ApplicationStatus | None] = mapped_column(Enum(ApplicationStatus, native_enum=False, length=30))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)

    application: Mapped[Application] = relationship(back_populates="events")


class ApplicationDocument(UUIDMixin, Base):
    __tablename__ = "application_documents"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, native_enum=False, length=20), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    content: Mapped[str | None] = mapped_column(Text)  # for generated cover letters
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    application: Mapped[Application] = relationship(back_populates="documents")
