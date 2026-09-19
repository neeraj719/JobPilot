"""Profile / job-preference schemas and the flattened ``CandidateContext`` (contract §3, §11)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmploymentType, WorkMode


class ProfileBase(BaseModel):
    """Every editable column of ``UserProfile``."""

    # Personal
    full_name: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=20)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)

    # Professional
    headline: str | None = Field(default=None, max_length=255)
    summary: str | None = None
    current_designation: str | None = Field(default=None, max_length=255)
    current_company: str | None = Field(default=None, max_length=255)
    years_of_experience: float | None = Field(default=None, ge=0, le=60)
    current_salary: int | None = Field(default=None, ge=0)
    previous_companies: list[Any] | None = None
    education: list[Any] | None = None
    skills: list[Any] | None = None
    technologies: list[Any] | None = None
    certifications: list[Any] | None = None
    projects: list[Any] | None = None
    achievements: list[Any] | None = None
    languages: list[Any] | None = None
    skill_experience: dict[str, Any] | None = None

    # Eligibility facts (never inferred by AI)
    work_authorization: dict[str, Any] | None = None
    requires_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None
    canonical_answers: dict[str, Any] | None = None


class ProfileUpdate(ProfileBase):
    """All fields optional; only the provided ones are written."""

    model_config = ConfigDict(extra="ignore")


class ProfileRead(ProfileBase):
    """``UserProfile`` (minus ids) plus derived completeness information."""

    model_config = ConfigDict(from_attributes=True)

    previous_companies: list[Any] = Field(default_factory=list)
    education: list[Any] = Field(default_factory=list)
    skills: list[Any] = Field(default_factory=list)
    technologies: list[Any] = Field(default_factory=list)
    certifications: list[Any] = Field(default_factory=list)
    projects: list[Any] = Field(default_factory=list)
    achievements: list[Any] = Field(default_factory=list)
    languages: list[Any] = Field(default_factory=list)
    skill_experience: dict[str, Any] = Field(default_factory=dict)
    work_authorization: dict[str, Any] = Field(default_factory=dict)
    canonical_answers: dict[str, Any] = Field(default_factory=dict)

    completeness: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class JobPreferenceBase(BaseModel):
    desired_titles: list[Any] | None = None
    min_salary: int | None = Field(default=None, ge=0)
    desired_salary: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=1, max_length=8)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    preferred_locations: list[Any] | None = None
    work_modes: list[WorkMode] | None = None
    employment_types: list[EmploymentType] | None = None
    experience_min: float | None = Field(default=None, ge=0, le=60)
    experience_max: float | None = Field(default=None, ge=0, le=60)
    preferred_technologies: list[Any] | None = None
    excluded_keywords: list[Any] | None = None
    min_match_score: int | None = Field(default=None, ge=0, le=100)
    only_posted_within_hours: int | None = Field(default=None, ge=1, le=24 * 90)


class JobPreferenceUpdate(JobPreferenceBase):
    model_config = ConfigDict(extra="ignore")


class JobPreferenceRead(JobPreferenceBase):
    model_config = ConfigDict(from_attributes=True)

    desired_titles: list[Any] = Field(default_factory=list)
    currency: str = "INR"
    preferred_locations: list[Any] = Field(default_factory=list)
    work_modes: list[Any] = Field(default_factory=list)
    employment_types: list[Any] = Field(default_factory=list)
    preferred_technologies: list[Any] = Field(default_factory=list)
    excluded_keywords: list[Any] = Field(default_factory=list)
    min_match_score: int = 75
    only_posted_within_hours: int | None = 24
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CandidateContext(BaseModel):
    """Flattened candidate view read by the answer engine, field mapper and matcher.

    ``flat`` only contains keys whose value actually exists, so consumers can test
    ``"expected_salary" in ctx.flat`` before answering a question and fall back to
    ``NEEDS_USER_INPUT`` instead of inventing a fact.

    ``resume`` is a ``resumes.schemas.ResumeRead`` when that module is available,
    otherwise a plain dict with the same key fields (or ``None`` when the user has no
    resume yet).
    """

    model_config = ConfigDict(from_attributes=True)

    profile: ProfileRead
    preferences: JobPreferenceRead
    resume: Any | None = None
    resume_path: str | None = None
    flat: dict[str, Any] = Field(default_factory=dict)

    # -- convenience accessors used by the answer engine / field mapper -------------
    def has(self, key: str) -> bool:
        return key in self.flat

    def value(self, key: str, default: Any = None) -> Any:
        return self.flat.get(key, default)

    def skill_years(self, skill: str) -> float | None:
        return self.flat.get(f"skill_years:{(skill or '').strip().lower()}")
