"""Typed inputs/outputs for every AI task (CONTRACTS.md §6).

These models are the *contract* between the AI module and the rest of the app:
other modules never see a raw LLM response, only these validated objects.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AnswerSource, EmailClassification

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.job import Job

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- resume


class Links(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class ExperienceEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company: str | None = None
    title: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    # Resume-studio additions (optional; older JSON validates unchanged).
    location: str | None = None
    url: str | None = None


class EducationEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None


class ProjectEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    # Resume-studio additions (optional; older JSON validates unchanged).
    location: str | None = None
    url: str | None = None


class CertificationEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    issuer: str | None = None
    year: str | None = None

    @field_validator("year", mode="before")
    @classmethod
    def _year_to_str(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return str(v)


#: Every section a structured resume can show, in the default display order.
RESUME_SECTION_KEYS: tuple[str, ...] = (
    "summary",
    "skills",
    "experience",
    "projects",
    "education",
    "certifications",
    "achievements",
    "languages",
)


class ParsedResume(BaseModel):
    """Structured resume content. Every field is optional: the parser never invents data."""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    total_experience_years: float | None = None
    links: Links = Field(default_factory=Links)
    # Resume-studio additions (optional; defaults keep older JSON and its consumers unchanged).
    headline: str | None = None
    location: str | None = None
    achievements: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    #: Section keys in display order (``summary, skills, experience, projects, education,
    #: certifications, achievements, languages``); empty means the template's default order.
    section_order: list[str] = Field(default_factory=list)

    @field_validator("achievements", "languages", mode="before")
    @classmethod
    def _text_list(cls, v: Any) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            v = v.splitlines()
        return [str(item).strip() for item in v if item is not None and str(item).strip()]

    @field_validator("section_order", mode="before")
    @classmethod
    def _known_sections(cls, v: Any) -> list[str]:
        if not v:
            return []
        out: list[str] = []
        for item in v:
            key = str(item or "").strip().lower()
            if key in RESUME_SECTION_KEYS and key not in out:
                out.append(key)
        return out

    @field_validator("total_experience_years", mode="before")
    @classmethod
    def _sane_years(cls, v: Any) -> float | None:
        if v is None or v == "":
            return None
        try:
            years = float(v)
        except (TypeError, ValueError):
            return None
        if years < 0 or years > 60:
            return None
        return round(years, 1)


# --------------------------------------------------------------------------- job


class JobContext(BaseModel):
    """Everything a task needs to know about a job, without touching the ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    title: str = ""
    company_name: str = ""
    company_description: str | None = None
    location: str | None = None
    work_mode: str | None = None
    description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_min: float | None = None
    experience_max: float | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    source: str | None = None

    @classmethod
    def from_job(cls, job: "Job") -> "JobContext":
        """Build a context from a ``Job`` ORM row (company/sources accessed defensively)."""
        company_name = ""
        company_description: str | None = None
        try:
            company = getattr(job, "company", None)
            if company is not None:
                company_name = company.name or ""
                company_description = company.description
        except Exception:  # pragma: no cover - detached instance
            logger.debug("Could not load company for job %s", getattr(job, "id", None))

        source: str | None = None
        try:
            sources = list(getattr(job, "sources", []) or [])
            if sources:
                source = str(sources[0].source)
        except Exception:  # pragma: no cover - detached instance
            logger.debug("Could not load sources for job %s", getattr(job, "id", None))

        work_mode = getattr(job, "work_mode", None)
        return cls(
            id=str(job.id) if getattr(job, "id", None) else None,
            title=getattr(job, "title", "") or "",
            company_name=company_name,
            company_description=company_description,
            location=getattr(job, "location", None),
            work_mode=str(work_mode) if work_mode else None,
            description=getattr(job, "description", "") or "",
            required_skills=[str(s) for s in (getattr(job, "required_skills", None) or [])],
            preferred_skills=[str(s) for s in (getattr(job, "preferred_skills", None) or [])],
            experience_min=getattr(job, "experience_min", None),
            experience_max=getattr(job, "experience_max", None),
            salary_min=getattr(job, "salary_min", None),
            salary_max=getattr(job, "salary_max", None),
            salary_currency=getattr(job, "salary_currency", None),
            source=source,
        )

    @classmethod
    def coerce(cls, job: Any) -> "JobContext":
        """Accept a ``JobContext``, a ``Job`` row or a plain dict."""
        if isinstance(job, cls):
            return job
        if isinstance(job, dict):
            return cls.model_validate(job)
        if job is None:
            return cls()
        return cls.from_job(job)


# --------------------------------------------------------------------------- answers


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    answer: str | None = None
    source: AnswerSource = AnswerSource.DEFAULT
    confidence: float = 0.0
    rationale: str = ""
    needs_user_input: bool = False
    # Extra (non-contract) hints that make the review UI and the field mapper better.
    question_key: str | None = None
    is_sensitive: bool = False


# --------------------------------------------------------------------------- emails


class EmailClassificationResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    classification: EmailClassification = EmailClassification.OTHER
    confidence: float = 0.0
    reason: str = ""
    company_hint: str | None = None
    job_title_hint: str | None = None


# --------------------------------------------------------------------------- interviews


class InterviewPrep(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    technical: list[str] = Field(default_factory=list)
    behavioral: list[str] = Field(default_factory=list)
    company_specific: list[str] = Field(default_factory=list)
    job_specific: list[str] = Field(default_factory=list)
    resume_based: list[str] = Field(default_factory=list)


class MatchExplanation(BaseModel):
    """Envelope used on the wire for ``explain_match`` (the task returns the string)."""

    model_config = ConfigDict(from_attributes=True)

    explanation: str = ""


class CoverLetter(BaseModel):
    """Envelope used on the wire for ``generate_cover_letter``."""

    model_config = ConfigDict(from_attributes=True)

    cover_letter: str = ""


class PolishedRecommendation(BaseModel):
    """One reworded resume recommendation (``polish_resume_recommendations``).

    ``id`` must be one of the recommendation ids the caller sent; the task drops any
    other id. An empty ``detail`` keeps the deterministic wording.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    detail: str | None = None
    suggested_text: str | None = None


class PolishedRecommendations(BaseModel):
    """Envelope used on the wire for ``polish_resume_recommendations``."""

    model_config = ConfigDict(from_attributes=True)

    items: list[PolishedRecommendation] = Field(default_factory=list)


class AIStatus(BaseModel):
    provider: str
    model: str | None = None
    configured: bool = False
    #: What the signed-in user's calls resolve to (AI Model Settings); omitted when unknown.
    effective: dict[str, Any] | None = None


__all__ = [
    "AIStatus",
    "CertificationEntry",
    "CoverLetter",
    "EducationEntry",
    "EmailClassificationResult",
    "ExperienceEntry",
    "GeneratedAnswer",
    "InterviewPrep",
    "JobContext",
    "Links",
    "MatchExplanation",
    "ParsedResume",
    "PolishedRecommendation",
    "PolishedRecommendations",
    "ProjectEntry",
]
