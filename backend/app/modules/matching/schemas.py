"""Pydantic schemas for the matching module."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CompanyPriority

__all__ = ["JobMatchRead", "MatchSummary", "AnalyzeAllRequest", "AnalyzeAllResult"]


class JobMatchRead(BaseModel):
    """A stored :class:`~app.models.job.JobMatch` as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    user_id: uuid.UUID
    resume_id: uuid.UUID | None = None

    match_score: int
    skill_score: int
    experience_score: int
    location_score: int
    salary_score: int | None = None
    title_score: int
    company_priority: CompanyPriority | None = None

    skill_match: dict[str, Any] = Field(default_factory=dict)
    experience_match: str | None = None
    location_match: str | None = None
    salary_match: str | None = None
    missing_skills: list[str] = Field(default_factory=list)
    explanation: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    analyzed_at: datetime
    model_used: str | None = None


class MatchSummary(BaseModel):
    """``GET /matching/summary``."""

    total_jobs: int
    analyzed: int
    matched_at_or_above_min: int
    high_match: int
    queued: int
    min_match_score: int


class AnalyzeAllRequest(BaseModel):
    """``POST /matching/analyze-all`` body (all fields optional)."""

    resume_id: uuid.UUID | None = None
    only_unanalyzed: bool = False
    limit: int = Field(default=500, ge=1, le=2000)


class AnalyzeAllResult(BaseModel):
    """``POST /matching/analyze-all`` response."""

    analyzed: int
    high_match: int
    matched_at_or_above_min: int
    average_score: float
    skipped: int = 0
