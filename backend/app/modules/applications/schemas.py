"""Pydantic schemas for the applications module (CONTRACTS.md section 11)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    Actor,
    AnswerSource,
    AnswerStatus,
    ApplicationEventType,
    ApplicationStatus,
    ApplicationType,
    AutomationState,
    CompanyPriority,
    DocumentType,
    FieldType,
    JobSourceType,
    PauseReason,
)
from app.modules.applications.review import ReviewField, ReviewSummary
from app.modules.interviews.schemas import InterviewRead
from app.modules.jobs.schemas import JobCard, JobDetail

__all__ = [
    "AnswerUpdate",
    "AnswersUpdateRequest",
    "ApplicationAnswerRead",
    "ApplicationDetail",
    "ApplicationDocumentRead",
    "ApplicationEventRead",
    "ApplicationPatch",
    "ApplicationRead",
    "CoverLetterRead",
    "CoverLetterUpdate",
    "QueueItem",
    "ResumeAutomationRequest",
    "ReviewCounts",
    "ReviewField",
    "ReviewSummary",
    "SkipRequest",
    "StartRequest",
    "StatusUpdate",
]


# --------------------------------------------------------------------------- reads


class ApplicationRead(BaseModel):
    """One application row. Denormalised job fields keep list rendering cheap."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    resume_id: uuid.UUID | None = None
    automation_run_id: uuid.UUID | None = None

    status: ApplicationStatus
    priority: CompanyPriority
    match_score: int | None = None
    source: JobSourceType | None = None
    queue_position: int | None = None

    automation_state: AutomationState
    pause_reason: PauseReason | None = None
    pause_message: str | None = None
    retry_count: int = 0
    last_error: str | None = None
    review_required: bool = True
    approved_at: datetime | None = None
    auto_submit: bool = False

    cover_letter: str | None = None
    applied_at: datetime | None = None
    submitted_via: str | None = None
    external_application_id: str | None = None
    external_url: str | None = None
    confirmation_message: str | None = None

    last_update_at: datetime | None = None
    last_response_at: datetime | None = None
    next_action: str | None = None
    next_action_due: datetime | None = None
    notes: str | None = None
    skipped_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    # Denormalised by the service (not ORM columns).
    job_title: str | None = None
    company_name: str | None = None
    company_logo_url: str | None = None
    location: str | None = None
    application_type: ApplicationType | None = None
    ready: bool = False


class ApplicationAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order: int = 0
    question_key: str
    question_text: str
    field_type: FieldType = FieldType.TEXT
    options: list[Any] = Field(default_factory=list)
    required: bool = False
    answer: str | None = None
    answer_source: AnswerSource | None = None
    status: AnswerStatus
    confidence: float | None = None
    rationale: str | None = None
    is_sensitive: bool = False
    field_selector: str | None = None
    mapped_profile_field: str | None = None


class ApplicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    event_type: ApplicationEventType
    actor: Actor
    from_status: ApplicationStatus | None = None
    to_status: ApplicationStatus | None = None
    message: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ApplicationDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID | None = None
    document_type: DocumentType
    filename: str
    file_path: str | None = None
    content: str | None = None
    created_at: datetime


class ApplicationDetail(ApplicationRead):
    """``GET /applications/{id}``."""

    form_snapshot: dict[str, Any] = Field(default_factory=dict)
    answers: list[ApplicationAnswerRead] = Field(default_factory=list)
    events: list[ApplicationEventRead] = Field(default_factory=list)
    documents: list[ApplicationDocumentRead] = Field(default_factory=list)
    # The emails module is owned by another agent; its rows are passed through as JSON.
    emails: list[dict[str, Any]] = Field(default_factory=list)
    interviews: list[InterviewRead] = Field(default_factory=list)
    job: JobDetail | None = None
    review: ReviewSummary = Field(default_factory=ReviewSummary)


class QueueItem(BaseModel):
    """One row of ``GET /applications/queue``."""

    model_config = ConfigDict(from_attributes=True)

    application: ApplicationRead
    job: JobCard | None = None
    position: int = 0


class ReviewCounts(BaseModel):
    """``GET /applications/review-summary``."""

    pending_review: int = 0
    requires_input: int = 0
    ready_to_submit: int = 0


class CoverLetterRead(BaseModel):
    cover_letter: str | None = None


# --------------------------------------------------------------------------- writes


class AnswerUpdate(BaseModel):
    id: uuid.UUID
    answer: str | None = None


class AnswersUpdateRequest(BaseModel):
    answers: list[AnswerUpdate] = Field(default_factory=list)


class ResumeAutomationRequest(BaseModel):
    answers: list[AnswerUpdate] | None = None
    run_in_background: bool = True


class StatusUpdate(BaseModel):
    status: ApplicationStatus
    note: str | None = None


class SkipRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ApplicationPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    notes: str | None = None
    next_action: str | None = Field(default=None, max_length=500)
    next_action_due: datetime | None = None
    resume_id: uuid.UUID | None = None


class CoverLetterUpdate(BaseModel):
    content: str = Field(min_length=1)


class StartRequest(BaseModel):
    """``POST /applications/{id}/start`` body (optional)."""

    run_in_background: bool = True
