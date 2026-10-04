from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SCHEMA_MASTER, Base, LifecycleMixin, TimestampMixin, UUIDMixin, soft_delete_where
from app.models.enums import CompanyPriority

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.user import User


class UserProfile(UUIDMixin, TimestampMixin, LifecycleMixin, Base):
    """Structured candidate profile. This is the single source of truth the
    application engine uses to answer form questions (never invented)."""

    __tablename__ = "user_profiles"
    __table_args__ = {"schema": SCHEMA_MASTER}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Personal
    full_name: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    portfolio_url: Mapped[str | None] = mapped_column(String(500))

    # Professional
    headline: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    current_designation: Mapped[str | None] = mapped_column(String(255))
    current_company: Mapped[str | None] = mapped_column(String(255))
    years_of_experience: Mapped[float | None] = mapped_column(Float)
    current_salary: Mapped[int | None] = mapped_column(Integer)  # annual, in preference currency
    previous_companies: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [{company, title, start, end, description}]
    education: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [{institution, degree, field, start, end, grade}]
    skills: Mapped[list[Any]] = mapped_column(JSON, default=list)  # ["React", ...]
    technologies: Mapped[list[Any]] = mapped_column(JSON, default=list)
    certifications: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [{name, issuer, year}]
    projects: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [{name, description, tech, url}]
    achievements: Mapped[list[Any]] = mapped_column(JSON, default=list)
    languages: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # Skill -> years mapping used for "Years of experience with React?" style questions
    skill_experience: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Eligibility facts (only ever answered from here; never inferred by AI)
    work_authorization: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"IN": true, "US": false}
    requires_sponsorship: Mapped[bool | None] = mapped_column(Boolean)
    willing_to_relocate: Mapped[bool | None] = mapped_column(Boolean)
    # Free-form canonical answers to recurring questions keyed by question_key
    canonical_answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="profile")


class JobPreference(UUIDMixin, TimestampMixin, LifecycleMixin, Base):
    __tablename__ = "job_preferences"
    __table_args__ = {"schema": SCHEMA_MASTER}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), unique=True, nullable=False)

    desired_titles: Mapped[list[Any]] = mapped_column(JSON, default=list)
    min_salary: Mapped[int | None] = mapped_column(Integer)  # annual
    desired_salary: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    preferred_locations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    work_modes: Mapped[list[Any]] = mapped_column(JSON, default=list)  # WorkMode values
    employment_types: Mapped[list[Any]] = mapped_column(JSON, default=list)  # EmploymentType values
    experience_min: Mapped[float | None] = mapped_column(Float)
    experience_max: Mapped[float | None] = mapped_column(Float)
    preferred_technologies: Mapped[list[Any]] = mapped_column(JSON, default=list)
    excluded_keywords: Mapped[list[Any]] = mapped_column(JSON, default=list)
    min_match_score: Mapped[int] = mapped_column(Integer, default=75, nullable=False)
    only_posted_within_hours: Mapped[int | None] = mapped_column(Integer, default=24)

    user: Mapped[User] = relationship(back_populates="job_preference")


class CompanyPreference(UUIDMixin, TimestampMixin, LifecycleMixin, Base):
    """User's priority list: P1/P2/P3 or AVOID. ``company_id`` is optional so a user
    can prioritise a company we have not yet seen a job from."""

    __tablename__ = "company_preferences"
    #: Partial unique: removing a company from the priority list tombstones the row, so
    #: adding the same company back has to be allowed to re-use the key.
    __table_args__ = (
        Index("uq_company_pref_user_name_active", "user_id", "normalized_name", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("master.companies.id", ondelete="SET NULL"))
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    priority: Mapped[CompanyPriority] = mapped_column(Enum(CompanyPriority, native_enum=False, length=10), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="company_preferences")
    company: Mapped[Company | None] = relationship()
