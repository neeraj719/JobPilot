"""Applications API (CONTRACTS.md section 11).

Thin router: every endpoint resolves the caller's own application and delegates to
``applications.service``. Literal paths are declared before ``/{application_id}`` so
``/queue`` and ``/review-summary`` are never parsed as an id.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import ApplicationStatus, CompanyPriority, JobSourceType
from app.models.user import User
from app.modules.applications import service
from app.modules.applications.schemas import (
    AnswersUpdateRequest,
    ApplicationAnswerRead,
    ApplicationDetail,
    ApplicationEventRead,
    ApplicationPatch,
    ApplicationRead,
    CoverLetterRead,
    CoverLetterUpdate,
    QueueItem,
    ResumeAutomationRequest,
    ReviewCounts,
    ReviewSummary,
    SkipRequest,
    StartRequest,
    StatusUpdate,
)
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import PageResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------------------------------------------------------------------- collections


@router.get("/queue", response_model=PageResponse[QueueItem])
def get_queue(
    priority: CompanyPriority | None = Query(None),
    application_status: ApplicationStatus | None = Query(None, alias="status"),
    ready: bool = Query(False, description="Only applications with every answer prepared"),
    pagination: Pagination = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResponse[QueueItem]:
    """The work queue, ordered by company priority, then match score, then freshness."""
    return service.list_queue(db, user.id, pagination, priority=priority, status=application_status, ready_only=ready)


@router.get("/review-summary", response_model=ReviewCounts)
def get_review_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewCounts:
    """Counters for the Approval Center badge."""
    return service.review_summary(db, user.id)


@router.get("", response_model=PageResponse[ApplicationRead])
@router.get("/", response_model=PageResponse[ApplicationRead], include_in_schema=False)
def list_applications(
    application_status: ApplicationStatus | None = Query(None, alias="status"),
    source: JobSourceType | None = Query(None),
    company: str | None = Query(None),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    q: str | None = Query(None, description="Search job title, company or notes"),
    sort: str | None = Query("recent", description="recent | applied | score | company | priority"),
    pagination: Pagination = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResponse[ApplicationRead]:
    return service.list_applications(
        db,
        user.id,
        pagination,
        status=application_status,
        source=source,
        company=company,
        date_from=date_from,
        date_to=date_to,
        q=q,
        sort=sort,
    )


# --------------------------------------------------------------------------- one application


@router.get("/{application_id}", response_model=ApplicationDetail)
def get_application(
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationDetail:
    application = service.get_application(db, user.id, application_id)
    return ApplicationDetail.model_validate(service.build_detail(db, user.id, application))


@router.patch("/{application_id}", response_model=ApplicationRead)
def patch_application(
    application_id: uuid.UUID,
    payload: ApplicationPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    application = service.get_application(db, user.id, application_id)
    return service.to_read(service.update_application(db, application, payload))


@router.get("/{application_id}/events", response_model=list[ApplicationEventRead])
def get_events(
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApplicationEventRead]:
    application = service.get_application(db, user.id, application_id)
    return [ApplicationEventRead.model_validate(event) for event in service.list_events(db, application)]


@router.get("/{application_id}/review", response_model=ReviewSummary)
def get_review(
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewSummary:
    """What the Approval Center shows, including every blocker."""
    application = service.get_application(db, user.id, application_id)
    return service.build_review(db, application)


# --------------------------------------------------------------------------- automation


@router.post("/{application_id}/start", response_model=ApplicationRead)
def start_application(
    application_id: uuid.UUID,
    payload: StartRequest | None = Body(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    """Prepare answers and hand the application to the browser/adapter runner."""
    run_in_background = True if payload is None else payload.run_in_background
    application = service.start_application(db, application_id, user.id, run_in_background=run_in_background)
    return service.to_read(application)


@router.post("/{application_id}/answers/generate", response_model=list[ApplicationAnswerRead])
def regenerate_answers(
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApplicationAnswerRead]:
    """Re-run the answer engine, keeping everything you typed yourself."""
    application = service.get_application(db, user.id, application_id)
    rows = service.generate_application_answers(db, application)
    return [ApplicationAnswerRead.model_validate(row) for row in rows]


@router.put("/{application_id}/answers", response_model=list[ApplicationAnswerRead])
def update_answers(
    application_id: uuid.UUID,
    payload: AnswersUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApplicationAnswerRead]:
    from app.modules.applications.answers import save_user_answers

    application = service.get_application(db, user.id, application_id)
    save_user_answers(db, application, payload.answers)
    rows = sorted(application.answers or [], key=lambda a: (a.order, a.question_key))
    return [ApplicationAnswerRead.model_validate(row) for row in rows]


@router.post("/{application_id}/approve", response_model=ApplicationRead)
def approve_application(
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    """Human approval: validate, then submit through the adapter."""
    application = service.get_application(db, user.id, application_id)
    return service.to_read(service.approve(db, application, user))


@router.post("/{application_id}/submit", response_model=ApplicationRead)
def submit_application(
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    """Alias of ``/approve`` kept for API symmetry (section 11)."""
    application = service.get_application(db, user.id, application_id)
    return service.to_read(service.approve(db, application, user))


@router.post("/{application_id}/resume-automation", response_model=ApplicationRead)
def resume_automation(
    application_id: uuid.UUID,
    payload: ResumeAutomationRequest | None = Body(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    """Continue after you resolved a pause (answered a question, finished a CAPTCHA)."""
    application = service.get_application(db, user.id, application_id)
    request = payload or ResumeAutomationRequest()
    return service.to_read(
        service.resume_automation(
            db,
            application,
            request.answers,
            run_in_background=request.run_in_background,
        )
    )


# --------------------------------------------------------------------------- status


@router.patch("/{application_id}/status", response_model=ApplicationRead)
def set_status(
    application_id: uuid.UUID,
    payload: StatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    """Manual status change (moving to INTERVIEW also creates an interview row)."""
    application = service.get_application(db, user.id, application_id)
    return service.to_read(service.set_status(db, application, payload.status, payload.note))


@router.post("/{application_id}/skip", response_model=ApplicationRead)
def skip_application(
    application_id: uuid.UUID,
    payload: SkipRequest | None = Body(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    application = service.get_application(db, user.id, application_id)
    return service.to_read(service.skip(db, application, (payload.reason if payload else None)))


@router.post("/{application_id}/withdraw", response_model=ApplicationRead)
def withdraw_application(
    application_id: uuid.UUID,
    payload: SkipRequest | None = Body(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    application = service.get_application(db, user.id, application_id)
    return service.to_read(service.withdraw(db, application, (payload.reason if payload else None)))


# --------------------------------------------------------------------------- cover letter


@router.post("/{application_id}/cover-letter", response_model=CoverLetterRead)
def create_cover_letter(
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CoverLetterRead:
    application = service.get_application(db, user.id, application_id)
    return CoverLetterRead(cover_letter=service.generate_cover_letter(db, application))


@router.put("/{application_id}/cover-letter", response_model=CoverLetterRead)
def update_cover_letter(
    application_id: uuid.UUID,
    payload: CoverLetterUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CoverLetterRead:
    application = service.get_application(db, user.id, application_id)
    return CoverLetterRead(cover_letter=service.save_cover_letter(db, application, payload.content))
