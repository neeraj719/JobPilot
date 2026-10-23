"""ATS optimizer models (job targets, job-description snapshots, analyses, suggestions).

Owned by the ``ats`` work stream (see ``notes/resume-studio-plan.md``). Tables live in the
``media`` schema next to the resumes they analyse and follow ``docs/DATABASE.md``: uuid
primary keys, ``StandardColumnsMixin``, soft delete, partial unique indexes.

``job_targets``
    One saved opportunity: company + role (+ posting URL), its status in the application
    workflow, the resume it is tailored from / to, and pointers to the latest JD snapshot and
    analysis. A target is unique per user by ``fingerprint`` (sha256 of the normalised company,
    role and URL), enforced by a **partial** unique index so a deleted target can be re-created.
``job_description_snapshots``
    An immutable copy of a job description as it was read (pasted, uploaded, fetched from a
    posting URL or a public board, copied from a discovered job), with the structured
    requirements extracted from it. ``user_id`` is the owner; ``job_target_id`` is null for a
    JD analysed without saving a target.
``ats_analyses``
    One estimated compatibility report of one resume version against one snapshot. The
    deterministic part is computed synchronously; ``status``/``progress`` track the optional
    model polish that runs afterwards.
``optimization_suggestions``
    The concrete changes an analysis proposes, with the guard results (``checks``) and what the
    user did with each (applied / edited / ignored).

The two back-pointers of ``job_targets`` (``latest_snapshot_id``, ``last_analysis_id``) close a
cycle with the tables that point at the target, so their foreign keys are created with
``use_alter`` (named constraints, added after the tables exist).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SCHEMA_MEDIA, Base, StandardColumnsMixin, UTCDateTime, soft_delete_where
from app.models.enums import (
    AtsAnalysisStatus,
    JdSource,
    JobTargetStatus,
    SuggestionKind,
    SuggestionStatus,
    WorkMode,
)

#: Raw JD text is capped at this many characters (the rest is never stored).
JD_TEXT_MAX_CHARS = 50_000


class JobTarget(StandardColumnsMixin, Base):
    __tablename__ = "job_targets"
    __table_args__ = (
        Index("uq_job_targets_user_fingerprint_active", "user_id", "fingerprint", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MEDIA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_company: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("master.companies.id", ondelete="SET NULL"))
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    job_url: Mapped[str | None] = mapped_column(String(2048))
    #: sha256(normalized company | normalized role | normalized URL) — the uniqueness key.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    work_mode: Mapped[WorkMode | None] = mapped_column(Enum(WorkMode, native_enum=False, length=10))
    required_skills: Mapped[list[Any]] = mapped_column(JSON, default=list)
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[JobTargetStatus] = mapped_column(
        Enum(JobTargetStatus, native_enum=False, length=20), default=JobTargetStatus.SAVED, index=True, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    follow_up_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.resumes.id", ondelete="SET NULL"))
    tailored_resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.resumes.id", ondelete="SET NULL"))
    tailored_resume_version: Mapped[int | None] = mapped_column(Integer)
    #: The tailored resume's version when the status moved to APPLIED ("what was sent").
    submitted_resume_version: Mapped[int | None] = mapped_column(Integer)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transaction.applications.id", ondelete="SET NULL"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("unified.jobs.id", ondelete="SET NULL"))
    latest_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "media.job_description_snapshots.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_job_targets_latest_snapshot_id",
        )
    )
    last_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media.ats_analyses.id", ondelete="SET NULL", use_alter=True, name="fk_job_targets_last_analysis_id")
    )
    last_analyzed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class JobDescriptionSnapshot(StandardColumnsMixin, Base):
    """An immutable copy of a job description and the requirements extracted from it."""

    __tablename__ = "job_description_snapshots"
    __table_args__ = {"schema": SCHEMA_MEDIA}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    job_target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media.job_targets.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[JdSource] = mapped_column(Enum(JdSource, native_enum=False, length=20), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048))
    fetched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    title: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: {required_skills, preferred_skills, responsibilities, qualifications, keywords, seniority,
    #:  years_min, years_max, education, ...} — see ``ats.schemas.StructuredJD``.
    structured: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_from_previous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Required/preferred skills added and removed compared with the previous snapshot of the target.
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AtsAnalysis(StandardColumnsMixin, Base):
    """One estimated ATS compatibility report: a resume version against a JD snapshot."""

    __tablename__ = "ats_analyses"
    __table_args__ = {"schema": SCHEMA_MEDIA}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media.resumes.id", ondelete="CASCADE"), index=True, nullable=False)
    resume_version: Mapped[int] = mapped_column(Integer, nullable=False)
    job_target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media.job_targets.id", ondelete="SET NULL"), index=True
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media.job_description_snapshots.id", ondelete="SET NULL"), index=True
    )
    #: The analysis this one re-ran (after applying suggestions); null for a first analysis.
    previous_analysis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.ats_analyses.id", ondelete="SET NULL"))
    status: Mapped[AtsAnalysisStatus] = mapped_column(
        Enum(AtsAnalysisStatus, native_enum=False, length=20), default=AtsAnalysisStatus.PENDING, index=True, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    overall_score: Mapped[int | None] = mapped_column(Integer)
    category_scores: Mapped[list[Any]] = mapped_column(JSON, default=list)
    matched_keywords: Mapped[list[Any]] = mapped_column(JSON, default=list)
    missing_keywords: Mapped[list[Any]] = mapped_column(JSON, default=list)
    weak_items: Mapped[list[Any]] = mapped_column(JSON, default=list)
    parse_risks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    methodology_version: Mapped[str] = mapped_column(String(40), nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ai_provider: Mapped[str | None] = mapped_column(String(60))
    ai_model: Mapped[str | None] = mapped_column(String(120))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    suggestions: Mapped[list[OptimizationSuggestion]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="OptimizationSuggestion.ordinal"
    )


class OptimizationSuggestion(StandardColumnsMixin, Base):
    """One change an analysis proposes, and what the user did with it."""

    __tablename__ = "optimization_suggestions"
    __table_args__ = {"schema": SCHEMA_MEDIA}

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.ats_analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[SuggestionKind] = mapped_column(Enum(SuggestionKind, native_enum=False, length=30), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: Field path inside ``parsed_data``: ``skills``, ``summary``, ``experience[1].description``, ``projects``.
    target_path: Mapped[str | None] = mapped_column(String(200))
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str | None] = mapped_column(Text)
    safe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmation_label: Mapped[str | None] = mapped_column(String(300))
    #: Points on the overall estimate if this change alone is applied.
    estimated_gain: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus, native_enum=False, length=20), default=SuggestionStatus.PROPOSED, index=True, nullable=False
    )
    applied_version: Mapped[int | None] = mapped_column(Integer)
    #: Guard results and evidence: {"bullet_problem": null, "evidence": [...], "ai_polished": false, ...}.
    checks: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    analysis: Mapped[AtsAnalysis] = relationship(back_populates="suggestions")


__all__ = ["JD_TEXT_MAX_CHARS", "AtsAnalysis", "JobDescriptionSnapshot", "JobTarget", "OptimizationSuggestion"]
