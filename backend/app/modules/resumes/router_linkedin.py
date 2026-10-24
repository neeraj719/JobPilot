"""``POST /api/v1/resumes/from-linkedin`` — a resume built from the LinkedIn connection.

Lives outside ``resumes/router.py`` on purpose (that file belongs to another stream); it is
mounted under ``/resumes`` (with the ``resume`` module guard) by
``app.modules.integrations.linkedin_router``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import RateLimitedError
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.modules.integrations.linkedin_schemas import LinkedInResumeRequest
from app.modules.resumes import service
from app.modules.resumes.schemas import ResumeRead

router = APIRouter()
CREATE_PER_MINUTE = 10


@router.post(
    "/from-linkedin",
    response_model=ResumeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a resume from your LinkedIn connection",
)
def create_from_linkedin(
    payload: LinkedInResumeRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    """DMA or export history → the export normaliser; basics only → your profile plus
    LinkedIn's name and email. The first version is recorded with ``change_source=SYSTEM``."""
    from app.modules.integrations import linkedin_service

    allowed, _ = rate_limiter.check(f"resumes:from-linkedin:{user.id}", CREATE_PER_MINUTE, 60)
    if not allowed:
        raise RateLimitedError("Too many requests for this feature. Try again in a minute.")
    body = payload or LinkedInResumeRequest()
    resume = linkedin_service.create_resume(
        db, user.id, name=body.name, target_role=body.target_role, template=body.template, set_default=body.set_default
    )
    db.flush()
    return service.resume_to_read(resume)
