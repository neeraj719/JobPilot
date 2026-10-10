"""Profile + job preference endpoints (contract §3).

Mounted at ``/api/v1`` so the paths are ``/profile``, ``/preferences/job`` and
``/profiles/standing-answers``.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Response, status
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
    StandingAnswerRead,
    StandingAnswerUpsert,
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


@router.get(
    "/profiles/standing-answers",
    response_model=list[StandingAnswerRead],
    summary="Answers you saved once for reuse on every application",
)
def list_standing_answers(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[StandingAnswerRead]:
    return [StandingAnswerRead.model_validate(row) for row in service.list_standing_answers(db, user.id)]


@router.put(
    "/profiles/standing-answers",
    response_model=StandingAnswerRead,
    summary="Save a standing answer (replaces the one for the same question)",
)
def upsert_standing_answer(
    payload: StandingAnswerUpsert,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandingAnswerRead:
    row = service.upsert_standing_answer(
        db,
        user.id,
        question_key=payload.question_key,
        question_text=payload.question_text,
        answer=payload.answer,
        field_type=payload.field_type,
        applies_to=payload.applies_to,
        expires_at=payload.expires_at,
        is_active=payload.is_active,
    )
    return StandingAnswerRead.model_validate(row)


@router.delete(
    "/profiles/standing-answers/{standing_answer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a standing answer",
)
def delete_standing_answer(
    standing_answer_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_standing_answer(db, user.id, standing_answer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
