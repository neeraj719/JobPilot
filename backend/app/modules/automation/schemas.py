"""Automation schemas (contract §14).

Semantic validation (timezone names, HH:MM, limits, auto-submit sources) lives in
``automation.service`` so failures surface as ``ValidationFailed`` with a stable
``code`` instead of a pydantic error blob.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AutomationRunStatus, AutomationRunTrigger, JobSourceType

__all__ = [
    "AutomationConfigRead",
    "AutomationConfigUpdate",
    "AutomationRunRead",
    "AutomationRunStep",
    "AutomationStatusRead",
    "RunRequest",
    "TodayStatus",
]


class AutomationConfigRead(BaseModel):
    """``GET /automation/config``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    enabled: bool = False
    schedule_time: str = "09:00"
    timezone: str = "Asia/Kolkata"
    daily_application_limit: int = 20
    per_platform_limit: dict[str, int] = Field(default_factory=dict)
    min_match_score: int = 75
    prioritize_priority_companies: bool = True
    only_posted_within_hours: int = 24
    enabled_sources: list[JobSourceType] = Field(default_factory=list)
    delay_between_actions_seconds: float = 2.0
    retry_limit: int = 3
    auto_submit_enabled: bool = False
    auto_submit_sources: list[JobSourceType] = Field(default_factory=list)
    auto_generate_cover_letters: bool = True
    notify_on_input_required: bool = True
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AutomationConfigUpdate(BaseModel):
    """``PUT /automation/config`` — every field optional, only the provided ones are written."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool | None = None
    schedule_time: str | None = None
    timezone: str | None = None
    daily_application_limit: int | None = Field(default=None, ge=0)
    per_platform_limit: dict[str, int] | None = None
    min_match_score: int | None = Field(default=None, ge=0, le=100)
    prioritize_priority_companies: bool | None = None
    only_posted_within_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    enabled_sources: list[str] | None = None
    delay_between_actions_seconds: float | None = Field(default=None, ge=0, le=60)
    retry_limit: int | None = Field(default=None, ge=0, le=10)
    auto_submit_enabled: bool | None = None
    auto_submit_sources: list[str] | None = None
    auto_generate_cover_letters: bool | None = None
    notify_on_input_required: bool | None = None


class AutomationRunStep(BaseModel):
    """One recorded pipeline step (also the shape stored in ``AutomationRun.steps``)."""

    step: str
    status: str = "SUCCESS"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class AutomationRunRead(BaseModel):
    """``GET /automation/runs/{id}``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger: AutomationRunTrigger
    status: AutomationRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    current_step: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    steps: list[AutomationRunStep] = Field(default_factory=list)
    error: str | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    """``POST /automation/run`` body."""

    dry_run: bool = False


class TodayStatus(BaseModel):
    applications_submitted: int = 0
    limit_remaining: int = 0
    daily_limit: int = 0


class AutomationStatusRead(BaseModel):
    """``GET /automation/status``."""

    enabled: bool = False
    next_run_at: datetime | None = None
    last_run: AutomationRunRead | None = None
    running: bool = False
    today: TodayStatus = Field(default_factory=TodayStatus)
