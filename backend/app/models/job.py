from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ApplicationType, CompanyPriority, EmploymentType, JobSourceType, WorkMode

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.company import Company
    from app.models.resume import Resume
    from app.models.user import User


class Job(UUIDMixin, TimestampMixin, Base):
    """A normalised job posting. The same posting seen on several platforms is ONE
    Job with several JobSource rows (see spec §17 duplicate detection)."""

    __tablename__ = "jobs"

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), index=True)
    normalized_location: Mapped[str | None] = mapped_column(String(255), index=True)
    work_mode: Mapped[WorkMode | None] = mapped_column(Enum(WorkMode, native_enum=False, length=10))
    employment_type: Mapped[EmploymentType | None] = mapped_column(Enum(EmploymentType, native_enum=False, length=20))
    salary_min: Mapped[int | None] = mapped_column(Integer)  # annual
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    experience_min: Mapped[float | None] = mapped_column(Float)
    experience_max: Mapped[float | None] = mapped_column(Float)
    required_skills: Mapped[list[Any]] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list[Any]] = mapped_column(JSON, default=list)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    canonical_url: Mapped[str | None] = mapped_column(String(1024))
    apply_url: Mapped[str | None] = mapped_column(String(1024))  # where the browser automation navigates
    application_type: Mapped[ApplicationType] = mapped_column(
        Enum(ApplicationType, native_enum=False, length=20), default=ApplicationType.UNKNOWN, nullable=False
    )
    dedupe_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # company+title+location fingerprint
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    company: Mapped[Company] = relationship(back_populates="jobs", lazy="joined")
    sources: Mapped[list[JobSource]] = relationship(back_populates="job", cascade="all, delete-orphan")
    matches: Mapped[list[JobMatch]] = relationship(back_populates="job", cascade="all, delete-orphan")
    applications: Mapped[list[Application]] = relationship(back_populates="job")


class JobSource(UUIDMixin, Base):
    """Where a Job was seen (LinkedIn, Naukri, company site...)."""

    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_job_source_external"),)

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    source: Mapped[JobSourceType] = mapped_column(Enum(JobSourceType, native_enum=False, length=30), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    apply_url: Mapped[str | None] = mapped_column(String(1024))
    application_type: Mapped[ApplicationType] = mapped_column(
        Enum(ApplicationType, native_enum=False, length=20), default=ApplicationType.UNKNOWN, nullable=False
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    job: Mapped[Job] = relationship(back_populates="sources")


class JobMatch(UUIDMixin, TimestampMixin, Base):
    """AI/heuristic match of a Job against a user's profile, resume and preferences."""

    __tablename__ = "job_matches"
    __table_args__ = (UniqueConstraint("job_id", "user_id", name="uq_job_match_job_user"),)

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))

    match_score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 0-100
    skill_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    experience_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    location_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    salary_score: Mapped[int | None] = mapped_column(Integer)  # None = unknown
    title_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    company_priority: Mapped[CompanyPriority | None] = mapped_column(Enum(CompanyPriority, native_enum=False, length=10))

    skill_match: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {matched:[], missing:[], total:int}
    experience_match: Mapped[str | None] = mapped_column(String(50))  # STRONG / GOOD / UNDER / OVER / UNKNOWN
    location_match: Mapped[str | None] = mapped_column(String(50))  # MATCH / REMOTE_OK / MISMATCH / UNKNOWN
    salary_match: Mapped[str | None] = mapped_column(String(50))  # ABOVE / WITHIN / BELOW / UNKNOWN
    missing_skills: Mapped[list[Any]] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(80))

    job: Mapped[Job] = relationship(back_populates="matches")
    user: Mapped[User] = relationship()
    resume: Mapped[Resume | None] = relationship()
