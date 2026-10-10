"""Dashboard schemas (contract §14)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Actor

__all__ = [
    "ActivityItem",
    "AttentionItem",
    "BucketCount",
    "ChartsResponse",
    "CompanyCount",
    "DayCount",
    "FunnelStage",
    "PeriodStats",
    "SourceCount",
    "StatsResponse",
    "StatusCount",
    "TotalsStats",
]


class PeriodStats(BaseModel):
    """Counts inside one time window (today / this week / this month)."""

    applications: int = 0
    responses: int = 0
    interviews: int = 0
    rejections: int = 0
    pending: int = 0
    jobs_found: int = 0


class TotalsStats(BaseModel):
    jobs_found: int = 0
    jobs_matched: int = 0
    high_match: int = 0
    queued: int = 0
    applications: int = 0
    responses: int = 0
    interviews: int = 0
    offers: int = 0
    rejections: int = 0
    pending_review: int = 0
    requires_input: int = 0


class AttentionItem(BaseModel):
    """One "needs you" card on the dashboard."""

    type: str
    title: str
    link: str
    count: int = 0


class StatsResponse(BaseModel):
    """``GET /dashboard/stats``."""

    today: PeriodStats = Field(default_factory=PeriodStats)
    week: PeriodStats = Field(default_factory=PeriodStats)
    month: PeriodStats = Field(default_factory=PeriodStats)
    totals: TotalsStats = Field(default_factory=TotalsStats)
    response_rate: float = 0.0
    interview_rate: float = 0.0
    offer_rate: float = 0.0
    attention: list[AttentionItem] = Field(default_factory=list)


class DayCount(BaseModel):
    date: date
    count: int = 0


class CompanyCount(BaseModel):
    name: str
    count: int = 0


class SourceCount(BaseModel):
    source: str
    count: int = 0


class StatusCount(BaseModel):
    status: str
    count: int = 0


class FunnelStage(BaseModel):
    stage: str
    count: int = 0


class BucketCount(BaseModel):
    bucket: str
    count: int = 0


class ChartsResponse(BaseModel):
    """``GET /dashboard/charts?range=7d|30d|90d``."""

    range: str = "30d"
    start_date: date | None = None
    end_date: date | None = None
    applications_per_day: list[DayCount] = Field(default_factory=list)
    responses_per_day: list[DayCount] = Field(default_factory=list)
    by_company: list[CompanyCount] = Field(default_factory=list)
    by_source: list[SourceCount] = Field(default_factory=list)
    by_status: list[StatusCount] = Field(default_factory=list)
    funnel: list[FunnelStage] = Field(default_factory=list)
    match_distribution: list[BucketCount] = Field(default_factory=list)


class ActivityItem(BaseModel):
    """One entry of the merged audit-log + application-event timeline."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str  # AUDIT | EVENT
    action: str  # audit action or ApplicationEventType
    actor: Actor = Actor.SYSTEM
    level: str = "INFO"
    message: str = ""
    application_id: uuid.UUID | None = None
    automation_run_id: uuid.UUID | None = None
    from_status: str | None = None
    to_status: str | None = None
    link: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
