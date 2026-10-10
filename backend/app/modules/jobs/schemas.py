"""Pydantic schemas for the jobs module (``docs/CONTRACTS.md`` §9)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ApplicationStatus,
    ApplicationType,
    CompanyPriority,
    EmploymentType,
    JobSourceType,
    WorkMode,
)
from app.modules.matching.schemas import JobMatchRead

T = TypeVar("T")

__all__ = [
    "PageResponse",
    "CompanyBrief",
    "JobCard",
    "JobSourceRead",
    "ApplicationBrief",
    "JobDetail",
    "IngestResult",
    "DiscoverRequest",
    "DiscoverSourceResult",
    "DiscoverResult",
    "SkipRequest",
    "SourceInfoRead",
    "QueuedApplicationRead",
    "JobStats",
    "JobSortOption",
]

JobSortOption = str  # "match" | "posted" | "salary"


class PageResponse(BaseModel, Generic[T]):
    """Standard paginated envelope (mirrors ``common.schemas.PageResponse``)."""

    items: list[T]
    total: int
    page: int
    page_size: int


class CompanyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    logo_url: str | None = None
    domain: str | None = None


class JobCard(BaseModel):
    """One row in the jobs list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: CompanyBrief
    location: str | None = None
    work_mode: WorkMode | None = None
    employment_type: EmploymentType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    experience_min: float | None = None
    experience_max: float | None = None
    sources: list[JobSourceType] = Field(default_factory=list)
    primary_source: JobSourceType | None = None
    posted_at: datetime | None = None
    application_type: ApplicationType = ApplicationType.UNKNOWN
    match_score: int | None = None
    company_priority: CompanyPriority = CompanyPriority.P2
    application_status: ApplicationStatus | None = None
    application_id: uuid.UUID | None = None
    missing_skills: list[str] = Field(default_factory=list)


class JobSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: JobSourceType
    external_id: str
    url: str
    apply_url: str | None = None
    application_type: ApplicationType
    posted_at: datetime | None = None
    discovered_at: datetime
    last_seen_at: datetime


class ApplicationBrief(BaseModel):
    """Enough of an application for the job pages (the full shape lives in §11)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    priority: CompanyPriority
    match_score: int | None = None
    automation_state: str | None = None
    applied_at: datetime | None = None
    created_at: datetime | None = None


class JobDetail(JobCard):
    """``GET /jobs/{id}``."""

    description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    canonical_url: str | None = None
    apply_url: str | None = None
    is_active: bool = True
    job_sources: list[JobSourceRead] = Field(default_factory=list)
    match: JobMatchRead | None = None
    application: ApplicationBrief | None = None


class IngestResult(BaseModel):
    """Outcome of :func:`app.modules.jobs.service.ingest_discovered`."""

    jobs_found: int = 0
    jobs_new: int = 0
    duplicates_merged: int = 0
    #: Listings dropped because they were unusable (e.g. a blank company name).
    skipped: int = 0
    job_ids_new: list[uuid.UUID] = Field(default_factory=list)
    job_ids_all: list[uuid.UUID] = Field(default_factory=list)
    per_source: dict[str, dict[str, int]] = Field(default_factory=dict)


class DiscoverRequest(BaseModel):
    """``POST /jobs/discover`` body."""

    sources: list[JobSourceType] | None = None
    limit: int | None = Field(default=None, ge=1, le=200)


class DiscoverSourceResult(BaseModel):
    source: JobSourceType
    found: int = 0
    new: int = 0
    error: str | None = None


class DiscoverResult(BaseModel):
    jobs_found: int = 0
    jobs_new: int = 0
    duplicates_merged: int = 0
    jobs_analyzed: int = 0
    sources: list[DiscoverSourceResult] = Field(default_factory=list)


class SkipRequest(BaseModel):
    reason: str | None = None


class SourceInfoRead(BaseModel):
    """``GET /jobs/sources`` — adapter metadata plus how many listings we hold."""

    source: JobSourceType
    display_name: str
    is_mock: bool
    supports_auto_apply: bool
    requires_account: bool
    uses_browser: bool
    rate_limit_per_minute: int
    terms_note: str
    job_count: int = 0
    connected: bool = False


class QueuedApplicationRead(BaseModel):
    """Minimal application view returned by ``POST /jobs/{id}/queue|skip``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    priority: CompanyPriority
    match_score: int | None = None
    skipped_reason: str | None = None
    created_at: datetime | None = None


class JobStats(BaseModel):
    """Small aggregate used by the jobs page header."""

    total: int
    analyzed: int
    new_today: int
    by_source: dict[str, int] = Field(default_factory=dict)


JobCard.model_rebuild()
JobDetail.model_rebuild()
