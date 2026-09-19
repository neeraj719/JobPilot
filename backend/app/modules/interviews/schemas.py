"""Interview schemas (CONTRACTS.md section 11, "Interviews")."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InterviewStatus, InterviewType

__all__ = [
    "InterviewCreate",
    "InterviewPrepRead",
    "InterviewRead",
    "InterviewUpdate",
]


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    interview_type: InterviewType
    status: InterviewStatus
    round_number: int = 1
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    location_or_link: str | None = None
    interviewer: str | None = None
    notes: str | None = None
    outcome: str | None = None
    prep_material: dict[str, Any] = Field(default_factory=dict)
    source_email_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    # Denormalised for calendar rendering (filled by the service).
    company_name: str | None = None
    job_title: str | None = None


class InterviewCreate(BaseModel):
    application_id: uuid.UUID
    interview_type: InterviewType = InterviewType.OTHER
    status: InterviewStatus = InterviewStatus.SCHEDULED
    round_number: int = Field(default=1, ge=1, le=20)
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    location_or_link: str | None = Field(default=None, max_length=1000)
    interviewer: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class InterviewUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    interview_type: InterviewType | None = None
    status: InterviewStatus | None = None
    round_number: int | None = Field(default=None, ge=1, le=20)
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    location_or_link: str | None = Field(default=None, max_length=1000)
    interviewer: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    outcome: str | None = Field(default=None, max_length=50)


class InterviewPrepRead(BaseModel):
    """``POST /interviews/{id}/prep`` response."""

    model_config = ConfigDict(from_attributes=True)

    interview_id: uuid.UUID
    technical: list[str] = Field(default_factory=list)
    behavioral: list[str] = Field(default_factory=list)
    company_specific: list[str] = Field(default_factory=list)
    job_specific: list[str] = Field(default_factory=list)
    resume_based: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None
