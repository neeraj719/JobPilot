"""Interviews API (CONTRACTS.md section 11). Thin router - logic lives in the service."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import InterviewStatus
from app.models.user import User
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import PageResponse
from app.modules.interviews import service
from app.modules.interviews.schemas import InterviewCreate, InterviewRead, InterviewUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=PageResponse[InterviewRead])
@router.get("/", response_model=PageResponse[InterviewRead], include_in_schema=False)
def list_interviews(
    upcoming: bool | None = Query(None, description="Only rounds that have not happened yet"),
    application_id: uuid.UUID | None = Query(None),
    interview_status: InterviewStatus | None = Query(None, alias="status"),
    pagination: Pagination = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResponse[InterviewRead]:
    """Every interview of the current user, newest first (or soonest when ``upcoming``)."""
    return service.list_interviews(
        db,
        user.id,
        pagination,
        upcoming=upcoming,
        application_id=application_id,
        status=interview_status,
    )


@router.post("", response_model=InterviewRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=InterviewRead, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_interview(
    payload: InterviewCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewRead:
    return service.to_read(service.create_interview(db, user.id, payload))


@router.get("/{interview_id}", response_model=InterviewRead)
def get_interview(
    interview_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewRead:
    return service.to_read(service.get_interview(db, user.id, interview_id))


@router.patch("/{interview_id}", response_model=InterviewRead)
def update_interview(
    interview_id: uuid.UUID,
    payload: InterviewUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewRead:
    return service.to_read(service.update_interview(db, user.id, interview_id, payload))


@router.post("/{interview_id}/prep", response_model=InterviewRead)
def generate_prep(
    interview_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewRead:
    """Generate the AI preparation sheet and store it on the interview."""
    return service.to_read(service.generate_prep(db, user.id, interview_id))


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview(
    interview_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_interview(db, user.id, interview_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
