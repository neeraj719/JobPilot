"""Resume API schemas (CONTRACTS.md §7).

``ParsedResume`` (and its nested entries) is owned by the AI module and re-exported
here so the frontend sees one shape for parsed resume data everywhere.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ResumeParseStatus
from app.modules.ai.schemas import (
    CertificationEntry,
    EducationEntry,
    ExperienceEntry,
    Links,
    ParsedResume,
    ProjectEntry,
)


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    target_role: str | None = None
    is_default: bool = False
    original_filename: str
    mime_type: str
    size_bytes: int
    parse_status: ResumeParseStatus
    parse_error: str | None = None
    parsed_at: datetime | None = None
    # ``ParsedResume``-shaped; ``{}`` until the resume has been parsed.
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    current_version: int = 1
    created_at: datetime
    updated_at: datetime

    @field_validator("parsed_data", mode="before")
    @classmethod
    def _default_parsed(cls, v: Any) -> dict[str, Any]:
        return v or {}


class ResumeUpdate(BaseModel):
    """PATCH body — every field optional."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    target_role: str | None = Field(default=None, max_length=255)
    is_default: bool | None = None


class ResumeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    version_number: int
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    created_at: datetime

    @field_validator("parsed_data", mode="before")
    @classmethod
    def _default_parsed(cls, v: Any) -> dict[str, Any]:
        return v or {}


# --------------------------------------------------------------------------- recommendations

RecommendationCategory = Literal[
    "MISSING_SKILL",
    "KEYWORD_GAP",
    "WEAK_SUMMARY",
    "EXPERIENCE_BULLETS",
    "TITLE_ALIGNMENT",
    "SECTION_MISSING",
    "LENGTH_AND_FORMAT",
    "STALE_CONTENT",
]
RecommendationPriority = Literal["HIGH", "MEDIUM", "LOW"]
#: ``add``: the resume shows related experience, list the skill if you have used it;
#: ``learn``: nothing related on the resume yet; ``list``: the resume text already
#: mentions it but the skills section (what matching reads) does not.
RecommendationAction = Literal["add", "learn", "list"]


class RecommendationEvidence(BaseModel):
    """What triggered a recommendation: a target job, a resume field or a keyword."""

    label: str
    job_id: str | None = None
    field: str | None = None


class Recommendation(BaseModel):
    id: str  # stable slug, e.g. "missing-skill-kubernetes"
    category: RecommendationCategory
    priority: RecommendationPriority
    title: str
    detail: str
    evidence: list[RecommendationEvidence] = Field(default_factory=list)
    suggested_text: str | None = None
    #: Points on the average match score across the target jobs if fully addressed.
    estimated_score_gain: float = 0.0
    action: RecommendationAction | None = None
    #: Canonical skills the recommendation is about (empty for non-skill advice).
    skills: list[str] = Field(default_factory=list)


class TitleCount(BaseModel):
    title: str
    count: int


class SkillDemand(BaseModel):
    skill: str
    count: int
    share: float  # 0-1, fraction of target jobs requiring it


class TargetSummary(BaseModel):
    jobs_analysed: int = 0
    top_titles: list[TitleCount] = Field(default_factory=list)
    top_skills: list[SkillDemand] = Field(default_factory=list)


class ScoreProjection(BaseModel):
    """Average match score over the target jobs, now and with every HIGH item addressed."""

    current_average: float = 0.0
    projected_average: float = 0.0
    delta: float = 0.0
    added_skills: list[str] = Field(default_factory=list)
    jobs_improved: int = 0


class VersionScore(BaseModel):
    version_number: int
    created_at: datetime | None = None
    note: str | None = None
    overall_score: int
    average_match_score: float
    is_current: bool = False


class ResumeRecommendations(BaseModel):
    resume_id: uuid.UUID
    resume_version: int
    generated_at: datetime
    overall_score: int  # 0-100 resume health
    target_summary: TargetSummary
    recommendations: list[Recommendation] = Field(default_factory=list)
    score_projection: ScoreProjection
    version_history: list[VersionScore] = Field(default_factory=list)
    #: False when the LLM wording step failed or returned nothing usable.
    ai_polished: bool = False
    ai_provider: str | None = None
    cached: bool = False


# --------------------------------------------------------------------------- apply suggestions

ChangeKind = Literal["ADD_SKILL", "REPLACE_SUMMARY", "REPLACE_BULLET"]


class ApplicableChange(BaseModel):
    """One edit to ``parsed_data`` that a recommendation can make, for the user to review."""

    #: The recommendation id; bullet changes add ``--bullet-N`` (one change per weak bullet).
    id: str
    recommendation_id: str
    kind: ChangeKind
    title: str
    before: str | None = None
    after: str
    #: Field path inside ``parsed_data``: ``skills``, ``summary``, ``experience[1].description``.
    target: str
    selected_by_default: bool = False
    requires_confirmation: bool = False
    confirmation_label: str | None = None
    #: ``after`` still holds a ``[...]`` placeholder the user must replace before applying.
    has_placeholders: bool = False
    #: Points on the average match score across the target jobs (skills only move it).
    estimated_score_gain: float = 0.0


class ManualItem(BaseModel):
    """Advice the app cannot apply for the user (it needs their own work or facts)."""

    recommendation_id: str
    title: str
    detail: str
    category: RecommendationCategory
    priority: RecommendationPriority


class ApplyPlan(BaseModel):
    resume_id: uuid.UUID
    #: Send back in :class:`ApplyRequest`; a newer version makes the plan stale (409).
    resume_version: int
    changes: list[ApplicableChange] = Field(default_factory=list)
    manual: list[ManualItem] = Field(default_factory=list)


class ApplyChangeRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    #: Edited text for REPLACE_SUMMARY / REPLACE_BULLET; ignored for ADD_SKILL.
    after: str | None = Field(default=None, max_length=4000)


class ApplyRequest(BaseModel):
    resume_version: int = Field(ge=1)
    changes: list[ApplyChangeRequest] = Field(min_length=1, max_length=100)


class AppliedChange(BaseModel):
    id: str
    kind: ChangeKind
    title: str


class SkippedChange(BaseModel):
    id: str
    reason: str


class ApplyResult(BaseModel):
    resume: ResumeRead
    applied: list[AppliedChange] = Field(default_factory=list)
    skipped: list[SkippedChange] = Field(default_factory=list)
    recommendations: ResumeRecommendations


__all__ = [
    "AppliedChange",
    "ApplicableChange",
    "ApplyChangeRequest",
    "ApplyPlan",
    "ApplyRequest",
    "ApplyResult",
    "CertificationEntry",
    "ManualItem",
    "SkippedChange",
    "EducationEntry",
    "ExperienceEntry",
    "Links",
    "ParsedResume",
    "ProjectEntry",
    "Recommendation",
    "RecommendationEvidence",
    "ResumeRead",
    "ResumeRecommendations",
    "ResumeUpdate",
    "ResumeVersionRead",
    "ScoreProjection",
    "SkillDemand",
    "TargetSummary",
    "TitleCount",
    "VersionScore",
]
