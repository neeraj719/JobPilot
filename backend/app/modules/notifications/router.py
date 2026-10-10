"""Notification endpoints (contract §5). Mounted at ``/api/v1/notifications``."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import CountResponse, PageResponse
from app.modules.notifications import service
from app.modules.notifications.schemas import MarkAllReadResponse, NotificationRead

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/unread-count", response_model=CountResponse, summary="Number of unread notifications")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CountResponse:
    return CountResponse(count=service.unread_count(db, user.id))


@router.post("/read-all", response_model=MarkAllReadResponse, summary="Mark every notification as read")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MarkAllReadResponse:
    return MarkAllReadResponse(ok=True, updated=service.mark_all_read(db, user.id))


@router.get("", response_model=PageResponse[NotificationRead], summary="The user's notifications")
@router.get("/", response_model=PageResponse[NotificationRead], include_in_schema=False)
def list_notifications(
    pagination: Pagination = Depends(),
    unread_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResponse[NotificationRead]:
    return service.list_notifications(db, user.id, pagination, unread_only=unread_only)


@router.post("/{notification_id}/read", response_model=NotificationRead, summary="Mark one notification as read")
def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationRead:
    return NotificationRead.model_validate(service.mark_read(db, user.id, notification_id))
