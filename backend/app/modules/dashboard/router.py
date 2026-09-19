"""Dashboard endpoints (contract §14). Thin — the aggregation lives in the service."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.modules.dashboard import service
from app.modules.dashboard.schemas import ActivityItem, ChartsResponse, StatsResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StatsResponse:
    return service.build_stats(db, user.id)


@router.get("/charts", response_model=ChartsResponse)
def get_charts(
    range: str = Query(service.DEFAULT_RANGE, pattern="^(7d|30d|90d)$", description="7d | 30d | 90d"),  # noqa: A002
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChartsResponse:
    return service.build_charts(db, user.id, range)


@router.get("/activity", response_model=list[ActivityItem])
def get_activity(
    limit: int = Query(30, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActivityItem]:
    return service.list_activity(db, user.id, limit)
