"""Profile + job preference endpoints (contract §3).

Mounted at ``/api/v1`` so the paths are ``/profile`` and ``/preferences/job``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.modules.profiles import service
from app.modules.profiles.schemas import (
    JobPreferenceRead,
    JobPreferenceUpdate,
    ProfileRead,
    ProfileUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/profile", response_model=ProfileRead, summary="Current user's candidate profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProfileRead:
    profile = service.get_or_create_profile(db, user.id)
    preference = service.get_or_create_job_preference(db, user.id)
    return service.to_profile_read(profile, preference)


@router.put("/profile", response_model=ProfileRead, summary="Update the candidate profile")
def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileRead:
    profile = service.update_profile(db, user.id, payload)
    preference = service.get_or_create_job_preference(db, user.id)
    return service.to_profile_read(profile, preference)


@router.get("/preferences/job", response_model=JobPreferenceRead, summary="Job search preferences")
def get_job_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> JobPreferenceRead:
    return service.to_preference_read(service.get_or_create_job_preference(db, user.id))


@router.put("/preferences/job", response_model=JobPreferenceRead, summary="Update job search preferences")
def update_job_preferences(
    payload: JobPreferenceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobPreferenceRead:
    return service.to_preference_read(service.update_job_preference(db, user.id, payload))
