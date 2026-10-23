"""ATS optimizer API schemas (``/api/v1/ats``).

Every score in these shapes is an **estimate** of how a typical applicant tracking system
would read the resume against one job description; it is never the score of a specific
employer's ATS and never a promise of shortlisting (:data:`DISCLAIMER`).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    AtsAnalysisStatus,
    JdSource,
    JobTargetStatus,
    SuggestionKind,
    SuggestionStatus,
    WorkMode,
)
from app.modules.resumes.schemas import ResumeRead

DISCLAIMER = (
    "This is an estimated compatibility score computed by JobPilot from the resume and this job description. "
    "It is not the score of any employer's applicant tracking system, and it does not guarantee an interview "
    "or a job offer."
)

Confidence = Literal["high", "medium", "low"]


# --------------------------------------------------------------------------- job descriptions


class StructuredJD(BaseModel):
    """What a job description asks for. Every string occurs in the JD text it came from."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: WorkMode | None = None
    seniority: str | None = None
    years_min: float | None = None
    years_max: float | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    degree_required: bool = False
    keywords: list[str] = Field(default_factory=list)
    deadline: datetime | None = None
    #: True when the model re-classified the deterministic result (validated against the text).
    ai_polished: bool = False
    #: How the structure was derived ("No requirements section found: ...").
    notes: list[str] = Field(default_factory=list)


class JdParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200_000)
    title: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    #: Ask the configured model to refine the classification (slow on a local model).
    use_ai: bool = False


class BoardPostingRef(BaseModel):
    """One posting on a public board, as ``GET /ats/companies/lookup`` returns it."""

    model_config = ConfigDict(extra="forbid")

    vendor: Literal["GREENHOUSE", "LEVER", "ASHBY", "SMARTRECRUITERS"]
    token: str = Field(min_length=1, max_length=128)
    external_id: str = Field(min_length=1, max_length=300)


class JdFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, max_length=2048)
    board: BoardPostingRef | None = None
    use_ai: bool = False


class JdParseResult(BaseModel):
    source: JdSource
    confidence: Confidence
    title: str | None = None
    company: str | None = None
    location: str | None = None
    url: str | None = None
    text: str
    structured: StructuredJD
    warnings: list[str] = Field(default_factory=list)


class OpenRole(BaseModel):
    title: str
    location: str | None = None
    url: str | None = None
    external_id: str
    vendor: str
    token: str
    work_mode: WorkMode | None = None
    posted_at: datetime | None = None


class LookupCompany(BaseModel):
    id: uuid.UUID | None = None
    name: str
    ats_type: str | None = None
    board_url: str | None = None
    token: str | None = None


class CompanyLookupResult(BaseModel):
    query: str
    role: str | None = None
    company: LookupCompany | None = None
    #: KNOWN (registry / bundled list), DETECTED (looked up live) or NONE.
    method: Literal["REGISTRY", "KNOWN", "DETECTED", "NONE"] = "NONE"
    supported: bool = False
    total_open: int = 0
    open_roles: list[OpenRole] = Field(default_factory=list)
    #: Roles whose title matches ``role``: the user picks one; nothing is guessed.
    matching_roles: list[OpenRole] = Field(default_factory=list)
    message: str


# --------------------------------------------------------------------------- methodology


class MethodologyCategory(BaseModel):
    key: str
    label: str
    weight: float
    description: str


class Methodology(BaseModel):
    version: str
    categories: list[MethodologyCategory]
    weight_bounds: dict[str, float]
    disclaimer: str = DISCLAIMER
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- analyses


class JdInput(BaseModel):
    """Exactly one of ``text``, ``snapshot_id``, ``job_target_id`` or ``job_id``."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=200_000)
    title: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=2048)
    source: JdSource | None = None
    #: From ``/ats/jd/parse``; re-validated against ``text`` (anything not in it is dropped).
    structured: StructuredJD | None = None
    snapshot_id: uuid.UUID | None = None
    job_target_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None


class AnalysisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_id: uuid.UUID
    jd: JdInput
    weights: dict[str, float] | None = None


class CategoryScore(BaseModel):
    key: str
    label: str
    score: int | None = None
    weight: float
    applicable: bool = True
    evidence: list[str] = Field(default_factory=list)


class KeywordHit(BaseModel):
    keyword: str
    kind: Literal["skill", "keyword", "title"]
    required: bool | None = None
    where: list[str] = Field(default_factory=list)


class KeywordMiss(BaseModel):
    keyword: str
    kind: Literal["skill", "keyword", "title"]
    required: bool | None = None
    #: Where it would fit, when the candidate's own material supports it ("skills", "Experience at Acme").
    where_it_fits: str | None = None
    #: The resume text or the profile shows the candidate has it (safe to add); else it needs confirmation.
    evidenced: bool = False


class WeakItem(BaseModel):
    path: str
    text: str
    reason: str


class ParseRisk(BaseModel):
    code: str
    message: str
    severity: Literal["high", "medium", "low"] = "medium"


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    kind: SuggestionKind
    title: str
    rationale: str = ""
    target_path: str | None = None
    before: str | None = None
    after: str | None = None
    safe: bool = False
    requires_confirmation: bool = False
    confirmation_label: str | None = None
    estimated_gain: float = 0.0
    status: SuggestionStatus
    applied_version: int | None = None
    checks: dict[str, Any] = Field(default_factory=dict)

    @field_validator("checks", mode="before")
    @classmethod
    def _checks(cls, v: Any) -> dict[str, Any]:
        return v or {}


class SnapshotSummary(BaseModel):
    id: uuid.UUID | None = None
    title: str | None = None
    company: str | None = None
    source: JdSource | None = None
    url: str | None = None
    created_at: datetime | None = None


class AnalysisRead(BaseModel):
    id: uuid.UUID
    resume_id: uuid.UUID
    resume_name: str | None = None
    resume_version: int
    #: False once the resume has a newer version than the one analysed.
    is_current: bool = True
    job_target_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None
    previous_analysis_id: uuid.UUID | None = None
    previous_score: int | None = None
    status: AtsAnalysisStatus
    progress: int = 0
    error: str | None = None
    overall_score: int | None = None
    category_scores: list[CategoryScore] = Field(default_factory=list)
    matched_keywords: list[KeywordHit] = Field(default_factory=list)
    missing_keywords: list[KeywordMiss] = Field(default_factory=list)
    weak_items: list[WeakItem] = Field(default_factory=list)
    parse_risks: list[ParseRisk] = Field(default_factory=list)
    methodology_version: str
    weights: dict[str, float] = Field(default_factory=dict)
    ai_provider: str | None = None
    ai_model: str | None = None
    duration_ms: int | None = None
    completed_at: datetime | None = None
    created_at: datetime
    jd: SnapshotSummary = Field(default_factory=SnapshotSummary)
    suggestions: list[SuggestionRead] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


class AnalysisListItem(BaseModel):
    id: uuid.UUID
    resume_id: uuid.UUID
    resume_name: str | None = None
    resume_version: int
    job_target_id: uuid.UUID | None = None
    status: AtsAnalysisStatus
    overall_score: int | None = None
    jd_title: str | None = None
    jd_company: str | None = None
    created_at: datetime


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    #: Edited text per suggestion id (summary, bullet, keyword context). Edited = the user's own words.
    edits: dict[uuid.UUID, str] = Field(default_factory=dict)

    @field_validator("edits")
    @classmethod
    def _edit_length(cls, v: dict[uuid.UUID, str]) -> dict[uuid.UUID, str]:
        for text in v.values():
            if len(text) > 4000:
                raise ValueError("Edited text is limited to 4000 characters")
        return v


class IgnoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    #: ``false`` puts ignored suggestions back to PROPOSED.
    ignore: bool = True


class AppliedItem(BaseModel):
    id: uuid.UUID
    kind: SuggestionKind
    title: str
    edited: bool = False


class SkippedItem(BaseModel):
    id: uuid.UUID
    reason: str


class Explanation(BaseModel):
    suggestion_id: uuid.UUID | None = None
    what: str
    why: str
    evidence: list[str] = Field(default_factory=list)
    source: Literal["AI", "USER", "SYSTEM"] = "AI"


class ApplyResult(BaseModel):
    resume: ResumeRead
    analysis: AnalysisRead
    previous_analysis_id: uuid.UUID
    previous_score: int | None = None
    applied: list[AppliedItem] = Field(default_factory=list)
    skipped: list[SkippedItem] = Field(default_factory=list)
    #: The version that held the resume before this apply (Undo restores it as a new version).
    restorable_version: int | None = None


class AutoOptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["new_resume", "new_version"] = "new_resume"
    name: str | None = Field(default=None, max_length=255)


class AutoOptimizeResult(BaseModel):
    mode: Literal["new_resume", "new_version"]
    resume: ResumeRead
    source_resume_id: uuid.UUID
    analysis: AnalysisRead
    previous_score: int | None = None
    applied: list[AppliedItem] = Field(default_factory=list)
    skipped: list[SkippedItem] = Field(default_factory=list)
    explanations: list[Explanation] = Field(default_factory=list)


class UndoResult(BaseModel):
    resume: ResumeRead
    analysis: AnalysisRead
    restored_version: int


# --------------------------------------------------------------------------- job targets


class SnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["PASTED", "URL", "BOARD"] = "PASTED"
    text: str | None = Field(default=None, max_length=200_000)
    url: str | None = Field(default=None, max_length=2048)
    board: BoardPostingRef | None = None
    title: str | None = Field(default=None, max_length=255)
    structured: StructuredJD | None = None
    use_ai: bool = False


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_target_id: uuid.UUID | None = None
    source: JdSource
    url: str | None = None
    fetched_at: datetime | None = None
    title: str | None = None
    company: str | None = None
    raw_text: str = ""
    structured: StructuredJD
    text_sha256: str
    changed_from_previous: bool = False
    changes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("structured", mode="before")
    @classmethod
    def _structured(cls, v: Any) -> Any:
        return v or {}

    @field_validator("changes", mode="before")
    @classmethod
    def _changes(cls, v: Any) -> dict[str, Any]:
        return v or {}


class TargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str | None = Field(default=None, max_length=255)
    role_title: str | None = Field(default=None, max_length=255)
    job_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=255)
    work_mode: WorkMode | None = None
    required_skills: list[str] | None = Field(default=None, max_length=60)
    deadline: datetime | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    follow_up_at: datetime | None = None
    source_resume_id: uuid.UUID | None = None
    #: Created from a discovered job: title, company and description are copied into the first snapshot.
    job_id: uuid.UUID | None = None
    status: JobTargetStatus = JobTargetStatus.SAVED
    #: Optional first JD snapshot (pasted text, a posting URL or a board posting).
    jd: SnapshotCreate | None = None
    #: "Save as job target" from the optimizer: reuse that JD snapshot (and link that analysis).
    snapshot_id: uuid.UUID | None = None
    analysis_id: uuid.UUID | None = None


class TargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    role_title: str | None = Field(default=None, min_length=1, max_length=255)
    job_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=255)
    work_mode: WorkMode | None = None
    deadline: datetime | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    follow_up_at: datetime | None = None
    source_resume_id: uuid.UUID | None = None
    status: JobTargetStatus | None = None
    #: Link the JobPilot application this target was submitted through (your own, read only).
    application_id: uuid.UUID | None = None


class ResumeRef(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    current_version: int
    archived: bool = False


class TargetRead(BaseModel):
    id: uuid.UUID
    company_name: str
    company_id: uuid.UUID | None = None
    role_title: str
    job_url: str | None = None
    location: str | None = None
    work_mode: WorkMode | None = None
    required_skills: list[str] = Field(default_factory=list)
    deadline: datetime | None = None
    status: JobTargetStatus
    notes: str | None = None
    follow_up_at: datetime | None = None
    source_resume: ResumeRef | None = None
    tailored_resume: ResumeRef | None = None
    tailored_resume_version: int | None = None
    submitted_resume_version: int | None = None
    application_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    latest_snapshot_id: uuid.UUID | None = None
    last_analysis_id: uuid.UUID | None = None
    last_score: int | None = None
    last_analyzed_at: datetime | None = None
    missing_requirements: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ActivityItem(BaseModel):
    at: datetime
    kind: Literal["snapshot", "analysis", "status", "tailored", "note", "created", "applied"]
    message: str
    ref_id: uuid.UUID | None = None


class TargetDetail(TargetRead):
    latest_snapshot: SnapshotRead | None = None
    snapshots: list[SnapshotRead] = Field(default_factory=list)
    last_analysis: AnalysisRead | None = None
    activity: list[ActivityItem] = Field(default_factory=list)


class TailorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_resume_id: uuid.UUID | None = None
    name: str | None = Field(default=None, max_length=255)


class TailorResult(BaseModel):
    target: TargetRead
    resume: ResumeRead
    analysis: AnalysisRead
    source_analysis_id: uuid.UUID
    source_score: int | None = None
    explanations: list[Explanation] = Field(default_factory=list)


class FieldChange(BaseModel):
    path: str
    before: Any = None
    after: Any = None
    kind: Literal["added", "removed", "changed"]


class DiffSummary(BaseModel):
    added: int = 0
    removed: int = 0
    changed: int = 0


class CompareSide(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    score: int | None = None


class CompareResult(BaseModel):
    source: CompareSide
    tailored: CompareSide
    fields: list[FieldChange] = Field(default_factory=list)
    summary: DiffSummary = Field(default_factory=DiffSummary)
    explanations: list[Explanation] = Field(default_factory=list)
    #: Which diff produced ``fields`` (always ``ats``: see ``targets.field_diff``).
    diff_provider: Literal["ats", "builder"] = "ats"


class AtsSummary(BaseModel):
    total_targets: int = 0
    targets_by_status: dict[str, int] = Field(default_factory=dict)
    recent_analyses: list[AnalysisListItem] = Field(default_factory=list)
    in_progress: list[TargetRead] = Field(default_factory=list)
    upcoming: list[TargetRead] = Field(default_factory=list)


__all__ = [name for name in dir() if not name.startswith("_")]
