"""Resume API schemas (CONTRACTS.md §7).

``ParsedResume`` (and its nested entries) is owned by the AI module and re-exported
here so the frontend sees one shape for parsed resume data everywhere.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ResumeChangeSource, ResumeKind, ResumeParseStatus
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
    kind: ResumeKind = ResumeKind.UPLOADED
    template: str = "classic"
    source_resume_id: uuid.UUID | None = None
    archived_at: datetime | None = None
    draft_saved_at: datetime | None = None
    # File columns are null for resumes built in the editor (``kind`` CREATED / TAILORED).
    has_file: bool = False
    original_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
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
    #: Template id from ``GET /resumes/templates`` (``classic``, ``modern``, ``compact``).
    template: str | None = Field(default=None, min_length=1, max_length=40)


class ResumeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    version_number: int
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    change_source: ResumeChangeSource = ResumeChangeSource.USER
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


# --------------------------------------------------------------------------- resume studio

ExportFormat = Literal["pdf", "docx"]
DiffKind = Literal["added", "removed", "changed"]


class ResumeBuildRequest(BaseModel):
    """``POST /resumes/build`` — a resume made in the editor from structured data."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    target_role: str | None = Field(default=None, max_length=255)
    template: str | None = Field(default=None, max_length=40)
    parsed_data: ParsedResume = Field(default_factory=ParsedResume)
    set_default: bool = False


class ResumeImportText(BaseModel):
    """``POST /resumes/import/text`` — pasted resume text."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=30, max_length=60_000)
    name: str | None = Field(default=None, max_length=255)
    target_role: str | None = Field(default=None, max_length=255)
    template: str | None = Field(default=None, max_length=40)


class ParsedDataSave(ParsedResume):
    """``PUT /resumes/{id}/parsed-data`` body: the resume data plus an optional note.

    Older clients send a bare ``ParsedResume``; the two extra keys are optional.
    ``change_source`` may be USER (default) or AI (the user saved AI-made content);
    SYSTEM is reserved for the server (upload, re-parse, restore, duplicate).
    """

    note: str | None = Field(default=None, max_length=500)
    change_source: ResumeChangeSource | None = None

    @field_validator("change_source")
    @classmethod
    def _client_sources(cls, v: ResumeChangeSource | None) -> ResumeChangeSource | None:
        if v == ResumeChangeSource.SYSTEM:
            raise ValueError("change_source must be USER or AI")
        return v

    def resume_data(self) -> ParsedResume:
        return ParsedResume.model_validate(self.model_dump(mode="json", exclude={"note", "change_source"}))


class ResumeDraftRead(BaseModel):
    """The editor's autosaved, not yet versioned, data (``GET/PUT /resumes/{id}/draft``)."""

    resume_id: uuid.UUID
    draft_data: dict[str, Any] | None = None
    draft_saved_at: datetime | None = None
    #: The version the draft is based on: a newer version means the draft is stale.
    current_version: int = 1


class ResumeDuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)


class DiffField(BaseModel):
    """One changed field. ``path`` is a ``parsed_data`` path (``experience[0].bullets[2]``)."""

    path: str
    #: Human label of the section/entry ("Experience · Engineer at Acme").
    label: str | None = None
    before: Any = None
    after: Any = None
    kind: DiffKind


class DiffSummary(BaseModel):
    added: int = 0
    removed: int = 0
    changed: int = 0


class ResumeDiff(BaseModel):
    """Field-level diff (plan §4.2): bullets line by line, skills as added/removed sets."""

    fields: list[DiffField] = Field(default_factory=list)
    summary: DiffSummary = Field(default_factory=DiffSummary)
    #: One line for lists: "+2 skills, 1 bullet changed".
    description: str = ""
    before_label: str | None = None
    after_label: str | None = None


class HistoryItem(BaseModel):
    """One version in the cross-resume history (``GET /resumes/history``)."""

    id: uuid.UUID
    resume_id: uuid.UUID
    resume_name: str
    resume_kind: ResumeKind
    resume_archived: bool = False
    version_number: int
    is_current: bool = False
    note: str | None = None
    change_source: ResumeChangeSource
    change_summary: str
    created_at: datetime


class HistoryPage(BaseModel):
    items: list[HistoryItem] = Field(default_factory=list)
    next_cursor: str | None = None


class RecentResume(BaseModel):
    id: uuid.UUID
    name: str
    kind: ResumeKind
    target_role: str | None = None
    current_version: int
    has_draft: bool = False
    updated_at: datetime


class ResumeSummary(BaseModel):
    """Dashboard numbers for the Resume section (plan §4.6)."""

    total: int = 0
    archived: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)
    recently_edited: list[RecentResume] = Field(default_factory=list)
    drafts_pending: int = 0
    #: Resumes whose current version was made by AI and has not been edited since.
    ai_versions_to_review: int = 0
    default_resume_id: uuid.UUID | None = None


# --------------------------------------------------------------------------- writing help

WritingField = Literal["summary", "bullet", "headline", "achievement", "description"]


class BulletChecks(BaseModel):
    kept_details: bool = True
    no_new_numbers: bool = True
    no_new_claims: bool = True


class BulletCandidate(BaseModel):
    text: str
    #: ``rule`` (deterministic) or ``ai`` (model, then checked).
    source: Literal["rule", "ai"]
    checks: BulletChecks = Field(default_factory=BulletChecks)
    #: Holds a ``[...]`` placeholder the user must replace with a real result.
    has_placeholder: bool = False


class BulletSuggestions(BaseModel):
    original: str
    candidates: list[BulletCandidate] = Field(default_factory=list)
    #: Why nothing (or nothing more) is offered.
    note: str | None = None
    ai_used: bool = False


class RewriteBulletRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=3, max_length=600)
    role: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)


class AchievementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=3, max_length=600)


class ImproveTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    field: WritingField = "summary"


class ImprovedText(BaseModel):
    text: str
    changed: bool
    source: Literal["rule", "ai"] = "rule"
    #: Set when the model's version was refused (``invented_number``, ``invented_skill``…).
    reason: str | None = None


class DraftSummaryRequest(BaseModel):
    """Optional: the editor's unsaved data, so the draft uses what the user just typed."""

    model_config = ConfigDict(extra="forbid")

    parsed_data: ParsedResume | None = None


class SummaryDraft(BaseModel):
    text: str | None = None
    source: Literal["rule", "ai"] = "rule"
    reason: str | None = None


__all__ = [
    "AchievementRequest",
    "BulletCandidate",
    "BulletChecks",
    "BulletSuggestions",
    "DiffField",
    "DiffSummary",
    "DraftSummaryRequest",
    "ExportFormat",
    "HistoryItem",
    "HistoryPage",
    "ImproveTextRequest",
    "ImprovedText",
    "ParsedDataSave",
    "RecentResume",
    "ResumeBuildRequest",
    "ResumeDiff",
    "ResumeDraftRead",
    "ResumeDuplicateRequest",
    "ResumeImportText",
    "ResumeSummary",
    "RewriteBulletRequest",
    "SummaryDraft",
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
