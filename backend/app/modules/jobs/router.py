"""Jobs API (mounted at ``/api/v1/jobs``) — thin routing over :mod:`app.modules.jobs.service`."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import CompanyPriority, JobSourceType, WorkMode
from app.models.user import User
from app.modules.jobs import service
from app.modules.jobs.schemas import (
    DiscoverRequest,
    DiscoverResult,
    JobCard,
    JobDetail,
    PageResponse,
    QueuedApplicationRead,
    SkipRequest,
    SourceInfoRead,
)
from app.modules.matching.schemas import JobMatchRead

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=PageResponse[JobCard], summary="List discovered jobs")
@router.get("/", response_model=PageResponse[JobCard], include_in_schema=False)
def list_jobs(
    q: str | None = Query(default=None, description="Free text over title, company and description"),
    min_score: int | None = Query(default=None, ge=0, le=100),
    max_score: int | None = Query(default=None, ge=0, le=100),
    salary_min: int | None = Query(default=None, ge=0),
    location: str | None = None,
    work_mode: WorkMode | None = None,
    company: str | None = None,
    experience_min: float | None = Query(default=None, ge=0),
    experience_max: float | None = Query(default=None, ge=0),
    source: JobSourceType | None = None,
    posted_within_hours: int | None = Query(default=None, ge=1, le=24 * 90),
    status_filter: str | None = Query(default=None, alias="status", description="Application status or 'NONE'"),
    priority: CompanyPriority | None = None,
    sort: str = Query(default="match", pattern="^(match|posted|salary)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PageResponse[JobCard]:
    return service.list_jobs(
        db,
        user.id,
        page=page,
        page_size=page_size,
        sort=sort,
        q=q,
        min_score=min_score,
        max_score=max_score,
        salary_min=salary_min,
        location=location,
        work_mode=work_mode,
        company=company,
        experience_min=experience_min,
        experience_max=experience_max,
        source=source,
        posted_within_hours=posted_within_hours,
        status=status_filter,
        priority=priority,
    )


@router.get("/sources", response_model=list[SourceInfoRead], summary="Job sources and their adapters")
def list_sources(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SourceInfoRead]:
    return service.list_sources(db, user.id)


@router.post("/discover", response_model=DiscoverResult, summary="Run discovery across the enabled sources")
def discover(
    payload: DiscoverRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DiscoverResult:
    return service.discover_jobs(db, user.id, payload or DiscoverRequest())


@router.get("/{job_id}", response_model=JobDetail, summary="Job detail")
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobDetail:
    return service.get_job_detail(db, user.id, job_id)


@router.post("/{job_id}/analyze", response_model=JobMatchRead, summary="Score this job for the current user")
def analyze(
    job_id: uuid.UUID,
    resume_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobMatchRead:
    from app.modules.matching.service import analyze_job

    job = service.get_job(db, job_id)
    resume = _load_resume(db, user.id, resume_id)
    match = analyze_job(db, user.id, job, resume)
    return JobMatchRead.model_validate(match)


@router.post(
    "/{job_id}/queue",
    response_model=QueuedApplicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Queue this job for application",
)
def queue(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueuedApplicationRead:
    application = service.queue_job(db, user.id, job_id)
    return QueuedApplicationRead.model_validate(application)


@router.post("/{job_id}/skip", response_model=QueuedApplicationRead, summary="Skip this job")
def skip(
    job_id: uuid.UUID,
    payload: SkipRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueuedApplicationRead:
    application = service.skip_job(db, user.id, job_id, (payload or SkipRequest()).reason)
    return QueuedApplicationRead.model_validate(application)


def _load_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID | None):
    """Resolve an explicit resume id, scoped to the current user."""
    if resume_id is None:
        return None
    from app.core.exceptions import NotFoundError
    from app.models.resume import Resume

    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user_id:
        raise NotFoundError("Resume not found")
    return resume
