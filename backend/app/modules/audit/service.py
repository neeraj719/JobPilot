"""Audit log read service (contract §5).

Writing is done everywhere through ``app.core.audit.audit``; this module only exposes
the user-scoped, paginated read side used by the Activity views.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import list_audit_logs
from app.models.audit import AuditLog
from app.modules.audit.schemas import AuditLogRead
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import PageResponse

logger = logging.getLogger(__name__)


def count_audit_logs(
    db: Session,
    *,
    user_id: uuid.UUID,
    application_id: uuid.UUID | None = None,
    automation_run_id: uuid.UUID | None = None,
    action_prefix: str | None = None,
) -> int:
    """Total matching rows - mirrors the filters of ``core.audit.list_audit_logs``."""
    stmt = select(func.count(AuditLog.id)).where(AuditLog.user_id == user_id)
    if application_id:
        stmt = stmt.where(AuditLog.application_id == application_id)
    if automation_run_id:
        stmt = stmt.where(AuditLog.automation_run_id == automation_run_id)
    if action_prefix:
        stmt = stmt.where(AuditLog.action.like(f"{action_prefix}%"))
    return int(db.scalar(stmt) or 0)


def list_logs(
    db: Session,
    user_id: uuid.UUID,
    pagination: Pagination,
    *,
    application_id: uuid.UUID | None = None,
    automation_run_id: uuid.UUID | None = None,
    action_prefix: str | None = None,
) -> PageResponse[AuditLogRead]:
    rows = list_audit_logs(
        db,
        user_id=user_id,
        application_id=application_id,
        automation_run_id=automation_run_id,
        action_prefix=action_prefix,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    total = count_audit_logs(
        db,
        user_id=user_id,
        application_id=application_id,
        automation_run_id=automation_run_id,
        action_prefix=action_prefix,
    )
    return PageResponse[AuditLogRead](
        items=[AuditLogRead.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
