"""Matching API (mounted at ``/api/v1/matching``)."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.models.resume import Resume
from app.models.user import User
from app.modules.matching import service
from app.modules.matching.schemas import AnalyzeAllRequest, AnalyzeAllResult, MatchSummary

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze-all", response_model=AnalyzeAllResult, summary="Re-analyze every active job")
def analyze_all(
    payload: AnalyzeAllRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AnalyzeAllResult:
    payload = payload or AnalyzeAllRequest()
    resume = _load_resume(db, user.id, payload.resume_id)
    counts = service.analyze_all(
        db,
        user.id,
        resume=resume,
        only_unanalyzed=payload.only_unanalyzed,
        limit=payload.limit,
    )
    return AnalyzeAllResult(**counts)


@router.get("/summary", response_model=MatchSummary, summary="Match counts for the current user")
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatchSummary:
    return MatchSummary(**service.build_summary(db, user.id))


def _load_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID | None) -> Resume | None:
    if resume_id is None:
        return None
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user_id:
        raise NotFoundError("Resume not found")
    return resume
