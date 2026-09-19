"""Notification service (contract §5).

``notify`` is the single entry point every other module uses::

    from app.modules.notifications.service import notify
    notify(db, user.id, NotificationType.APPLICATION_SUBMITTED, "Applied to Google", link="/applications/<id>")
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.base import utcnow
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.modules.common.pagination import Pagination, paginate
from app.modules.common.schemas import PageResponse
from app.modules.notifications.schemas import NotificationRead

logger = logging.getLogger(__name__)


def notify(
    db: Session,
    user_id: uuid.UUID,
    type: NotificationType,  # noqa: A002 - part of the published contract
    title: str,
    body: str | None = None,
    link: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Notification:
    """Create an in-app notification. The caller owns the transaction."""
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title[:255],
        body=body,
        link=link[:500] if link else None,
        is_read=False,
        meta=meta or {},
        created_at=utcnow(),
    )
    db.add(notification)
    db.flush()
    logger.info("Notification %s for user %s: %s", type, user_id, title)
    return notification


def list_notifications(
    db: Session,
    user_id: uuid.UUID,
    pagination: Pagination,
    *,
    unread_only: bool = False,
) -> PageResponse[NotificationRead]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc())
    page = paginate(db, stmt, pagination, transform=NotificationRead.model_validate)
    return PageResponse[NotificationRead](items=page.items, total=page.total, page=page.page, page_size=page.page_size)


def get_notification(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = db.scalars(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    ).first()
    if notification is None:
        raise NotFoundError("Notification not found")
    return notification


def mark_read(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = get_notification(db, user_id, notification_id)
    notification.is_read = True
    db.flush()
    return notification


def mark_all_read(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.flush()
    count = int(result.rowcount or 0)
    logger.info("Marked %d notifications read for user %s", count, user_id)
    return count


def unread_count(db: Session, user_id: uuid.UUID) -> int:
    stmt = select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    return int(db.scalar(stmt) or 0)
