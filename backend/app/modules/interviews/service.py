"""Interview tracking and AI preparation (CONTRACTS.md section 11, "Interviews").

Every query is scoped through ``Application.user_id``: an interview only exists as part
of an application, and one user can never see another's rounds.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.database import soft_delete
from app.core.exceptions import NotFoundError
from app.models.application import Application
from app.models.base import utcnow
from app.models.enums import Actor, ApplicationEventType, InterviewStatus
from app.models.interview import Interview
from app.models.job import Job
from app.modules.common.pagination import Pagination, paginate_sequence
from app.modules.common.schemas import PageResponse
from app.modules.interviews.schemas import InterviewCreate, InterviewRead, InterviewUpdate

logger = logging.getLogger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_FAR_FUTURE = datetime(9999, 1, 1, tzinfo=timezone.utc)


def _aware(value: datetime | None, default: datetime = _EPOCH) -> datetime:
    if value is None:
        return default
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def to_read(interview: Interview) -> InterviewRead:
    """ORM row -> ``InterviewRead``, with the company/job denormalised for calendars."""
    read = InterviewRead.model_validate(interview)
    application = getattr(interview, "application", None)
    job = getattr(application, "job", None) if application is not None else None
    if job is not None:
        read.job_title = job.title
        read.company_name = getattr(getattr(job, "company", None), "name", None)
    return read


def get_application(db: Session, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    application = db.scalars(
        select(Application).where(Application.id == application_id, Application.user_id == user_id)
    ).first()
    if application is None:
        raise NotFoundError("Application not found")
    return application


def get_interview(db: Session, user_id: uuid.UUID, interview_id: uuid.UUID) -> Interview:
    """One interview, joined through the application so ownership is enforced."""
    interview = db.scalars(
        select(Interview)
        .join(Application, Interview.application_id == Application.id)
        .where(Interview.id == interview_id, Application.user_id == user_id)
    ).first()
    if interview is None:
        raise NotFoundError("Interview not found")
    return interview


def list_interviews(
    db: Session,
    user_id: uuid.UUID,
    pagination: Pagination,
    *,
    upcoming: bool | None = None,
    application_id: uuid.UUID | None = None,
    status: InterviewStatus | None = None,
) -> PageResponse[InterviewRead]:
    """``GET /interviews`` - newest first, or soonest first when ``upcoming``."""
    stmt = (
        select(Interview)
        .join(Application, Interview.application_id == Application.id)
        .where(Application.user_id == user_id)
    )
    if application_id is not None:
        stmt = stmt.where(Interview.application_id == application_id)
    if status is not None:
        stmt = stmt.where(Interview.status == status)

    rows = list(db.scalars(stmt).unique().all())
    now = utcnow()
    if upcoming:
        rows = [
            row
            for row in rows
            if row.status in {InterviewStatus.SCHEDULED, InterviewStatus.RESCHEDULED}
            and (row.scheduled_at is None or _aware(row.scheduled_at, _FAR_FUTURE) >= now)
        ]
        rows.sort(key=lambda r: _aware(r.scheduled_at, _FAR_FUTURE))
    else:
        rows.sort(key=lambda r: -_aware(r.scheduled_at or r.created_at).timestamp())

    page = paginate_sequence(rows, pagination)
    return PageResponse[InterviewRead](
        items=[to_read(row) for row in page.items],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


def create_interview(db: Session, user_id: uuid.UUID, payload: InterviewCreate) -> Interview:
    application = get_application(db, user_id, payload.application_id)
    interview = Interview(
        application_id=application.id,
        user_id=user_id,
        interview_type=payload.interview_type,
        status=payload.status,
        round_number=payload.round_number,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        location_or_link=payload.location_or_link,
        interviewer=payload.interviewer,
        notes=payload.notes,
        prep_material={},
    )
    db.add(interview)
    db.flush()
    _record(db, application, f"Interview scheduled ({payload.interview_type.value})", meta={"interview_id": str(interview.id)})
    audit(
        db,
        action="interview.created",
        message=f"Interview scheduled for {_label(application)}",
        user_id=user_id,
        application_id=application.id,
        actor=Actor.USER,
        meta={"interview_id": str(interview.id), "interview_type": payload.interview_type.value},
    )
    logger.info("Created interview %s for application %s", interview.id, application.id)
    return interview


def update_interview(db: Session, user_id: uuid.UUID, interview_id: uuid.UUID, payload: InterviewUpdate) -> Interview:
    interview = get_interview(db, user_id, interview_id)
    data = payload.model_dump(exclude_unset=True)
    for field_name, value in data.items():
        setattr(interview, field_name, value)
    db.flush()
    application = db.get(Application, interview.application_id)
    if application is not None:
        _record(db, application, "Interview updated", meta={"interview_id": str(interview.id), **{k: str(v) for k, v in data.items()}})
    logger.info("Updated interview %s (%s)", interview.id, ", ".join(data) or "no changes")
    return interview


def delete_interview(db: Session, user_id: uuid.UUID, interview_id: uuid.UUID) -> None:
    interview = get_interview(db, user_id, interview_id)
    application_id = interview.application_id
    soft_delete(interview)
    db.flush()
    audit(
        db,
        action="interview.deleted",
        message="Interview removed",
        user_id=user_id,
        application_id=application_id,
        actor=Actor.USER,
        meta={"interview_id": str(interview_id)},
    )


def generate_prep(db: Session, user_id: uuid.UUID, interview_id: uuid.UUID) -> Interview:
    """Fill ``prep_material`` via ``ai.tasks.generate_interview_prep``."""
    from app.modules.ai import tasks as ai_tasks
    from app.modules.profiles.service import build_candidate_context

    interview = get_interview(db, user_id, interview_id)
    application = get_application(db, user_id, interview.application_id)
    job = db.get(Job, application.job_id)
    candidate = build_candidate_context(db, user_id, application.resume_id)

    prep = ai_tasks.generate_interview_prep(job, candidate, interview.interview_type.value)
    material = prep.model_dump(mode="json")
    material["generated_at"] = utcnow().isoformat()
    interview.prep_material = material
    db.flush()

    _record(
        db,
        application,
        f"Interview preparation generated ({interview.interview_type.value})",
        meta={"interview_id": str(interview.id), "questions": sum(len(v) for v in prep.model_dump().values())},
    )
    audit(
        db,
        action="interview.prep_generated",
        message=f"Generated interview preparation for {_label(application)}",
        user_id=user_id,
        application_id=application.id,
        actor=Actor.AUTOMATION,
        meta={"interview_id": str(interview.id), "interview_type": interview.interview_type.value},
    )
    logger.info("Generated interview prep for %s", interview.id)
    return interview


def upcoming_for_user(db: Session, user_id: uuid.UUID, limit: int = 5) -> list[Interview]:
    """The next few scheduled rounds (used by the dashboard)."""
    now = utcnow()
    rows = db.scalars(
        select(Interview)
        .join(Application, Interview.application_id == Application.id)
        .where(Application.user_id == user_id, Interview.status.in_((InterviewStatus.SCHEDULED, InterviewStatus.RESCHEDULED)))
    ).unique().all()
    future = [row for row in rows if row.scheduled_at is None or _aware(row.scheduled_at, _FAR_FUTURE) >= now]
    future.sort(key=lambda r: _aware(r.scheduled_at, _FAR_FUTURE))
    return future[: max(0, limit)]


def _label(application: Application) -> str:
    job = getattr(application, "job", None)
    company = getattr(getattr(job, "company", None), "name", None) or "Unknown company"
    return f"{company} - {getattr(job, 'title', 'role')}"


def _record(db: Session, application: Application, message: str, *, meta: dict[str, Any] | None = None) -> None:
    from app.modules.applications.service import record_event

    record_event(db, application, ApplicationEventType.NOTE, message, actor=Actor.USER, meta=meta)


__all__ = [
    "create_interview",
    "delete_interview",
    "generate_prep",
    "get_interview",
    "list_interviews",
    "to_read",
    "upcoming_for_user",
    "update_interview",
]
